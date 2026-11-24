import unittest,tempfile,json,shutil,subprocess
from pathlib import Path
from aiohttp.test_utils import TestClient,TestServer
from cinema.server import create_app
from cinema.subtitles import extract_subtitles,list_subtitles
from cinema.conversion import conversion_command
FIXTURE=Path(__file__).parent/'fixtures/test.sup'
class PGSHTTPTests(unittest.IsolatedAsyncioTestCase):
 async def test_private_original_track_selection(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);client=TestClient(TestServer(create_app(root,'test-pgs-password-123',secure=False)));await client.start_server()
   try:
    (root/'media/clip.mp4').write_bytes(b'fixture');folder=root/'subtitles/clip.mp4';folder.mkdir(parents=True)
    (folder/'tracks.json').write_text(json.dumps({'tracks':[{'id':'2','format':'pgs','label':'原简中','lang':'zh','default':True}],'unsupported_count':0}));data=FIXTURE.read_bytes();(folder/'2.sup').write_bytes(data)
    self.assertEqual((await client.get('/api/subtitles/clip.mp4/2.sup')).status,401)
    await client.post('/api/login',json={'password':'test-pgs-password-123'});r=await client.get('/api/subtitles/clip.mp4');tracks=(await r.json())['tracks'];self.assertEqual(len(tracks),1);self.assertEqual(tracks[0]['format'],'pgs')
    r=await client.get('/api/subtitles/clip.mp4/2.sup');self.assertEqual(r.status,200);self.assertEqual(await r.read(),data);self.assertIn('application/octet-stream',r.headers['Content-Type'])
    self.assertEqual((await client.get('/api/subtitles/clip.mp4/2.vtt')).status,404)
    self.assertEqual((await client.get('/api/subtitles/clip.mp4/999.sup')).status,404)
    self.assertEqual((await client.get('/api/subtitles/other.mp4/2.sup')).status,404)
    await client.delete('/api/library/clip.mp4');self.assertFalse(folder.exists())
   finally:await client.close()
class HEVCTests(unittest.TestCase):
 def test_hevc_main_preserved(self):
  meta={'streams':[{'index':0,'codec_type':'video','codec_name':'hevc','profile':'Main','pix_fmt':'yuv420p','width':1920,'height':1038,'level':120,'color_transfer':'bt709'},{'index':1,'codec_type':'audio','codec_name':'aac','profile':'LC','channels':2}]}
  cmd,mode=conversion_command(Path('source.mkv'),Path('output.mp4'),Path('progress'),meta)
  self.assertEqual(mode,'remux');self.assertEqual(cmd[cmd.index('-c:v')+1],'copy');self.assertEqual(cmd[cmd.index('-tag:v')+1],'hvc1');self.assertIn('-map_chapters',cmd)
class PGSExtractionTests(unittest.TestCase):
 def test_bitmap_track_survives_background_conversion(self):
  from cinema.conversion import enqueue,work_once,list_jobs
  from cinema.subtitles import subtitle_path
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'fixture.mkv';fixture=FIXTURE
   cmd=['ffmpeg','-v','error','-f','lavfi','-i','color=black:s=128x64:r=24:d=5','-i',str(fixture),'-map','0:v','-map','1:0','-c:v','libx264','-pix_fmt','yuv420p','-c:s','copy','-metadata:s:s:0','language=chi','-metadata:s:s:0','title=原简中','-disposition:s:0','default','-t','5',str(source)]
   result=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr)
   enqueue(root,source,'fixture.mkv');self.assertTrue(work_once(root,0));job=list_jobs(root)[0];self.assertEqual(job['status'],'done',job.get('error'))
   manifest=list_subtitles(root,job['output']);self.assertEqual(len(manifest['tracks']),1);track=manifest['tracks'][0];self.assertEqual(track['format'],'pgs');self.assertTrue(track['default']);self.assertEqual(manifest['unsupported_count'],0);self.assertTrue(subtitle_path(root,job['output'],track['id']).read_bytes().startswith(b'PG'))
if __name__=='__main__':unittest.main()
