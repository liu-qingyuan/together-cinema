import asyncio,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from urllib.parse import quote
from aiohttp import FormData
from aiohttp.test_utils import TestClient,TestServer
from cinema.server import create_app
class AviUploadTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.client=TestClient(TestServer(create_app(self.tmp.name,'test-password-123456',secure=False)));await self.client.start_server();await self.client.post('/api/login',json={'password':'test-password-123456'})
 async def asyncTearDown(self):
  await self.client.close();self.tmp.cleanup()
 async def upload(self,name,data):
  body=FormData();body.add_field('video',data,filename=name);return await self.client.post('/api/upload',data=body)
 async def worker(self):
  p=await asyncio.create_subprocess_exec(sys.executable,'-m','cinema.conversion','--once','--data-dir',self.tmp.name);self.assertEqual(await p.wait(),0)
 async def test_avi_mpeg4_mp3_to_mp4(self):
  clip=self.root/'fixture.avi';p=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=160x120:rate=10','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','1','-c:v','mpeg4','-pix_fmt','yuv420p','-c:a','libmp3lame','-ac','2','-y',str(clip)],capture_output=True);self.assertEqual(p.returncode,0,p.stderr)
  response=await self.upload('网页AVI自动处理测试.AVI',clip.read_bytes());self.assertEqual(response.status,202,await response.text());job=await response.json();self.assertEqual((await (await self.client.get('/api/library')).json())['files'],[])
  await self.worker();jobs=(await (await self.client.get('/api/conversions')).json())['jobs'];done=next(j for j in jobs if j['id']==job['id']);self.assertEqual(done['status'],'done',done);self.assertEqual(done['mode'],'transcode');self.assertFalse((self.root/'incoming'/(job['id']+'.mkv')).exists());output=self.root/'media'/done['output'];streams=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(output)]))['streams'];self.assertEqual([s['codec_name'] for s in streams],['h264','aac']);self.assertEqual((await self.client.get('/media/'+quote(done['output'],safe=''))).status,200)
 async def test_corrupt_avi_is_not_published_and_can_be_cleaned(self):
  response=await self.upload('broken.avi',b'not AVI');self.assertEqual(response.status,202);job=await response.json();await self.worker();jobs=(await (await self.client.get('/api/conversions')).json())['jobs'];self.assertEqual(jobs[0]['status'],'failed');self.assertEqual((await (await self.client.get('/api/library')).json())['files'],[]);self.assertEqual((await self.client.post('/api/conversions/'+job['id']+'/cancel')).status,202);await self.worker();self.assertFalse((self.root/'incoming'/(job['id']+'.mkv')).exists())
 async def test_avi_and_mkv_share_queue_cap_and_cancel(self):
  jobs=[]
  for name in ['first.mkv','second.avi','third.AVI']:
   response=await self.upload(name,b'pending');self.assertEqual(response.status,202);jobs.append(await response.json())
  self.assertEqual((await self.upload('fourth.avi',b'pending')).status,409)
  for j in jobs:self.assertEqual((await self.client.post('/api/conversions/'+j['id']+'/cancel')).status,202)
  sentinel=self.root/'incoming/keep.txt';sentinel.write_text('keep');await self.worker();self.assertEqual(sentinel.read_text(),'keep');self.assertEqual(list((self.root/'incoming').glob('*.mkv')),[])
