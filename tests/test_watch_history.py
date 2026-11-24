import tempfile
import unittest
from types import SimpleNamespace
from cinema.watch_history import WatchHistory, film_title


class ScreeningLedger(unittest.TestCase):
    def test_bounded_and_durable(self):
        with tempfile.TemporaryDirectory() as d:
            store = WatchHistory(d)
            store.per_room, store.total = 3, 5
            for room in ('AB', 'CD'):
                for n in range(5):
                    store.record(room, str(n))
            reopened = WatchHistory(d)
            self.assertEqual([r['title'] for r in reopened.list('AB')], ['4','3'])
            self.assertEqual([r['title'] for r in reopened.list('CD')], ['4','3','2'])
            self.assertEqual(reopened.list('ZZ'), [])

    def test_titles_not_media_addresses(self):
        network = SimpleNamespace(sources={'id':SimpleNamespace(info={'title':'雪山之夜','url':'https://example.invalid/private'})})
        self.assertEqual(film_title('abcdef123456-盛夏晴空.mp4',network),'盛夏晴空')
        self.assertEqual(film_title('net:id',network),'雪山之夜')
        network.sources['id'].info['title'] = 'https://example.invalid/?token=private'
        self.assertEqual(film_title('net:id',network),'网络影片')


class ScreeningEvents(unittest.IsolatedAsyncioTestCase):
    async def test_select_pause_seek_resume_then_rewatch(self):
        from aiohttp.test_utils import TestClient, TestServer
        from cinema.server import create_app
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            async with TestClient(TestServer(create_app(d, 'fixture-pass-123', False))) as client:
                (Path(d)/'media/night.mp4').touch()
                await client.post('/api/login',json={'password':'fixture-pass-123'})
                ws = await client.ws_connect('/ws?room=JK')
                self.assertEqual((await ws.receive_json())['memories'], [])
                await ws.receive_json()  # initial state
                for paused,pos,record in [(True,0,False),(False,0,True),(True,1,False),(False,1,False),(False,4,False)]:
                    await ws.send_json(dict(type='control',file='night.mp4',position=pos,paused=paused))
                    state = await ws.receive_json()
                    self.assertEqual('memory' in state, record)
                await ws.close()
                ws = await client.ws_connect('/ws?room=JK')
                self.assertEqual([r['title'] for r in (await ws.receive_json())['memories']], ['night'])
                await ws.receive_json()
                await ws.send_json(dict(type='control',file='night.mp4',position=0,paused=False))
                self.assertEqual((await ws.receive_json())['memory']['title'],'night')
                await ws.close()
