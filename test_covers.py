import io
import tempfile
import unittest
from pathlib import Path

from unittest.mock import patch

from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

from server import create_app


def image_bytes(color='teal'):
    output = io.BytesIO()
    Image.new('RGB', (320, 180), color).save(output, 'PNG')
    return output.getvalue()


class CoverTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.client = TestClient(TestServer(create_app(self.tmp.name, 'cover-fixture-password', secure=False)))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.tmp.cleanup()

    async def member(self):
        self.assertEqual((await self.client.post('/api/login', json={'room': 'CV'})).status, 200)
        ws = await self.client.ws_connect('/ws?room=CV')
        hello = await ws.receive_json()
        await ws.receive_json()
        return ws, {'X-Room-Member': hello['member_token']}

    async def upload(self, headers, content=None):
        body = FormData()
        body.add_field('cover', io.BytesIO(image_bytes() if content is None else content),
                       filename='my-cover.png', content_type='image/png')
        return await self.client.post('/api/covers', data=body, headers=headers)

    async def test_members_upload_and_visitors_read_shared_current_cover(self):
        response = await self.client.get('/api/covers')
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())['current'], 'sky')
        self.assertEqual((await self.upload({})).status, 401)
        # A login cookie alone is not evidence of active room membership.
        await self.client.post('/api/login', json={'room': 'CV'})
        self.assertEqual((await self.upload({})).status, 403)
        ws, headers = await self.member()
        response = await self.upload(headers)
        self.assertEqual(response.status, 201, await response.text())
        catalog = await response.json()
        current = next(item for item in catalog['covers'] if item['id'] == catalog['current'])
        self.assertFalse(current['builtin'])
        async with TestClient(TestServer(create_app(self.tmp.name, 'cover-fixture-password', secure=False))) as visitor:
            self.assertEqual((await (await visitor.get('/api/covers')).json())['current'], current['id'])
            response = await visitor.get(current['desktop'])
            self.assertEqual(response.status, 200)
            self.assertEqual(response.content_type, 'image/webp')
            with Image.open(io.BytesIO(await response.read())) as image:
                self.assertEqual(image.size, (320, 180))
        await ws.close()

    async def test_failed_upload_preserves_current_and_cleans_source_and_variants(self):
        ws, headers = await self.member()
        previous = await (await self.upload(headers)).json()
        root = Path(self.tmp.name) / 'covers'
        before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
        for content in [b'not-an-image', b'', image_bytes()[:40], b'x' * (8 * 1024**2 + 1)]:
            response = await self.upload(headers, content)
            self.assertIn(response.status, (400, 413), await response.text())
            self.assertEqual(await (await self.client.get('/api/covers')).json(), previous)
            self.assertEqual({str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}, before)
        class FullDisk:
            f_bavail = 0
            f_frsize = 4096
        with patch('covers.os.statvfs', return_value=FullDisk()):
            self.assertEqual((await self.upload(headers)).status, 507)
        # A failure after derivative generation/publication must roll back too.
        replace = Path.replace
        def cannot_publish_index(path, target):
            if path.name == '.index.tmp':
                raise OSError('injected disk write failure')
            return replace(path, target)
        with patch.object(Path, 'replace', cannot_publish_index), self.assertLogs('aiohttp.server', level='ERROR'):
            self.assertEqual((await self.upload(headers)).status, 500)
        self.assertEqual(await (await self.client.get('/api/covers')).json(), previous)
        self.assertEqual({str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}, before)
        self.assertEqual(sorted(p.name for p in root.iterdir()), sorted(['index.json', previous['current']]))
        await ws.close()

    async def test_every_write_requires_live_private_membership_and_same_origin(self):
        ws, headers = await self.member()
        # Public member IDs in room state are not write credentials.
        await ws.send_json({'type': 'ping'})
        state = await ws.receive_json()
        forged = {'X-Room-Member': state['host']}
        for credentials in [{}, forged, dict(headers, Origin='https://evil.example')]:
            self.assertEqual((await self.upload(credentials)).status, 403)
            self.assertEqual((await self.client.put('/api/covers/current', json={'id': 'galaxy'}, headers=credentials)).status, 403)
            self.assertEqual((await self.client.delete('/api/covers/sky', headers=credentials)).status, 403)
        # Closing the room connection revokes the token even with a valid login cookie.
        await ws.close()
        self.assertEqual((await self.upload(headers)).status, 403)
        self.assertEqual((await self.client.put('/api/covers/current', json={'id': 'galaxy'}, headers=headers)).status, 403)
        self.assertEqual((await self.client.delete('/api/covers/sky', headers=headers)).status, 403)
        self.assertEqual((await (await self.client.get('/api/covers')).json())['current'], 'sky')

    async def test_covers_and_room_media_have_independent_lifecycles(self):
        import asyncio
        media = Path(self.tmp.name) / 'media'
        for name in ('one.mp4', 'two.mp4'):
            (media / name).write_bytes(b'test-media')
        ws, headers = await self.member()
        await ws.send_json({'type': 'control', 'file': 'one.mp4', 'position': 5, 'paused': False})
        state = await ws.receive_json()
        ident = (await (await self.upload(headers)).json())['current']
        await self.client.delete('/api/covers/' + ident, headers=headers)
        # Cover writes must not broadcast a playback command (or a library refresh).
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(ws.receive_json(), .1)
        await ws.send_json({'type': 'ping'})
        after = await ws.receive_json()
        self.assertEqual(after['file'], 'one.mp4')
        self.assertFalse(after['paused'])
        self.assertGreater(after['position'], state['position'])
        self.assertEqual(after['library_version'], state['library_version'])
        await self.client.put('/api/covers/current', json={'id': 'galaxy'}, headers=headers)
        await ws.send_json({'type': 'control', 'file': 'two.mp4', 'position': 0, 'paused': True})
        self.assertEqual((await ws.receive_json())['file'], 'two.mp4')
        self.assertEqual((await (await self.client.get('/api/covers')).json())['current'], 'galaxy')
        await ws.close()

    async def test_select_and_delete_fall_back_only_for_current_and_release_assets(self):
        ws, headers = await self.member()
        first = (await (await self.upload(headers)).json())['current']
        second = (await (await self.upload(headers)).json())['current']
        response = await self.client.put('/api/covers/current', json={'id': first}, headers=headers)
        self.assertEqual(response.status, 200, await response.text())
        self.assertEqual((await response.json())['current'], first)
        response = await self.client.delete('/api/covers/' + second, headers=headers)
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())['current'], first)
        self.assertFalse((Path(self.tmp.name) / 'covers' / second).exists())
        response = await self.client.delete('/api/covers/' + first, headers=headers)
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())['current'], 'sky')
        root = Path(self.tmp.name) / 'covers'
        self.assertEqual([path.name for path in root.iterdir()], ['index.json'])
        self.assertEqual((await self.client.get(f'/covers/{first}/desktop.webp')).status, 404)
        self.assertEqual((await self.client.delete('/api/covers/sky', headers=headers)).status, 400)
        response = await self.client.put('/api/covers/current', json={'id': 'galaxy'}, headers=headers)
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())['current'], 'galaxy')
        await ws.close()


if __name__ == '__main__':
    unittest.main()
