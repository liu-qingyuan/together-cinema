import hashlib,tempfile,unittest,io
from pathlib import Path
from aiohttp.test_utils import TestClient,TestServer
from cinema.server import create_app
class ParallelUploadTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.client=TestClient(TestServer(create_app(self.tmp.name,'test-password-123456',secure=False)));await self.client.start_server();await self.client.post('/api/login',json={'password':'test-password-123456'})
 async def asyncTearDown(self):await self.client.close();self.tmp.cleanup()
 async def test_session_publishes_exact_mp4_only_after_complete(self):
  data=b'fixture bytes'*1024;r=await self.client.post('/api/uploads',json={'filename':'clip.mp4','size':len(data)});self.assertEqual(r.status,201,await r.text());s=await r.json();self.assertEqual((await(await self.client.get('/api/library')).json())['files'],[]);r=await self.client.put('/api/uploads/'+s['id']+'/0',data=data,headers={'X-Chunk-SHA256':hashlib.sha256(data).hexdigest()});self.assertEqual(r.status,200,await r.text());r=await self.client.post('/api/uploads/'+s['id']+'/complete');self.assertEqual(r.status,201,await r.text());done=await r.json();self.assertEqual((self.root/'media'/done['name']).read_bytes(),data);self.assertEqual(list((self.root/'media').glob('.upload-parallel-*')),[])
 async def start(self,name,size):
  r=await self.client.post('/api/uploads',json={'filename':name,'size':size});self.assertEqual(r.status,201,await r.text());return await r.json()
 async def put(self,s,index,data,digest=None):return await self.client.put('/api/uploads/'+s['id']+'/'+str(index),data=io.BytesIO(data),headers={'X-Chunk-SHA256':digest or hashlib.sha256(data).hexdigest()})
 async def test_out_of_order_and_matching_retry(self):
  from cinema.parallel_upload import CHUNK_SIZE
  a=b'a'*CHUNK_SIZE;b=b'tail';s=await self.start('ordered.mp4',len(a)+len(b));self.assertEqual((await self.put(s,1,b)).status,200);self.assertEqual((await self.client.post('/api/uploads/'+s['id']+'/complete')).status,409);self.assertEqual((await self.put(s,1,b)).status,200);self.assertEqual((await self.put(s,1,b'fail')).status,409);self.assertEqual((await self.put(s,0,a)).status,200);r=await self.client.post('/api/uploads/'+s['id']+'/complete');self.assertEqual(r.status,201);j=await r.json();self.assertEqual((self.root/'media'/j['name']).read_bytes(),a+b)
 async def test_bad_chunks_never_publish_and_can_retry(self):
  s=await self.start('retry.mp4',4);self.assertEqual((await self.put(s,0,b'data','0'*64)).status,400);self.assertEqual((await self.put(s,0,b'bad')).status,400);self.assertEqual((await self.put(s,-1,b'data')).status,400);self.assertEqual((await self.put(s,99,b'data')).status,400);self.assertEqual((await self.client.post('/api/uploads/'+s['id']+'/complete')).status,409);self.assertEqual((await self.put(s,0,b'data')).status,200);self.assertEqual((await self.client.post('/api/uploads/'+s['id']+'/complete')).status,201)
 async def test_cancel_and_legacy_mutual_exclusion(self):
  from aiohttp import FormData
  s=await self.start('cancel.mp4',4);self.assertEqual((await self.client.post('/api/uploads',json={'filename':'other.mp4','size':1})).status,409);body=FormData();body.add_field('video',b'legacy',filename='legacy.mp4');self.assertEqual((await self.client.post('/api/upload',data=body)).status,409);self.assertEqual((await self.client.delete('/api/uploads/'+s['id'])).status,200);self.assertEqual(list((self.root/'media').glob('.upload-parallel-*')),[]);self.assertEqual((await self.put(s,0,b'data')).status,404);body=FormData();body.add_field('video',b'legacy',filename='legacy.mp4');self.assertEqual((await self.client.post('/api/upload',data=body)).status,201)
 async def test_avi_enters_same_private_conversion_queue(self):
  s=await self.start('source.avi',4);self.assertEqual((await self.put(s,0,b'data')).status,200);r=await self.client.post('/api/uploads/'+s['id']+'/complete');self.assertEqual(r.status,202);j=await r.json();self.assertEqual((self.root/'incoming'/(j['id']+'.mkv')).read_bytes(),b'data');self.assertEqual((await(await self.client.get('/api/library')).json())['files'],[])
 async def test_metadata_auth_origin_size_and_name(self):
  for body,code in [({'filename':'x.mp4','size':True},400),({'filename':'x.mp4','size':0},400),({'filename':'../x.mp4','size':1},400),({'filename':'x.txt','size':1},400),({'filename':'x.mp4','size':8*1024**3+1},413)]:
   r=await self.client.post('/api/uploads',json=body);self.assertEqual(r.status,code,await r.text())
  self.assertEqual((await self.client.post('/api/uploads',json={'filename':'x.mp4','size':1},headers={'Origin':'https://evil.example'})).status,403);self.assertEqual((await self.client.post('/api/uploads',data=b' '*5000)).status,413);await self.client.post('/api/logout');self.assertEqual((await self.client.post('/api/uploads',json={'filename':'x.mp4','size':1})).status,401)
 async def test_expiry_restart_cleanup_and_reserve(self):
  from cinema.parallel_upload import ParallelUploads,IDLE_SECONDS
  from unittest.mock import patch
  media=self.root/'isolated';media.mkdir();m=ParallelUploads(media,100,0);s=m.start('file.mp4',4);m.active.updated-=IDLE_SECONDS+1;m.expire();self.assertIsNone(m.active);self.assertEqual(list(media.iterdir()),[]);m.start('file.mp4',4);m.cancel(m.active.ident);orphan=media/('.upload-parallel-'+'a'*32);orphan.write_bytes(b'old');ParallelUploads(media,100,0);self.assertFalse(orphan.exists())
  fake=type('Disk',(),{'f_bavail':0,'f_frsize':4096})();
  with patch('cinema.parallel_upload.os.statvfs',return_value=fake):self.assertEqual((await self.client.post('/api/uploads',json={'filename':'x.mp4','size':1})).status,507)
 async def test_cancel_during_stream_does_not_leave_a_file(self):
  import asyncio
  s=await self.start('stream.mp4',4096);started=asyncio.Event();release=asyncio.Event()
  async def body():
   yield b'x'*1024;started.set();await release.wait();yield b'x'*3072
  task=asyncio.create_task(self.client.put('/api/uploads/'+s['id']+'/0',data=body(),headers={'X-Chunk-SHA256':hashlib.sha256(b'x'*4096).hexdigest()}));await started.wait();await asyncio.sleep(.05);self.assertEqual((await self.client.delete('/api/uploads/'+s['id'])).status,200);release.set();r=await task;self.assertEqual(r.status,410,await r.text());self.assertEqual(list((self.root/'media').glob('.upload-parallel-*')),[])
