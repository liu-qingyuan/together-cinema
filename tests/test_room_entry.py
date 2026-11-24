import tempfile,unittest
from pathlib import Path
from aiohttp import FormData
from aiohttp.test_utils import TestClient,TestServer
from server import create_app
class RoomEntry(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.data=Path(self.tmp.name);self.app=TestServer(create_app(self.data,'internal-signing-123',secure=False));await self.app.start_server();self.client=TestClient(self.app);await self.client.start_server()
 async def asyncTearDown(self):await self.client.close();self.tmp.cleanup()
 async def test_room_code_is_the_only_new_entry_credential(self):
  r=await self.client.post('/api/login',json={'room':'ab'});self.assertEqual(r.status,200);self.assertEqual((await r.json())['room'],'AB');self.assertTrue(r.cookies['watch_session']['httponly']);self.assertEqual((await self.client.get('/api/library')).status,200)
  ws=await self.client.ws_connect('/ws?room=AB');await ws.receive_json();self.assertEqual((await ws.receive_json())['room'],'AB');await ws.close()
 async def test_room_validation_and_origin_remain(self):
  for code in ['A','TOOLONG123',None,1,'中文']:
   r=await self.client.post('/api/login',json={'room':code});self.assertEqual(r.status,400)
  self.assertEqual((await self.client.get('/api/library')).status,401)
  self.assertEqual((await self.client.post('/api/login',json={'room':'AB'},headers={'Origin':'https://evil.invalid'})).status,403)
 async def test_every_room_entry_can_upload_share_and_delete(self):
  await self.client.post('/api/login',json={'room':'AB'});form=FormData();form.add_field('video',b'room-entry-fixture',filename='shared.mp4',content_type='video/mp4');r=await self.client.post('/api/upload',data=form);self.assertEqual(r.status,201)
  await self.client.post('/api/logout');await self.client.post('/api/login',json={'room':'CD'});files=(await (await self.client.get('/api/library')).json())['files'];self.assertEqual(len(files),1);name=files[0]['name'];self.assertEqual((await self.client.get('/media/'+name)).status,200);self.assertEqual((await self.client.delete('/api/library/'+name)).status,200);self.assertFalse((await (await self.client.get('/api/library')).json())['files'])
 async def test_legacy_session_compatibility(self):
  self.assertEqual((await self.client.post('/api/login',json={'password':'internal-signing-123'})).status,200)
