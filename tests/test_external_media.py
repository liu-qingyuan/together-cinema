import unittest
class ResourceLifecycle(unittest.TestCase):
 def test_import_resource_bounded_media_module(self):
  from external_media import MAX_SOURCES,MAX_MANIFEST,CHUNK_SIZE
  self.assertLessEqual(MAX_SOURCES,32);self.assertLessEqual(MAX_MANIFEST,1048576);self.assertLessEqual(CHUNK_SIZE,65536)

import asyncio,tempfile,json,sys,os,socket,gc,tracemalloc
from pathlib import Path
from unittest.mock import patch
from aiohttp import web
from aiohttp.test_utils import TestClient,TestServer
from external_media import ExternalMedia,Source,PublicResolver,public_url
from extractor import Extractor
class URLSafety(unittest.IsolatedAsyncioTestCase):
 async def test_private_schemes_addresses_redirect_policy(self):
  for url in ['http://example.com/v.mp4','https://127.0.0.1/a','https://169.254.169.254/a','https://[::1]/a','https://u:p@example.com/a','https://example.com:8443/a','https://localhost/a']:
   with self.assertRaises(ValueError):public_url(url)
  with patch('asyncio.base_events.BaseEventLoop.getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('10.0.0.1',443))]):
   with self.assertRaises(OSError):await PublicResolver().resolve('example.com')
class ExtractorLifecycle(unittest.IsolatedAsyncioTestCase):
 async def test_repeated_timeout_cancel_and_no_temp_or_children(self):
  with tempfile.TemporaryDirectory() as root:
   engine=Extractor([sys.executable,'-c','import time;time.sleep(10)'],timeout=.04,temp_root=root)
   for _ in range(8):
    with self.assertRaises(RuntimeError):await engine.resolve('https://youtu.be/aqz-KE-bpKQ')
    self.assertFalse(engine.busy);self.assertIsNone(engine.pid);self.assertEqual(list(Path(root).iterdir()),[])
   engine.timeout=10;task=asyncio.create_task(engine.resolve('https://youtu.be/aqz-KE-bpKQ'))
   while engine.pid is None:await asyncio.sleep(.005)
   pid=engine.pid;task.cancel()
   with self.assertRaises(asyncio.CancelledError):await task
   self.assertFalse(engine.busy);self.assertEqual(list(Path(root).iterdir()),[])
   with self.assertRaises(ProcessLookupError):os.kill(pid,0)
 async def test_selection_hls_unknown_audio_codec_is_not_dropped(self):
  choices=Extractor.candidates({'title':'fixture','formats':[{'url':'https://example.com/audio.m3u8','vcodec':'none','acodec':None,'ext':'mp4','protocol':'m3u8_native'},{'url':'https://example.com/video.m3u8','vcodec':'avc1.4D401F','acodec':'none','height':360,'protocol':'m3u8_native'}]});self.assertEqual(len(choices),1);self.assertTrue(choices[0]['audio_url'])
class ResourceSweep(unittest.IsolatedAsyncioTestCase):
 async def test_repeated_registration_release_memory_is_bounded(self):
  media=ExternalMedia('http://extractor:8081','fixture');tracemalloc.start();gc.collect();before=tracemalloc.get_traced_memory()[0]
  for cycle in range(100):
   for i in range(16):media.sources[str(i)]=Source(str(i),{'url':'https://example.com/v.mp4','kind':'mp4','title':'test'},'relay','https://example.com/')
   await media.sweep({'net:0'});self.assertTrue(media.sources['0'].was_active);await media.sweep(set())
   for key in list(media.sources):await media.release(key)
  gc.collect();after=tracemalloc.get_traced_memory()[0];tracemalloc.stop();self.assertLess(after-before,200000);self.assertEqual(media.stats()['sources'],0);self.assertEqual(media.stats()['video_disk_cache_bytes'],0)
 async def test_signatures_and_manifest_child_rewrite(self):
  media=ExternalMedia('http://extractor:8081','fixture');source=Source('test',{'url':'https://example.com/v.m3u8','kind':'hls'},'relay','https://example.com/');text=media.rewrite(source,b'#EXTM3U\n#EXT-X-MAP:URI="init.mp4"\nseg.ts\n','https://example.com/path/v.m3u8');self.assertIn('/api/network/test/play?u=',text);self.assertNotIn('\nseg.ts',text)
  with self.assertRaises(ValueError):media.rewrite(source,b'#EXTM3U\nhttps://127.0.0.1/private\n','https://example.com/a')

class RelayHTTP(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.open_upstream=0
  async def fixture(request):
   if request.path.endswith('.m3u8'):return web.Response(text='#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:2,\nseg.ts\n#EXT-X-ENDLIST\n',content_type='application/vnd.apple.mpegurl')
   if request.path=='/slow.mp4':
    self.open_upstream+=1;response=web.StreamResponse(headers={'Content-Type':'video/mp4'});await response.prepare(request)
    try:
     for _ in range(100):await response.write(b'x'*32768);await asyncio.sleep(.02)
    except (ConnectionError,asyncio.CancelledError):pass
    finally:self.open_upstream-=1
    return response
   body=b'0123456789';r=request.headers.get('Range')
   if r=='bytes=2-5':return web.Response(body=body[2:6],status=206,headers={'Content-Range':'bytes 2-5/10','Accept-Ranges':'bytes'},content_type='video/mp4')
   return web.Response(body=body,content_type='video/mp4')
  app=web.Application();app.router.add_get('/{name}',fixture);self.upstream=TestServer(app);await self.upstream.start_server();outer=self
  class FixtureMedia(ExternalMedia):
   async def request(this,url,method='GET',headers=None):
    public_url(url);response=await this.session.request(method,outer.upstream.make_url(urlsplit(url).path),headers=headers,allow_redirects=False)
    from yarl import URL
    response._url=URL(url);return response
  from urllib.parse import urlsplit
  self.media=FixtureMedia('http://unused','fixture');await self.media.start();app=web.Application();app.router.add_get('/api/network/{source_id}/play',self.media.play);self.client=TestClient(TestServer(app));await self.client.start_server()
 async def asyncTearDown(self):await self.media.close();await self.client.close();await self.upstream.close()
 async def test_range_stream_is_not_buffered_or_cached(self):
  self.media.sources['id']=Source('id',{'url':'https://public.example/v.mp4','kind':'mp4'},'relay','https://public.example/')
  r=await self.client.get('/api/network/id/play',headers={'Range':'bytes=2-5'});self.assertEqual(r.status,206);self.assertEqual(await r.read(),b'2345');self.assertEqual(r.headers['Content-Range'],'bytes 2-5/10');self.assertEqual(self.media.streams,0);self.assertEqual(self.media.stats()['video_disk_cache_bytes'],0)
 async def test_signed_playlist_and_tamper_rejection(self):
  self.media.sources['id']=Source('id',{'url':'https://public.example/v.m3u8','kind':'hls'},'relay','https://public.example/')
  r=await self.client.get('/api/network/id/play');text=await r.text();link=next(x for x in text.splitlines() if x.startswith('/api/'));self.assertEqual((await self.client.get(link)).status,200);self.assertEqual((await self.client.get(link+'X')).status,403)
 async def test_client_disconnect_and_release_close_upstream(self):
  self.media.sources['id']=Source('id',{'url':'https://public.example/slow.mp4','kind':'mp4'},'relay','https://public.example/')
  r=await self.client.get('/api/network/id/play');await r.content.read(32768);r.close()
  for _ in range(100):
   if not self.media.streams and not self.open_upstream:break
   await asyncio.sleep(.02)
  self.assertEqual(self.media.streams,0);self.assertEqual(self.open_upstream,0);self.assertEqual(self.media.sources['id'].tasks,set());await self.media.release('id');self.assertFalse(self.media.sources)

class NetworkRoomHTTP(unittest.IsolatedAsyncioTestCase):
 async def test_room_entry_auth_sync_and_end_cleanup(self):
  from server import create_app
  class FixtureMedia(ExternalMedia):
   async def resolve(this,url,mode):
    public_url(url);this.sources['fixture']=Source('fixture',{'url':url,'title':'fixture','kind':'mp4','duration':10},mode,url)
    return [this.describe('fixture')]
  with tempfile.TemporaryDirectory() as root:
   engine=FixtureMedia('http://unused','test')
   with patch('server.ExternalMedia',return_value=engine):app=create_app(Path(root),'test-network-123',secure=False)
   async with TestClient(TestServer(app)) as client:
    self.assertEqual((await client.get('/api/network/stats')).status,401)
    await client.post('/api/login',json={'room':'AB'})
    self.assertEqual((await client.post('/api/network/resolve',json={'url':'https://public.example/v.mp4'},headers={'Origin':'https://evil.invalid'})).status,403)
    r=await client.post('/api/network/resolve',json={'url':'https://public.example/v.mp4','mode':'relay'});self.assertEqual(r.status,200);self.assertEqual((await r.json())['choices'][0]['file'],'net:fixture')
    ws=await client.ws_connect('/ws?room=AB');await ws.receive_json();await ws.receive_json()
    await ws.send_json({'type':'control','file':'net:fixture','position':9.9,'paused':False})
    state=await ws.receive_json();self.assertEqual(state['file'],'net:fixture')
    await asyncio.sleep(.25)
    self.assertEqual((await client.post('/api/network/fixture/complete')).status,200)
    state=await ws.receive_json(timeout=2);self.assertIsNone(state['file'])
    self.assertEqual((await (await client.get('/api/network/stats')).json())['sources'],0)
    self.assertEqual((await client.get('/api/network/fixture/source')).status,410)
    await ws.close()
   self.assertIsNone(engine.session);self.assertIsNone(engine.internal)

class SignedURLTransport(unittest.IsolatedAsyncioTestCase):
 async def test_signed_path_is_not_canonicalized(self):
  from unittest.mock import AsyncMock
  from types import SimpleNamespace
  url='https://example.com/v/source/youtube%3Bdur%3D1/sig/A%3D%3D/index.m3u8'
  response=SimpleNamespace(status=200)
  media=ExternalMedia('http://unused','test');media.session=SimpleNamespace(request=AsyncMock(return_value=response))
  self.assertIs(await media.request(url),response)
  self.assertEqual(str(media.session.request.call_args.args[1]),url)

class OrphanLifecycle(unittest.IsolatedAsyncioTestCase):
 async def test_parent_exit_still_terminates_descendants(self):
  import subprocess,signal
  with tempfile.TemporaryDirectory() as root:
   pidfile=Path(root)/'pid';temporary=Path(root)/'tmp';temporary.mkdir()
   script="import subprocess,sys;from pathlib import Path;p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)']);Path("+repr(str(pidfile))+").write_text(str(p.pid))"
   engine=Extractor([sys.executable,'-c',script],timeout=.15,temp_root=str(temporary))
   pid=None
   try:
    with self.assertRaises(RuntimeError):await engine.resolve('https://youtu.be/aqz-KE-bpKQ')
    pid=int(pidfile.read_text())
    def running():
     if sys.platform=='linux':
      try:state=Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()[0]
      except FileNotFoundError:return False
      return state!='Z'
     r=subprocess.run(['ps','-o','stat=','-p',str(pid)],capture_output=True,text=True)
     return bool(r.stdout.strip()) and not r.stdout.strip().startswith('Z')
    for _ in range(50):
     if not running():break
     await asyncio.sleep(.01)
    self.assertFalse(running(),'descendant survived parent exit and timeout')
    self.assertEqual(list(temporary.iterdir()),[]);self.assertFalse(engine.busy)
   finally:
    if pid:
     try:os.kill(pid,signal.SIGKILL)
     except ProcessLookupError:pass
