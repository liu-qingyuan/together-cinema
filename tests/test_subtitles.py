import tempfile
import unittest
from pathlib import Path
from aiohttp.test_utils import TestClient, TestServer
from cinema.server import create_app


class SubtitleHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.client=TestClient(TestServer(create_app(self.root,'subtitle-test-123456',secure=False)))
        await self.client.start_server();(self.root/'media/clip.mp4').write_bytes(b'clip')
        self.folder=self.root/'subtitles/clip.mp4';self.folder.mkdir(parents=True)
        (self.folder/'tracks.json').write_text('{"tracks":[{"id":"7","label":"中文","lang":"zh","default":true}],"unsupported_count":5}')
        (self.folder/'7.vtt').write_text('WEBVTT\n\n00:00.000 --> 00:02.000\n字幕测试\n')

    async def asyncTearDown(self):
        await self.client.close();self.tmp.cleanup()

    async def test_private_subtitle_track_load_and_delete_cleanup(self):
        self.assertEqual((await self.client.get('/api/subtitles/clip.mp4')).status,401)
        await self.client.post('/api/login',json={'password':'subtitle-test-123456'})
        r=await self.client.get('/api/subtitles/clip.mp4')
        self.assertEqual(r.status,200)
        data=await r.json();self.assertEqual(data['tracks'][0]['lang'],'zh')
        self.assertEqual(data['unsupported_count'],5)
        r=await self.client.get('/api/subtitles/clip.mp4/7.vtt')
        self.assertEqual(r.status,200);self.assertIn('text/vtt',r.headers['Content-Type'])
        self.assertTrue((await r.text()).startswith('WEBVTT'))
        self.assertEqual((await self.client.get('/api/subtitles/other.mp4/7.vtt')).status,404)
        self.assertEqual((await self.client.delete('/api/library/clip.mp4')).status,200)
        self.assertFalse(self.folder.exists())
        self.assertEqual((await self.client.get('/api/subtitles/clip.mp4/7.vtt')).status,404)



class ExtractionTests(unittest.TestCase):
    def test_text_tracks_survive_background_conversion(self):
        import subprocess
        from cinema.conversion import enqueue, work_once, list_jobs
        from cinema.subtitles import list_subtitles, subtitle_path
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'fixture.mkv'
            (root/'zh.srt').write_text('1\n00:00:00,000 --> 00:00:02,000\n字幕测试\n')
            (root/'en.srt').write_text('1\n00:00:00,000 --> 00:00:02,000\nSubtitle test\n')
            command=['ffmpeg','-v','error','-f','lavfi','-i','color=black:s=64x48:r=24:d=3',
                     '-i',str(root/'zh.srt'),'-i',str(root/'en.srt'),'-map','0:v','-map','1:0','-map','2:0',
                     '-c:v','libx264','-pix_fmt','yuv420p','-c:s','srt',
                     '-metadata:s:s:0','language=chi','-metadata:s:s:0','title=中文',
                     '-metadata:s:s:1','language=eng','-disposition:s:0','default',str(source)]
            subprocess.run(command,check=True,capture_output=True)
            enqueue(root,source,'fixture.mkv');self.assertTrue(work_once(root,0))
            job=list_jobs(root)[0];self.assertEqual(job['status'],'done',job.get('error'))
            tracks=list_subtitles(root,job['output'])['tracks'];self.assertEqual(len(tracks),2)
            self.assertEqual(tracks[0]['lang'],'zh');self.assertTrue(tracks[0]['default'])
            self.assertEqual(tracks[1]['lang'],'en')
            for t in tracks:self.assertTrue(subtitle_path(root,job['output'],t['id']).read_text().startswith('WEBVTT'))
            self.assertFalse(list((root/'media').glob('.*.processing.mp4')))

    def test_track_path_cannot_escape_pair_directory(self):
        import json
        from cinema.subtitles import subtitle_path
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'subtitles/clip.mp4';folder.mkdir(parents=True)
            (folder/'tracks.json').write_text(json.dumps({'tracks':[{'id':'../../outside'}]}))
            with self.assertRaises(ValueError):subtitle_path(root,'clip.mp4','../../outside')

if __name__=='__main__':unittest.main()
