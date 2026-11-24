import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from aiohttp.test_utils import TestClient, TestServer

from cinema.external_media import ExternalMedia, Source, public_url
from cinema.server import create_app


class FixtureMedia(ExternalMedia):
    """Register controlled sources without contacting an upstream site."""

    async def resolve(self, url, mode):
        public_url(url)
        source_id = Path(urlsplit(url).path).stem
        self.sources[source_id] = Source(
            source_id, {'url': url, 'kind': 'mp4', 'title': source_id, 'duration': 120},
            mode, url)
        return [self.describe(source_id)]


class SourceUnavailableHTTP(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.engine = FixtureMedia('http://unused', 'fixture')
        with patch('cinema.server.ExternalMedia', return_value=self.engine):
            app = create_app(self.data, 'fixture-pass-123', secure=False)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()
        response = await self.client.post('/api/login', json={'password': 'fixture-pass-123'})
        self.assertEqual(response.status, 200)
        self.sockets = []

    async def asyncTearDown(self):
        for ws in self.sockets:
            await ws.close()
        await self.client.close()
        self.tmp.cleanup()

    async def connect(self, room):
        ws = await self.client.ws_connect('/ws?room=' + room)
        self.sockets.append(ws)
        hello = await ws.receive_json(timeout=2)
        state = await ws.receive_json(timeout=2)
        self.assertEqual(hello['type'], 'hello')
        self.assertEqual(state['type'], 'state')
        return ws, hello, state

    async def pair(self, room='AB'):
        host, _, _ = await self.connect(room)
        guest, hello, joined = await self.connect(room)
        self.assertEqual(await host.receive_json(timeout=2), joined)
        self.assertNotEqual(joined['host'], hello['id'])
        return host, guest

    async def receive_pair(self, pair):
        states = [await ws.receive_json(timeout=2) for ws in pair]
        self.assertEqual(states[0]['type'], 'state')
        self.assertEqual(states[0], states[1])
        return states[0]

    async def act(self, pair, **command):
        await pair[0].send_json(command)
        return await self.receive_pair(pair)

    async def resolve(self, name):
        response = await self.client.post('/api/network/resolve', json={
            'url': 'https://media.example/' + name + '.mp4', 'mode': 'relay'})
        self.assertEqual(response.status, 200)
        return (await response.json())['choices'][0]['file']

    def assert_idle(self, state):
        self.assertIsNone(state['file'])
        self.assertTrue(state['paused'])
        self.assertEqual(state['position'], 0)
        self.assertFalse(state['boosting'])
        self.assertEqual(state['base_rate'], 1.5)
        self.assertEqual(state['playback_rate'], 1.5)

    async def test_network_reclamation_stops_both_members_at_selected_base_rate(self):
        source = await self.resolve('first')
        other_source = await self.resolve('other')
        pair = await self.pair()
        other_pair = await self.pair('CD')
        other_playing = await self.act(
            other_pair, type='control', file=other_source, position=7, paused=False)
        started = await self.act(pair, type='control', file=source, position=12, paused=False)
        await self.act(pair, type='rate', file=source, rate=1.5)
        playing = await self.act(pair, type='boost', file=source, active=True)
        self.assertTrue(playing['boosting'])
        self.assertEqual(playing['playback_rate'], 2)
        # Let the real watchdog observe this source as active before completing it.
        await asyncio.sleep(.25)
        response = await self.client.post('/api/network/first/complete')
        self.assertEqual(response.status, 200)
        stopped = await self.receive_pair(pair)
        self.assert_idle(stopped)
        self.assertEqual(stopped['host'], playing['host'])
        self.assertEqual(stopped['members'], playing['members'])
        self.assertEqual(stopped['online'], 2)
        self.assertEqual(stopped['library_version'], playing['library_version'])
        self.assertEqual((await self.client.get('/api/network/first/source')).status, 410)
        self.assertEqual((await self.client.get('/api/network/other/source')).status, 200)
        # Duplicate completion notices and later snapshots must keep the idle invariant.
        for _ in range(2):
            self.assertEqual((await self.client.post('/api/network/first/complete')).status, 200)
        await asyncio.sleep(.25)
        for ws in pair:
            await ws.send_json({'type': 'ping'})
            self.assert_idle(await ws.receive_json(timeout=2))
        for ws in other_pair:
            await ws.send_json({'type': 'ping'})
            state = await ws.receive_json(timeout=2)
            self.assertEqual(state['file'], other_source)
            self.assertFalse(state['paused'])
            self.assertGreater(state['position'], other_playing['position'])
        _, hello, _ = await self.connect('AB')
        self.assertEqual(hello['memories'], [started['memory']])

    async def test_late_network_reclamation_and_repeated_completion_keep_new_selection(self):
        source = await self.resolve('first')
        (self.data / 'media' / 'next.mp4').write_bytes(b'next fixture')
        pair = await self.pair()
        await self.act(pair, type='control', file=source, position=12, paused=False)
        await asyncio.sleep(.25)
        released, resume = asyncio.Event(), asyncio.Event()
        release = self.engine.release

        async def delayed_release(source_id):
            await release(source_id)
            released.set()
            # Hold cleanup at the existing network Seam while the host selects a new film.
            await resume.wait()

        try:
            with patch.object(self.engine, 'release', side_effect=delayed_release):
                response = await self.client.post('/api/network/first/complete')
                self.assertEqual(response.status, 200)
                await asyncio.wait_for(released.wait(), timeout=2)
                await self.act(pair, type='control', file='next.mp4', position=20, paused=False)
                await self.act(pair, type='rate', file='next.mp4', rate=1.5)
                playing = await self.act(pair, type='boost', file='next.mp4', active=True)
        finally:
            resume.set()
        for _ in range(2):
            self.assertEqual((await self.client.post('/api/network/first/complete')).status, 200)
        self.assertEqual((await self.client.get('/api/network/first/source')).status, 410)
        await asyncio.sleep(.25)
        for ws in pair:
            await ws.send_json({'type': 'ping'})
            state = await ws.receive_json(timeout=2)
            self.assertEqual(state['file'], 'next.mp4')
            self.assertFalse(state['paused'])
            self.assertTrue(state['boosting'])
            self.assertEqual(state['base_rate'], 1.5)
            self.assertEqual(state['playback_rate'], 2)
            self.assertGreater(state['position'], playing['position'])
            self.assertEqual(state['host'], playing['host'])
            self.assertEqual(state['members'], playing['members'])

    async def test_late_and_repeated_local_deletion_does_not_stop_new_selection(self):
        media = self.data / 'media'
        (media / 'first.mp4').write_bytes(b'first fixture')
        (media / 'next.mp4').write_bytes(b'next fixture')
        pair = await self.pair()
        await self.act(pair, type='control', file='first.mp4', position=12, paused=False)
        await self.act(pair, type='control', file='next.mp4', position=20, paused=False)
        await self.act(pair, type='rate', file='next.mp4', rate=1.5)
        playing = await self.act(pair, type='boost', file='next.mp4', active=True)
        self.assertEqual((await self.client.delete('/api/library/first.mp4')).status, 200)
        unchanged = await self.receive_pair(pair)
        self.assertEqual(unchanged['library_version'], playing['library_version'] + 1)
        self.assertEqual((await self.client.delete('/api/library/first.mp4')).status, 404)
        for ws in pair:
            await ws.send_json({'type': 'ping'})
            state = await ws.receive_json(timeout=2)
            self.assertEqual(state['file'], 'next.mp4')
            self.assertFalse(state['paused'])
            self.assertTrue(state['boosting'])
            self.assertEqual(state['base_rate'], 1.5)
            self.assertEqual(state['playback_rate'], 2)
            self.assertGreater(state['position'], playing['position'])
            self.assertEqual(state['host'], playing['host'])
            self.assertEqual(state['members'], playing['members'])

    async def test_local_deletion_stops_members_but_only_refreshes_other_room_library(self):
        media = self.data / 'media'
        (media / 'first.mp4').write_bytes(b'first fixture')
        (media / 'other.mp4').write_bytes(b'other fixture')
        pair = await self.pair()
        other_pair = await self.pair('CD')
        other_playing = await self.act(
            other_pair, type='control', file='other.mp4', position=7, paused=False)
        started = await self.act(
            pair, type='control', file='first.mp4', position=12, paused=False)
        await self.act(pair, type='rate', file='first.mp4', rate=1.5)
        playing = await self.act(pair, type='boost', file='first.mp4', active=True)
        self.assertTrue(playing['boosting'])
        response = await self.client.delete('/api/library/first.mp4')
        self.assertEqual(response.status, 200)
        stopped = await self.receive_pair(pair)
        self.assert_idle(stopped)
        self.assertEqual(stopped['host'], playing['host'])
        self.assertEqual(stopped['members'], playing['members'])
        self.assertEqual(stopped['online'], 2)
        self.assertEqual(stopped['library_version'], playing['library_version'] + 1)
        other = await self.receive_pair(other_pair)
        self.assertEqual(other['library_version'], other_playing['library_version'] + 1)
        self.assertEqual(other['file'], 'other.mp4')
        self.assertFalse(other['paused'])
        self.assertGreater(other['position'], other_playing['position'])
        library = await (await self.client.get('/api/library')).json()
        self.assertEqual([item['name'] for item in library['files']], ['other.mp4'])
        self.assertEqual((await self.client.get('/media/first.mp4')).status, 404)
        self.assertEqual((await self.client.delete('/api/library/first.mp4')).status, 404)
        await asyncio.sleep(.25)
        for ws in pair:
            await ws.send_json({'type': 'ping'})
            self.assert_idle(await ws.receive_json(timeout=2))
        for ws in other_pair:
            await ws.send_json({'type': 'ping'})
            later = await ws.receive_json(timeout=2)
            self.assertEqual(later['file'], 'other.mp4')
            self.assertFalse(later['paused'])
            self.assertGreater(later['position'], other['position'])
        _, hello, _ = await self.connect('AB')
        self.assertEqual(hello['memories'], [started['memory']])
