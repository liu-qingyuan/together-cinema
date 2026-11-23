import sys,tempfile,unittest
from pathlib import Path
from aiohttp import web
from aiohttp.test_utils import TestClient,TestServer
from server import create_app
class Rooms(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.data=Path(self.tmp.name);self.client=TestClient(TestServer(create_app(self.data,'fixture-pass-123',secure=False)));await self.client.start_server();r=await self.client.post('/api/login',json={'password':'fixture-pass-123'});self.assertEqual(r.status,200)
 async def asyncTearDown(self):await self.client.close();self.tmp.cleanup()
 async def connect(self,code):
  ws=await self.client.ws_connect('/ws?room='+code+'&name=Tester');hello=await ws.receive_json();state=await ws.receive_json();return ws,hello,state
 async def test_distinct_short_rooms(self):
  a,ha,sa=await self.connect('AB');b,hb,sb=await self.connect('02');self.assertEqual(sa.get('room'),'AB');self.assertEqual(sb['room'],'02');self.assertEqual(sb['online'],1);await a.close();await b.close()
if __name__=='__main__':unittest.main()

class RoomCommunication(Rooms):
 async def event(self,ws,kind):
  import asyncio
  for _ in range(30):
   row=await asyncio.wait_for(ws.receive_json(),2)
   if row['type']==kind:return row
  self.fail('missing '+kind)
 async def test_chat_and_voice_are_room_scoped(self):
  a,ha,_=await self.connect('AB');b,hb,_=await self.connect('AB');c,hc,_=await self.connect('CD')
  await a.send_json({'type':'chat','text':'<img onerror=bad()> hello'})
  ea=await self.event(a,'chat');eb=await self.event(b,'chat');self.assertEqual(ea,eb)
  await c.send_json({'type':'ping'});self.assertEqual((await self.event(c,'state'))['online'],1)
  for w in [a,b,c]:await w.send_json({'type':'voice_join'});await self.event(w,'state')
  await a.send_json({'type':'signal','to':hb['id'],'signal':{'description':{'type':'offer','sdp':'test-opus'}}});sig=await self.event(b,'signal');self.assertEqual(sig['sender'],ha['id'])
  await a.send_json({'type':'signal','to':hc['id'],'signal':{'description':{'type':'offer','sdp':'MUST NOT CROSS ROOM'}}});await c.send_json({'type':'ping'});row=await c.receive_json();self.assertEqual(row['type'],'state')
  await b.send_json({'type':'voice_leave'});await self.event(b,'state');await a.send_json({'type':'signal','to':hb['id'],'signal':{'description':{'type':'offer','sdp':'LEFT MUST NOT RECEIVE'}}});await b.send_json({'type':'ping'});row=await self.event(b,'state');self.assertFalse(next(m for m in row['members'] if m['id']==hb['id'])['voice'])
  await a.close();await b.close();await c.close()
 async def test_short_code_validation_and_private_ice(self):
  from aiohttp import WSServerHandshakeError
  from unittest.mock import patch
  import base64,hashlib,hmac,os
  for code in ['A','x-x','TOOLONGROOM']:
   with self.assertRaises(WSServerHandshakeError):await self.client.ws_connect('/ws?room='+code)
  with patch.dict(os.environ,{'WATCH_TURN_SECRET':'test-secret','WATCH_TURN_URLS':'turn:fixture:3478?transport=udp'}):
   r=await self.client.get('/api/voice-config');self.assertEqual(r.status,200);self.assertIn('no-store',r.headers['Cache-Control']);config=await r.json();ice=config['iceServers'][0];expected=base64.b64encode(hmac.new(b'test-secret',ice['username'].encode(),hashlib.sha1).digest()).decode();self.assertEqual(ice['credential'],expected)
  await self.client.post('/api/logout');self.assertEqual((await self.client.get('/api/voice-config')).status,401)
 async def test_room_danmaku_legacy_and_delete(self):
  from danmaku import DanmakuStore
  store=DanmakuStore(self.data);store.add('fixture.mp4','legacy',1);store.add('fixture.mp4','AB only',2,'AB');self.assertEqual(store.list('fixture.mp4')[0]['text'],'legacy');self.assertEqual(store.list('fixture.mp4','AB')[0]['text'],'AB only');self.assertEqual(store.list('fixture.mp4','CD'),[]);store.remove('fixture.mp4');self.assertFalse(store.list('fixture.mp4'));self.assertFalse(store.list('fixture.mp4','AB'))
 async def test_room_file_delete_clears_all_rooms(self):
  (self.data/'media/fixture.mp4').write_bytes(b'fixture');a,_,_=await self.connect('AB');b,_,_=await self.connect('CD')
  for w in [a,b]:await w.send_json({'type':'control','file':'fixture.mp4','position':3,'paused':True});await self.event(w,'state')
  r=await self.client.delete('/api/library/fixture.mp4');self.assertEqual(r.status,200)
  for w in [a,b]:self.assertIsNone((await self.event(w,'state'))['file']);await w.close()

class RoomRate(unittest.TestCase):
 def test_rate_and_boost_resume_selected_base_rate(self):
  from server import Room
  from unittest.mock import patch
  with patch('server.time.monotonic',return_value=100) as clock:
   r=Room();r.host='h';r.update('h',{'file':'f','position':0,'paused':False},{'f'});self.assertFalse(r.set_rate('other',1.5,'f'));self.assertFalse(r.set_rate('h',True,'f'));self.assertTrue(r.set_rate('h',1.5,'f'));clock.return_value=102;self.assertEqual(r.snapshot()['position'],3);r.set_boost('h',True,'f');clock.return_value=103;r.set_boost('h',False,'f');self.assertEqual(r.snapshot()['playback_rate'],1.5);self.assertEqual(r.snapshot()['position'],5);r.update('h',{'file':'f','position':5,'paused':True},{'f'});self.assertEqual(r.snapshot()['playback_rate'],1.5)

class Checkpoint(Rooms):
 async def test_checkpoint_preserves_progress_once(self):
  import json,time
  (self.data/'media/fixture.mp4').write_bytes(b'video');p=self.data/'room-checkpoint.json';p.write_text(json.dumps({'file':'fixture.mp4','position':12,'paused':False,'base_rate':1.25,'server_time':time.time()-2}))
  await self.client.close();self.client=TestClient(TestServer(create_app(self.data,'fixture-pass-123',secure=False)));await self.client.start_server();await self.client.post('/api/login',json={'password':'fixture-pass-123'});w,_,state=await self.connect('01');self.assertEqual(state['file'],'fixture.mp4');self.assertFalse(state['paused']);self.assertGreaterEqual(state['position'],14.5);self.assertEqual(state['base_rate'],1.25);self.assertFalse(p.exists());await w.close()

class WelcomeCleanup(unittest.IsolatedAsyncioTestCase):
 async def test_interrupted_welcome_releases_host_and_member(self):
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as directory:
   async with TestClient(TestServer(create_app(Path(directory),'fixture-pass-123',secure=False))) as client:
    await client.post('/api/login',json={'password':'fixture-pass-123'})
    with patch.object(web.WebSocketResponse,'send_json',side_effect=ConnectionResetError('welcome interrupted')):
     failed=await client.ws_connect('/ws?room=QA')
     await failed.receive(timeout=3)
     await failed.close()
    async with client.ws_connect('/ws?room=QA') as ws:
     hello,state=await ws.receive_json(),await ws.receive_json()
     self.assertEqual(state['online'],1)
     self.assertEqual(state['host'],hello['id'])
