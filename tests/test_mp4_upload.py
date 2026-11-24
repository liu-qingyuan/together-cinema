import asyncio
import hashlib
import tempfile
import unittest
from pathlib import Path

from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer

from cinema.conversion import probe, work_once
from cinema.server import create_app
from tests.media_fixture import mp4


class MP4Intake(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.client = TestClient(TestServer(create_app(self.root, "fixture-session-key", secure=False)))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)
        await self.client.post("/api/login", json={"room": "TEST"})

    async def upload(self, name, data, chunked=False):
        if not chunked:
            form = FormData()
            form.add_field("video", data, filename=name)
            return await self.client.post("/api/upload", data=form)
        session = await (await self.client.post("/api/uploads", json={"filename": name, "size": len(data)})).json()
        url = "/api/uploads/" + session["id"]
        part = await self.client.put(url + "/0", data=data, headers={"X-Chunk-SHA256": hashlib.sha256(data).hexdigest()})
        self.assertEqual(part.status, 200)
        return await self.client.post(url + "/complete")

    async def test_same_extension_different_codecs_both_upload_routes(self):
        for chunked in (False, True):
            direct = mp4()
            r = await self.upload("modern.MP4", direct, chunked)
            self.assertEqual(r.status, 201, await r.text())
            name = (await r.json())["name"]
            self.assertEqual((self.root / "media" / name).read_bytes(), direct)
            old_files = set((self.root / "media").iterdir())
            r = await self.upload("legacy.MP4", mp4("mpeg4"), chunked)
            self.assertEqual(r.status, 202, await r.text())
            self.assertEqual(old_files, set((self.root / "media").iterdir()))
            await asyncio.to_thread(work_once, self.root, 0)
            result, = set((self.root / "media").iterdir()) - old_files
            streams = probe(result)["streams"]
            self.assertEqual([s["codec_name"] for s in streams], ["h264", "aac"])
            self.assertEqual(streams[0]["pix_fmt"], "yuv420p")
            self.assertFalse(list((self.root / "incoming").iterdir()))

    async def test_conversion_leaves_active_playback_running(self):
        playing = (await (await self.upload("playing.mp4", mp4())).json())["name"]
        async with self.client.ws_connect("/ws?room=TEST") as ws:
            await ws.receive_json()
            await ws.receive_json()
            await ws.send_json({"type": "control", "file": playing, "position": 10, "paused": False})
            initial = await ws.receive_json(timeout=3)
            self.assertEqual(initial["file"], playing)
            self.assertFalse(initial["paused"])
            self.assertEqual((await self.upload("old.mp4", mp4("mpeg4"))).status, 202)
            await asyncio.to_thread(work_once, self.root, 0)
            await ws.send_json({"type": "ping"})
            current = await ws.receive_json(timeout=3)
            self.assertEqual(current["file"], playing)
            self.assertFalse(current["paused"])
            self.assertGreaterEqual(current["position"], initial["position"])

    async def test_bad_mp4_does_not_appear_in_library(self):
        for chunked in (False, True):
            r = await self.upload("invalid.mp4", b"not a movie", chunked)
            self.assertEqual(r.status, 422)
        self.assertFalse(list((self.root / "media").iterdir()))

    async def test_full_queue_does_not_block_compatible_mp4(self):
        for _ in range(3):
            self.assertEqual((await self.upload("pending.avi", b"queued")).status, 202)
        self.assertEqual((await self.upload("needs-h264.mp4", mp4("mpeg4"))).status, 409)
        self.assertEqual((await self.upload("ready.mp4", mp4())).status, 201)
