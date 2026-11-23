import io
import asyncio
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer
from server import create_app


class MkvUploadTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.client = TestClient(TestServer(create_app(self.tmp.name, 'test-password-123456', secure=False)))
        await self.client.start_server()
        await self.client.post('/api/login', json={'password': 'test-password-123456'})

    async def asyncTearDown(self):
        await self.client.close()
        self.tmp.cleanup()

    async def test_mkv_is_queued_and_not_exposed_before_conversion(self):
        body = FormData()
        body.add_field('video', io.BytesIO(b'pending-mkv-data'), filename='movie.mkv')
        response = await self.client.post('/api/upload', data=body)
        self.assertEqual(response.status, 202)
        job = await response.json()
        self.assertEqual(job['status'], 'queued')
        jobs = await (await self.client.get('/api/conversions')).json()
        self.assertEqual(jobs['jobs'][0]['id'], job['id'])
        library = await (await self.client.get('/api/library')).json()
        self.assertEqual(library['files'], [])

    async def test_partial_conversion_output_stays_private(self):
        media = Path(self.tmp.name) / 'media'
        (media / '.partial.processing.mp4').write_bytes(b'incomplete')
        library = await (await self.client.get('/api/library')).json()
        self.assertEqual(library['files'], [])
        self.assertEqual((await self.client.get('/media/.partial.processing.mp4')).status, 404)

    async def test_cancel_queued_mkv_cleans_only_its_source(self):
        body = FormData()
        body.add_field('video', b'pending-data', filename='cancel.mkv')
        job = await (await self.client.post('/api/upload', data=body)).json()
        sentinel = Path(self.tmp.name) / 'incoming' / 'keep.txt'
        sentinel.write_text('keep')
        response = await self.client.post('/api/conversions/' + job['id'] + '/cancel')
        self.assertEqual(response.status, 202)
        process = await asyncio.create_subprocess_exec(
            sys.executable, str(Path(__file__).with_name('conversion.py')),
            '--once', '--data-dir', self.tmp.name)
        self.assertEqual(await process.wait(), 0)
        jobs = await (await self.client.get('/api/conversions')).json()
        self.assertEqual(jobs['jobs'][0]['status'], 'cancelled')
        self.assertEqual(sentinel.read_text(), 'keep')
        self.assertFalse((sentinel.parent / (job['id'] + '.mkv')).exists())

    async def test_completed_mkv_becomes_h264_aac_mp4_in_library(self):
        fixture = Path(self.tmp.name) / 'fixture.mkv'
        p = subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                            'testsrc2=size=160x90:rate=10', '-f', 'lavfi', '-i',
                            'sine=frequency=440:sample_rate=48000', '-t', '3',
                            '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt',
                            'yuv420p', '-c:a', 'ac3', '-y', str(fixture)], capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        body = FormData()
        body.add_field('video', fixture.read_bytes(), filename='测试.mkv')
        job = await (await self.client.post('/api/upload', data=body)).json()
        process = await asyncio.create_subprocess_exec(
            sys.executable, str(Path(__file__).with_name('conversion.py')),
            '--once', '--data-dir', self.tmp.name,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await process.communicate()
        self.assertEqual(process.returncode, 0, stderr)
        jobs = await (await self.client.get('/api/conversions')).json()
        self.assertEqual(jobs['jobs'][0]['status'], 'done', (stdout, stderr, jobs))
        self.assertEqual(jobs['jobs'][0]['mode'], 'audio')
        library = await (await self.client.get('/api/library')).json()
        self.assertEqual(len(library['files']), 1)
        output = Path(self.tmp.name) / 'media' / library['files'][0]['name']
        streams = json.loads(subprocess.check_output(
            ['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(output)]))['streams']
        self.assertEqual([s['codec_name'] for s in streams], ['h264', 'aac'])
        self.assertFalse((Path(self.tmp.name) / 'incoming' / (job['id'] + '.mkv')).exists())

    async def test_remux_and_video_transcode_paths(self):
        for codec, mode in [('libx264', 'remux'), ('mpeg4', 'transcode')]:
            with self.subTest(codec=codec):
                fixture = Path(self.tmp.name) / (codec + '.mkv')
                command = ['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                           'testsrc2=size=160x90:rate=10', '-f', 'lavfi', '-i',
                           'sine=frequency=440:sample_rate=48000', '-t', '1',
                           '-c:v', codec, '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-y', str(fixture)]
                result = subprocess.run(command, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                body = FormData()
                body.add_field('video', fixture.read_bytes(), filename=codec + '.mkv')
                submitted = await (await self.client.post('/api/upload', data=body)).json()
                process = await asyncio.create_subprocess_exec(
                    sys.executable, str(Path(__file__).with_name('conversion.py')),
                    '--once', '--data-dir', self.tmp.name)
                self.assertEqual(await process.wait(), 0)
                jobs = await (await self.client.get('/api/conversions')).json()
                job = next(j for j in jobs['jobs'] if j['id'] == submitted['id'])
                self.assertEqual(job['status'], 'done', job)
                self.assertEqual(job['mode'], mode)
                output = Path(self.tmp.name) / 'media' / job['output']
                streams = json.loads(subprocess.check_output(
                    ['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(output)]))['streams']
                self.assertEqual([s['codec_name'] for s in streams], ['h264', 'aac'])

    async def test_corrupt_mkv_reports_failure_without_publishing(self):
        body = FormData()
        body.add_field('video', b'not a real video', filename='broken.mkv')
        submitted = await (await self.client.post('/api/upload', data=body)).json()
        process = await asyncio.create_subprocess_exec(
            sys.executable, str(Path(__file__).with_name('conversion.py')),
            '--once', '--data-dir', self.tmp.name)
        self.assertEqual(await process.wait(), 0)
        jobs = await (await self.client.get('/api/conversions')).json()
        self.assertEqual(jobs['jobs'][0]['status'], 'failed')
        library = await (await self.client.get('/api/library')).json()
        self.assertEqual(library['files'], [])
        self.assertEqual((await self.client.post('/api/conversions/' + submitted['id'] + '/cancel')).status, 202)

    async def test_portrait_transcode_respects_720p_height_limit(self):
        fixture = Path(self.tmp.name) / 'portrait.mkv'
        generated = subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                                    'color=size=720x1280:rate=5', '-t', '0.2',
                                    '-c:v', 'mpeg4', '-y', str(fixture)], capture_output=True)
        self.assertEqual(generated.returncode, 0, generated.stderr)
        body = FormData()
        body.add_field('video', fixture.read_bytes(), filename='portrait.mkv')
        submitted = await (await self.client.post('/api/upload', data=body)).json()
        process = await asyncio.create_subprocess_exec(
            sys.executable, str(Path(__file__).with_name('conversion.py')),
            '--once', '--data-dir', self.tmp.name)
        self.assertEqual(await process.wait(), 0)
        jobs = await (await self.client.get('/api/conversions')).json()
        job = next(j for j in jobs['jobs'] if j['id'] == submitted['id'])
        self.assertEqual(job['status'], 'done', job)
        output = Path(self.tmp.name) / 'media' / job['output']
        streams = json.loads(subprocess.check_output(
            ['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(output)]))['streams']
        self.assertLessEqual(streams[0]['width'], 1280)
        self.assertLessEqual(streams[0]['height'], 720)


if __name__ == '__main__':
    unittest.main()
