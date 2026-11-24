import unittest
from unittest.mock import patch
from cinema.server import Room
class BoostTimelineTests(unittest.TestCase):
 def test_host_hold_release_and_timeout_keep_continuous_position(self):
  with patch('cinema.server.time.monotonic',return_value=100) as clock:
   r=Room();r.host='host';self.assertTrue(r.update('host',{'file':'clip.mp4','position':10,'paused':False},{'clip.mp4'}))
   self.assertTrue(r.set_boost('host',True,'clip.mp4'));clock.return_value=101.5;s=r.snapshot();self.assertEqual(s['playback_rate'],2);self.assertAlmostEqual(s['position'],13)
   self.assertFalse(r.set_boost('guest',False,'clip.mp4'));self.assertTrue(r.set_boost('host',False,'clip.mp4'));clock.return_value=102.5;self.assertAlmostEqual(r.snapshot()['position'],14)
   self.assertTrue(r.set_boost('host',True,'clip.mp4'));clock.return_value=106.5;s=r.snapshot();self.assertEqual(s['playback_rate'],1);self.assertAlmostEqual(s['position'],21)
   self.assertFalse(r.set_boost('host',1,'clip.mp4'));self.assertFalse(r.set_boost('host',True,'other.mp4'))

class DanmakuPersistenceTests(unittest.TestCase):
 def test_plain_text_comments_persist_per_movie_and_delete(self):
  import tempfile
  from pathlib import Path
  from cinema.danmaku import DanmakuStore
  with tempfile.TemporaryDirectory() as tmp:
   store=DanmakuStore(Path(tmp));a=store.add('clip.mp4','<img src=x onerror=alert(1)>  你好',12.5)
   self.assertEqual(a['time'],12.5);self.assertIn('<img',a['text']);self.assertEqual(DanmakuStore(Path(tmp)).list('clip.mp4'),[a]);self.assertEqual(store.list('other.mp4'),[])
   for text in ['', ' '*5, 'x'*121, 2]:
    with self.assertRaises(ValueError):store.add('clip.mp4',text,1)
   store.remove('clip.mp4');self.assertEqual(store.list('clip.mp4'),[])

class InteractiveWebSocketTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  import tempfile
  from pathlib import Path
  from aiohttp.test_utils import TestClient,TestServer
  from cinema.server import create_app
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.client=TestClient(TestServer(create_app(self.root,'interactive-test-123456',secure=False)));await self.client.start_server();(self.root/'media/clip.mp4').write_bytes(b'video-fixture')
 async def asyncTearDown(self):
  await self.client.close();self.tmp.cleanup()
 async def peers(self):
  await self.client.post('/api/login',json={'password':'interactive-test-123456'});a=await self.client.ws_connect('/ws');ha=await a.receive_json();await a.receive_json();b=await self.client.ws_connect('/ws');hb=await b.receive_json();await b.receive_json();await a.receive_json();return a,b,ha,hb
 async def control(self,a,b):
  await a.send_json({'type':'control','file':'clip.mp4','position':3,'paused':False});await a.receive_json();await b.receive_json()
 async def test_two_viewers_boost_release_guest_rejection_and_handoff(self):
  a,b,ha,hb=await self.peers();await self.control(a,b)
  await b.send_json({'type':'boost','file':'clip.mp4','active':True});await b.send_json({'type':'ping'});self.assertEqual((await b.receive_json())['playback_rate'],1)
  await a.send_json({'type':'boost','file':'clip.mp4','active':True});self.assertEqual((await a.receive_json())['playback_rate'],2);self.assertEqual((await b.receive_json())['playback_rate'],2)
  await a.send_json({'type':'boost','file':'clip.mp4','active':False});self.assertEqual((await a.receive_json())['playback_rate'],1);self.assertEqual((await b.receive_json())['playback_rate'],1)
  await a.send_json({'type':'boost','file':'clip.mp4','active':True});await a.receive_json();await b.receive_json();await a.close();handoff=await b.receive_json();self.assertEqual(handoff['host'],hb['id']);self.assertEqual(handoff['playback_rate'],1);await b.close()
 async def test_watchdog_restores_both_even_if_snapshot_already_expired(self):
  import asyncio
  a,b,_,_=await self.peers();await self.control(a,b);await a.send_json({'type':'boost','file':'clip.mp4','active':True});await a.receive_json();await b.receive_json()
  await asyncio.sleep(3.1);await b.send_json({'type':'ping'})
  self.assertEqual((await asyncio.wait_for(a.receive_json(),1.0))['playback_rate'],1);self.assertEqual((await asyncio.wait_for(b.receive_json(),1.0))['playback_rate'],1)
  await a.close();await b.close()
 async def test_private_persisted_broadcast_plaintext_rate_limit_and_delete(self):
  self.assertEqual((await self.client.get('/api/danmaku/clip.mp4')).status,401)
  a,b,_,_=await self.peers();await self.control(a,b);text='<img src=x onerror=alert(1)> 你好'
  await b.send_json({'type':'danmaku','file':'clip.mp4','text':text});ea,eb=await a.receive_json(),await b.receive_json();self.assertEqual(ea,eb);self.assertEqual(ea['type'],'danmaku');self.assertEqual(ea['comment']['text'],text);self.assertGreaterEqual(ea['comment']['time'],3)
  history=await self.client.get('/api/danmaku/clip.mp4');self.assertEqual(history.status,200);self.assertEqual((await history.json())['comments'],[ea['comment']])
  await b.send_json({'type':'danmaku','file':'clip.mp4','text':'too fast'});self.assertEqual((await b.receive_json())['type'],'error')
  self.assertEqual((await self.client.get('/api/danmaku/missing.mp4')).status,404)
  self.assertEqual((await self.client.delete('/api/library/clip.mp4')).status,200);self.assertEqual((await self.client.get('/api/danmaku/clip.mp4')).status,404)
  from cinema.danmaku import DanmakuStore
  self.assertEqual(DanmakuStore(self.root).list('clip.mp4'),[]);await a.close();await b.close()
