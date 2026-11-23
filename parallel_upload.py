"""One private upload, bounded parallel chunks, atomic publication by the caller."""
import asyncio
import hashlib
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from aiohttp import web

CHUNK_SIZE = 8 * 1024**2
PARALLELISM = 4
IDLE_SECONDS = 15 * 60

@dataclass
class _Session:
    ident: str
    name: str
    size: int
    path: Path
    fd: int
    count: int
    locks: dict = field(default_factory=dict)
    done: dict = field(default_factory=dict)
    inflight: int = 0
    updated: float = field(default_factory=time.monotonic)
    cancelled: bool = False

class ParallelUploads:
    def __init__(self, media, max_bytes, reserve):
        self.media, self.max_bytes, self.reserve = Path(media), max_bytes, reserve
        self.active = None
        self.slots = asyncio.Semaphore(PARALLELISM)
        # Only this Module's private namespace; a restarted upload cannot resume.
        for p in self.media.glob('.upload-parallel-*'):
            if re.fullmatch(r'\.upload-parallel-[a-f0-9]{32}', p.name) and not p.is_symlink():
                p.unlink(missing_ok=True)

    def start(self, name, size):
        if self.active:
            raise web.HTTPConflict(text='已有上传任务，请稍后再试')
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise web.HTTPBadRequest(text='文件大小无效')
        if size > self.max_bytes:
            raise web.HTTPRequestEntityTooLarge(max_size=self.max_bytes, actual_size=size)
        disk = os.statvfs(self.media)
        if disk.f_bavail * disk.f_frsize < size + self.reserve:
            raise web.HTTPInsufficientStorage(text='空间不足，保留 2 GiB 系统余量')
        ident = secrets.token_hex(16)
        path = self.media / ('.upload-parallel-' + ident)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            if hasattr(os, 'posix_fallocate'):
                os.posix_fallocate(fd, 0, size)
            else:
                os.ftruncate(fd, size)
        except OSError:
            os.close(fd); path.unlink(missing_ok=True)
            raise web.HTTPInsufficientStorage(text='无法分配上传空间')
        self.active = _Session(ident, name, size, path, fd, (size + CHUNK_SIZE - 1) // CHUNK_SIZE)
        return {'id': ident, 'chunk_size': CHUNK_SIZE, 'chunk_count': self.active.count,
                'parallelism': PARALLELISM}

    def get(self, ident):
        s = self.active
        if not s or s.ident != ident or s.cancelled:
            raise web.HTTPNotFound(text='上传任务不存在或已过期，请重新选择文件')
        return s

    async def write(self, ident, index, request, digest):
        s = self.get(ident)
        if not isinstance(index, int) or not 0 <= index < s.count:
            raise web.HTTPBadRequest(text='分片编号无效')
        if not re.fullmatch('[a-fA-F0-9]{64}', digest or ''):
            raise web.HTTPBadRequest(text='缺少分片校验值')
        digest = digest.lower()
        lock = s.locks.setdefault(index, asyncio.Lock())
        async with lock, self.slots:
            self.get(ident)
            prior = s.done.get(index)
            if prior and prior != digest:
                raise web.HTTPConflict(text='重试分片与已接收内容不一致')
            expected = min(CHUNK_SIZE, s.size - index * CHUNK_SIZE)
            if request.content_length is not None and request.content_length != expected:
                raise web.HTTPBadRequest(text='分片长度不正确')
            received = 0; h = hashlib.sha256(); s.inflight += 1
            try:
                async with asyncio.timeout(180):
                    async for block in request.content.iter_chunked(256 * 1024):
                        if s.cancelled:
                            raise web.HTTPGone(text='上传已取消')
                        if received + len(block) > expected:
                            raise web.HTTPBadRequest(text='分片超出文件范围')
                        disk = os.statvfs(self.media)
                        if disk.f_bavail * disk.f_frsize < self.reserve:
                            raise web.HTTPInsufficientStorage(text='空间不足，已保留系统余量')
                        h.update(block)
                        if not prior:
                            offset = 0
                            while offset < len(block):
                                written = os.pwrite(s.fd, block[offset:], index * CHUNK_SIZE + received + offset)
                                if written <= 0: raise OSError('short file write')
                                offset += written
                        received += len(block); s.updated = time.monotonic()
                if received != expected or h.hexdigest() != digest:
                    raise web.HTTPBadRequest(text='分片校验失败，请重试')
                s.done[index] = digest
                return {'index': index, 'bytes': received, 'completed_chunks': len(s.done)}
            except TimeoutError:
                raise web.HTTPRequestTimeout(text='分片上传超时，请重试')
            finally:
                s.inflight -= 1
                if s.cancelled and not s.inflight and s.fd is not None:
                    os.close(s.fd); s.fd = None

    def ready(self, ident):
        s = self.get(ident)
        if s.inflight or len(s.done) != s.count:
            raise web.HTTPConflict(text='分片尚未全部上传完成')
        os.fsync(s.fd)
        if os.fstat(s.fd).st_size != s.size:
            raise web.HTTPBadRequest(text='上传文件长度不正确')
        return s

    def cancel(self, ident):
        s = self.get(ident); s.cancelled = True; self.active = None
        s.path.unlink(missing_ok=True)
        if not s.inflight and s.fd is not None:
            os.close(s.fd); s.fd = None

    def expire(self):
        s = self.active
        if s and not s.inflight and time.monotonic() - s.updated > IDLE_SECONDS:
            self.cancel(s.ident)

    async def lifecycle(self, app):
        async def sweep():
            while True:
                await asyncio.sleep(30); self.expire()
        task = asyncio.create_task(sweep())
        try:
            yield
        finally:
            task.cancel()
            try: await task
            except asyncio.CancelledError: pass
            if self.active: self.cancel(self.active.ident)
