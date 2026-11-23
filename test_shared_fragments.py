import asyncio,unittest,time
from collections import Counter
from urllib.parse import urlsplit
from aiohttp import web
from aiohttp.test_utils import TestClient,TestServer
from yarl import URL
from external_media import ExternalMedia,Source,public_url

class SharedHTTP(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.calls=Counter();self.gate=asyncio.Event();self.gate.set();self.fail=False;self.open=0
  async def upstream(request):
   self.calls[(request.path,request.headers.get('Range'))]+=1
   if request.path.endswith('.m3u8'):return web.Response(text='#EXTM3U\n#EXTINF:4,\nsegment.ts\n#EXT-X-ENDLIST\n',content_type='application/vnd.apple.mpegurl')
   if self.fail:
    await asyncio.sleep(.04);return web.Response(status=503)
   self.open+=1
   try:
    await self.gate.wait();await asyncio.sleep(.04)
    data=b'0123456789'
    if request.path in ('/unknown.ts','/unknown-large.ts'):
     if request.path=='/unknown-large.ts':data=b'x'*(2*1024*1024+1)
     response=web.StreamResponse(headers={'Content-Type':'video/mp2t'});await response.prepare(request);await response.write(data);await response.write_eof();return response
    headers={'Content-Type':'video/mp2t'};status=200
    if request.path.startswith('/big'):data=b'x'*(2*1024*1024)
    if request.path=='/large.ts':data=b'x'*(2*1024*1024+1)
    if request.headers.get('Range')=='bytes=2-5':data=data[2:6];status=206;headers['Content-Range']='bytes 2-5/10'
    return web.Response(body=data,status=status,headers=headers)
   finally:self.open-=1
  app=web.Application();app.router.add_get('/{name}',upstream);self.upstream=TestServer(app,handler_cancellation=True);await self.upstream.start_server();outer=self
  class FixtureMedia(ExternalMedia):
   async def request(this,url,method='GET',headers=None):
    public_url(url);r=await this.session.request(method,outer.upstream.make_url(urlsplit(url).path),headers=headers,allow_redirects=False);r._url=URL(url,encoded=True);return r
  self.media=FixtureMedia('http://unused','test');await self.media.start();self.source=Source('one',{'url':'https://public.example/master.m3u8','kind':'hls'},'relay','https://public.example/');self.media.sources['one']=self.source
  app=web.Application();app.router.add_get('/api/network/{source_id}/play',self.media.play);self.client=TestClient(TestServer(app));await self.client.start_server()
 async def asyncTearDown(self):
  self.gate.set();await self.media.close();await self.client.close();await self.upstream.close()
 def link(self,name='segment.ts',source=None):return self.media.link(source or self.source,'https://public.example/'+name)
 async def read(self,url=None,headers=None):
  r=await self.client.get(url or self.link(),headers=headers);return r.status,await r.read()
 async def test_two_viewers_single_origin_fetch_then_cache_hit(self):
  a,b=await asyncio.gather(self.read(),self.read());self.assertEqual(a,(200,b'0123456789'));self.assertEqual(a,b)
  self.assertEqual(self.calls[('/segment.ts',None)],1,'two viewers must share one origin request')
  self.assertEqual(await self.read(),a);self.assertEqual(self.calls[('/segment.ts',None)],1)
  stats=self.media.stats()['shared_cache'];self.assertGreater(stats['coalesced'],0);self.assertGreater(stats['hits'],0);self.assertEqual(stats['bytes'],10)

 async def test_range_and_source_isolation_head_manifest_bypass(self):
  a=await self.read(headers={'Range':'bytes=2-5'});b=await self.read(headers={'Range':'bytes=2-5'});self.assertEqual(a,(206,b'2345'));self.assertEqual(a,b)
  self.assertEqual(self.calls[('/segment.ts','bytes=2-5')],1)
  self.assertEqual(await self.read(),(200,b'0123456789'));self.assertEqual(self.calls[('/segment.ts',None)],1)
  other=Source('two',dict(self.source.info),'relay',self.source.page);self.media.sources['two']=other
  await self.read(self.link(source=other));self.assertEqual(self.calls[('/segment.ts',None)],2)
  await self.client.head(self.link());self.assertEqual(self.calls[('/segment.ts',None)],3)
  for _ in range(2):self.assertEqual((await self.read(self.link('master.m3u8')))[0],200)
  self.assertEqual(self.calls[('/master.m3u8',None)],2)

 async def test_large_fragments_stream_without_cache(self):
  a=await self.read(self.link('large.ts'));self.assertEqual(a[0],200);self.assertEqual(len(a[1]),2*1024*1024+1)
  stats=self.media.stats()['shared_cache'];self.assertEqual(stats['bytes'],0);self.assertEqual(stats['reserved_bytes'],0);self.assertGreater(stats['skips'],0)

 async def test_lru_budget_ttl_and_source_release(self):
  for i in range(9):
   self.assertEqual((await self.read(self.link('big'+str(i)+'.ts')))[0],200)
   st=self.media.stats()['shared_cache'];self.assertLessEqual(st['bytes']+st['reserved_bytes'],st['limit_bytes'])
  self.assertGreater(self.media.stats()['shared_cache']['bytes'],0);self.assertLessEqual(self.media.stats()['shared_cache']['bytes'],16*1024*1024)
  await self.read(self.link('big0.ts'));self.assertEqual(self.calls[('/big0.ts',None)],2)
  from unittest.mock import patch
  with patch('external_media.time.monotonic',return_value=time.monotonic()+46):self.media.fragments.sweep()
  self.assertEqual(self.media.stats()['shared_cache']['bytes'],0)
  await self.read();await self.media.sweep({'net:one'});await self.media.sweep(set())
  self.assertEqual(self.media.stats()['shared_cache']['bytes'],0);self.assertEqual((await self.read())[0],410)

 async def test_failure_not_retained_and_quota_counts_each_viewer(self):
  self.fail=True;a,b=await asyncio.gather(self.read(),self.read());self.assertEqual(a[0],502);self.assertEqual(b[0],502)
  self.assertEqual(self.calls[('/segment.ts',None)],1);self.assertEqual(self.media.stats()['shared_cache']['bytes'],0)
  self.fail=False;self.media.daily_limit=20
  self.assertEqual((await self.read())[0],200);self.assertEqual((await self.read())[0],200);self.assertEqual(self.media.bytes_sent,20)
  self.assertEqual((await self.read())[0],429);self.assertEqual(self.calls[('/segment.ts',None)],2)

 async def wait(self,predicate):
  for _ in range(150):
   if predicate():return
   await asyncio.sleep(.01)
  self.assertTrue(predicate(),'condition did not settle within 1.5 seconds')

 async def test_one_waiter_cancel_keeps_other_viewer_and_last_cancel_cleans(self):
  self.gate.clear();first=asyncio.create_task(self.read());await self.wait(lambda:self.open>0)
  second=asyncio.create_task(self.read());await self.wait(lambda:self.media.stats()['shared_cache']['coalesced']>0)
  first.cancel();await asyncio.gather(first,return_exceptions=True);await asyncio.sleep(.2)
  self.assertFalse(second.done());self.gate.set();self.assertEqual(await second,(200,b'0123456789'));self.assertEqual(self.calls[('/segment.ts',None)],1)
  self.gate.clear();last=asyncio.create_task(self.read(self.link('next.ts')));await self.wait(lambda:self.open>0);last.cancel();await asyncio.gather(last,return_exceptions=True)
  await self.wait(lambda:self.media.stats()['shared_cache']['inflight']==0 and self.media.stats()['shared_cache']['reserved_bytes']==0 and self.media.streams==0)
  self.assertEqual(self.calls[('/next.ts',None)],1)

 async def test_release_during_load_and_repeated_cleanup(self):
  self.gate.clear();a=asyncio.create_task(self.read());b=asyncio.create_task(self.read());await self.wait(lambda:self.open>0)
  await self.media.release('one');await asyncio.gather(a,b,return_exceptions=True)
  self.assertEqual(self.media.stats()['shared_cache']['reserved_bytes'],0);self.assertEqual(self.media.stats()['shared_cache']['bytes'],0)
  self.gate.set()
  for _ in range(20):
   self.source=Source('one',dict(self.source.info),'relay',self.source.page);self.media.sources['one']=self.source
   a,b=await asyncio.gather(self.read(),self.read());self.assertEqual(a,b);self.assertEqual(a[0],200)
   await self.media.release('one');st=self.media.stats()['shared_cache'];self.assertEqual((st['bytes'],st['reserved_bytes'],st['inflight']),(0,0,0))

 async def test_unknown_length_fragment_shares_but_progressive_mp4_remains_streamed(self):
  a,b=await asyncio.gather(self.read(self.link('unknown.ts')),self.read(self.link('unknown.ts')));self.assertEqual(a,(200,b'0123456789'));self.assertEqual(a,b);self.assertEqual(self.calls[('/unknown.ts',None)],1);self.assertEqual(self.media.stats()['shared_cache']['bytes'],10)
  plain=Source('plain',{'url':'https://public.example/plain.mp4','kind':'mp4'},'relay',self.source.page);self.media.sources['plain']=plain
  a,b=await asyncio.gather(self.read('/api/network/plain/play'),self.read('/api/network/plain/play'));self.assertEqual(a,b);self.assertEqual(a[0],200);self.assertEqual(self.calls[('/plain.mp4',None)],2)

 async def test_entry_count_bound(self):
  from unittest.mock import patch
  with patch.object(type(self.media.fragments),'MAX_ENTRIES',2):
   for i in range(3):await self.read(self.link(str(i)+'.ts'))
   self.assertEqual(self.media.stats()['shared_cache']['entries'],2)
   await self.read(self.link('0.ts'));self.assertEqual(self.calls[('/0.ts',None)],2)

 async def test_cancel_before_loader_starts_unreserves_budget(self):
  started=False
  async def loader():
   nonlocal started
   started=True
  with self.assertRaises(asyncio.CancelledError):await self.media.fragments.obtain(('one',b'key',None),loader,lambda:False)
  self.assertFalse(started);self.assertEqual(self.media.stats()['shared_cache']['reserved_bytes'],0);self.assertEqual(self.media.fragments.jobs,{})

 async def test_unknown_length_oversize_has_bounded_probe_and_stream_fallback(self):
  a=await self.read(self.link('unknown-large.ts'));self.assertEqual(a[0],200);self.assertEqual(len(a[1]),2*1024*1024+1)
  st=self.media.stats()['shared_cache'];self.assertEqual((st['bytes'],st['reserved_bytes'],st['inflight']),(0,0,0));self.assertGreater(st['skips'],0)
