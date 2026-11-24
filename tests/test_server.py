import asyncio
import io
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer
from cinema.server import Room, create_app


class RoomTests(unittest.TestCase):
    def test_only_host_controls_and_rejects_invalid_position(self):
        room = Room(); room.host = 'host'
        self.assertFalse(room.update('guest', {'file':'clip.mp4'}, {'clip.mp4'}))
        self.assertFalse(room.update('host', {'file':'clip.mp4','position':float('nan')}, {'clip.mp4'}))
        self.assertTrue(room.update('host', {'file':'clip.mp4','position':12,'paused':True}, {'clip.mp4'}))
        self.assertEqual(room.snapshot()['position'],12)


class ServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.client=TestClient(TestServer(create_app(self.tmp.name,'test-password-123456',secure=False)))
        await self.client.start_server()
        self.media=Path(self.tmp.name)/'media'
        (self.media/'clip.mp4').write_bytes(b'0123456789')

    async def asyncTearDown(self):
        await self.client.close();self.tmp.cleanup()

    async def login(self):
        r=await self.client.post('/api/login',json={'password':'test-password-123456'})
        self.assertEqual(r.status,200)

    async def test_private_library_and_media(self):
        self.assertEqual((await self.client.get('/api/library')).status,401)
        self.assertEqual((await self.client.get('/media/clip.mp4')).status,401)
        await self.login()
        r=await self.client.get('/media/clip.mp4',headers={'Range':'bytes=2-5'})
        self.assertEqual(r.status,206);self.assertEqual(await r.read(),b'2345')

    async def test_bad_login_and_cross_origin(self):
        self.assertEqual((await self.client.post('/api/login',json={'password':'bad'})).status,401)
        self.assertEqual((await self.client.post('/api/login',json={'password':'test-password-123456'},headers={'Origin':'https://evil.example'})).status,403)

    async def test_login_body_limit_logout_and_rate_limit(self):
        self.assertEqual((await self.client.post('/api/login',json={'password':'x'*5000})).status,413)
        await self.login()
        self.assertEqual((await self.client.post('/api/logout')).status,200)
        self.assertEqual((await self.client.get('/api/library')).status,401)
        for _ in range(10):
            self.assertEqual((await self.client.post('/api/login',json={'password':'wrong'})).status,401)
        self.assertEqual((await self.client.post('/api/login',json={'password':'wrong'})).status,429)

    async def test_upload_space_limit_removes_partial_file(self):
        await self.login()
        body=FormData();body.add_field('video',io.BytesIO(b'video-bytes'),filename='hello.mp4')
        class FullDisk:
            f_bavail=0
            f_frsize=4096
        with patch('cinema.server.os.statvfs',return_value=FullDisk()):
            r=await self.client.post('/api/upload',data=body)
        self.assertEqual(r.status,507)
        self.assertEqual([p.name for p in self.media.iterdir()],['clip.mp4'])

    async def test_upload_and_disallow_nonvideo(self):
        await self.login()
        body=FormData();body.add_field('video',io.BytesIO(b'video-bytes'),filename='hello.mp4')
        r=await self.client.post('/api/upload',data=body)
        self.assertEqual(r.status,201); name=(await r.json())['name']
        self.assertEqual((self.media/name).read_bytes(),b'video-bytes')
        body=FormData();body.add_field('video',io.BytesIO(b'x'),filename='attack.html')
        self.assertEqual((await self.client.post('/api/upload',data=body)).status,400)

    async def test_delete_private_video_clears_active_room(self):
        self.assertEqual((await self.client.delete('/api/library/clip.mp4')).status,401)
        await self.login()
        ws=await self.client.ws_connect('/ws');await ws.receive_json();await ws.receive_json()
        await ws.send_json({'type':'control','file':'clip.mp4','position':3,'paused':False})
        await ws.receive_json()
        r=await self.client.delete('/api/library/clip.mp4')
        self.assertEqual(r.status,200)
        self.assertFalse((self.media/'clip.mp4').exists())
        state=await ws.receive_json()
        self.assertIsNone(state['file']);self.assertTrue(state['paused'])
        self.assertEqual(state['position'],0)
        self.assertEqual((await self.client.get('/media/clip.mp4')).status,404)
        self.assertEqual((await self.client.delete('/api/library/clip.mp4')).status,404)
        await ws.close()

    async def test_delete_respects_origin_and_library_scope(self):
        await self.login()
        r=await self.client.delete('/api/library/clip.mp4',headers={'Origin':'https://evil.example'})
        self.assertEqual(r.status,403);self.assertTrue((self.media/'clip.mp4').exists())
        outside=Path(self.tmp.name)/'outside.mp4';outside.write_bytes(b'protected')
        (self.media/'alias.mp4').symlink_to(outside)
        (self.media/'.hidden.mp4').write_bytes(b'hidden')
        for name in ['alias.mp4','.hidden.mp4','outside.mp4']:
            self.assertEqual((await self.client.delete('/api/library/'+name)).status,404)
        self.assertEqual(outside.read_bytes(),b'protected')
        self.assertTrue((self.media/'.hidden.mp4').exists())

    async def test_delete_other_video_notifies_all_without_stopping_current(self):
        await self.login();(self.media/'other.mp4').write_bytes(b'other')
        a=await self.client.ws_connect('/ws');await a.receive_json();await a.receive_json()
        b=await self.client.ws_connect('/ws');await b.receive_json();await b.receive_json();await a.receive_json()
        await a.send_json({'type':'control','file':'clip.mp4','position':3,'paused':True})
        await a.receive_json();await b.receive_json()
        self.assertEqual((await self.client.delete('/api/library/other.mp4')).status,200)
        for ws in [a,b]:
            state=await ws.receive_json()
            self.assertEqual(state['file'],'clip.mp4');self.assertEqual(state['position'],3)
            self.assertEqual(state['library_version'],1)
        self.assertTrue((self.media/'clip.mp4').exists())
        await a.close();await b.close()

    async def test_websocket_sync_and_host_handoff(self):
        await self.login()
        a=await self.client.ws_connect('/ws');self.assertEqual((await a.receive_json())['type'],'hello')
        initial=await a.receive_json();first=initial['host']
        b=await self.client.ws_connect('/ws');hello=await b.receive_json();await b.receive_json();await a.receive_json()
        await a.send_json({'type':'control','file':'clip.mp4','position':17,'paused':True})
        self.assertEqual((await a.receive_json())['position'],17)
        self.assertEqual((await b.receive_json())['position'],17)
        await a.close()
        self.assertEqual((await b.receive_json())['host'],hello['id'])
        self.assertNotEqual(first,hello['id']);await b.close()


if __name__=='__main__':unittest.main()
