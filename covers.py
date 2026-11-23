"""Site-wide gallery covers; independent of rooms, media and personal themes."""
import asyncio
import io
import json
import os
import secrets
import shutil
from pathlib import Path

from aiohttp import web
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_COVER_BYTES = 8 * 1024**2
MAX_COVER_PIXELS = 8_000_000
PRESETS = [
    dict(id='sky', name='动漫天空', alt='云间留白的动漫蓝天',
         credit='Sky Backgrounds · Unicorn Creates', width=1280, height=720),
    dict(id='galaxy', name='雪山银河', alt='银河下的厄尔布鲁士雪山与帐篷',
         credit='Milky way in Elbrus · oliwok', width=960, height=1440),
]


def derive(source):
    """Decode once, normalize orientation and strip metadata from public variants."""
    try:
        with Image.open(source, formats=['JPEG', 'PNG', 'WEBP']) as original:
            if original.width * original.height > MAX_COVER_PIXELS or original.n_frames != 1:
                raise ValueError()
            image = ImageOps.exif_transpose(original).convert('RGB')
        width, height = image.size
        variants = {}
        for size, bounds in [('desktop', (1920, 1440)), ('mobile', (960, 1280))]:
            resized = image.copy()
            resized.thumbnail(bounds)
            output = io.BytesIO()
            resized.save(output, 'WEBP', quality=85)
            variants[size] = output.getvalue()
        return width, height, variants
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
        raise web.HTTPBadRequest(text='请选择静态 JPEG／PNG／WebP，最多 800 万像素') from error


class SharedCovers:
    """Upload selects on success; failed writes preserve the previous selection.

    Reads are public. The HTTP caller must verify active membership before writes.
    Custom originals and variants live together and are removed together.
    """
    def __init__(self, data_dir, reserve):
        self.root = Path(data_dir) / 'covers'
        self.root.mkdir(parents=True, exist_ok=True)
        self.reserve = reserve
        self.lock = asyncio.Lock()
        self.index = self.root / 'index.json'
        self.state = json.loads(self.index.read_text()) if self.index.exists() else {'current': 'sky', 'custom': []}

    def catalog(self):
        presets = [dict(item, builtin=True,
                        desktop=f'/scenes/v1-{item["id"]}-desktop.webp',
                        mobile=f'/scenes/v1-{item["id"]}-mobile.webp') for item in PRESETS]
        return {'current': self.state['current'], 'covers': presets + self.state['custom']}

    def asset(self, ident, size):
        if size not in ('desktop', 'mobile') or not any(item['id'] == ident for item in self.state['custom']):
            raise web.HTTPNotFound()
        return self.root / ident / (size + '.webp')

    def _write(self, path, content):
        disk = os.statvfs(self.root)
        if disk.f_bavail * disk.f_frsize - len(content) < self.reserve:
            raise web.HTTPInsufficientStorage(text='空间不足，保留系统磁盘余量')
        path.write_bytes(content)

    def _save(self, state):
        temporary = self.root / '.index.tmp'
        try:
            self._write(temporary, json.dumps(state, ensure_ascii=False).encode())
            temporary.replace(self.index)
            self.state = state
        finally:
            temporary.unlink(missing_ok=True)

    async def select(self, ident):
        async with self.lock:
            if not isinstance(ident, str) or not any(item['id'] == ident for item in self.catalog()['covers']):
                raise web.HTTPNotFound(text='封面不存在或已经删除')
            self._save(dict(self.state, current=ident))
            return self.catalog()

    async def delete(self, ident):
        async with self.lock:
            if ident in {item['id'] for item in PRESETS}:
                raise web.HTTPBadRequest(text='内置预设不能删除')
            custom = [item for item in self.state['custom'] if item['id'] != ident]
            if len(custom) == len(self.state['custom']):
                raise web.HTTPNotFound(text='封面不存在或已经删除')
            self._save({'current': 'sky' if self.state['current'] == ident else self.state['current'],
                        'custom': custom})
            shutil.rmtree(self.root / ident)
            return self.catalog()

    async def upload(self, part):
        async with self.lock:
            ident = secrets.token_hex(16)
            temporary = self.root / ('.upload-' + ident)
            published = self.root / ident
            temporary.mkdir()
            try:
                source = temporary / 'source'
                total = 0
                with source.open('xb') as output:
                    while chunk := await part.read_chunk(256 * 1024):
                        total += len(chunk)
                        if total > MAX_COVER_BYTES:
                            raise web.HTTPRequestEntityTooLarge(max_size=MAX_COVER_BYTES, actual_size=total)
                        disk = os.statvfs(self.root)
                        if disk.f_bavail * disk.f_frsize - len(chunk) < self.reserve:
                            raise web.HTTPInsufficientStorage(text='空间不足，保留系统磁盘余量')
                        output.write(chunk)
                width, height, variants = await asyncio.to_thread(derive, source)
                for size, content in variants.items():
                    self._write(temporary / (size + '.webp'), content)
                item = dict(id=ident, name=Path(part.filename).name[:100], alt='成员上传的展厅封面',
                            credit='成员上传 · 请确保拥有分发许可', builtin=False, width=width, height=height,
                            desktop=f'/covers/{ident}/desktop.webp', mobile=f'/covers/{ident}/mobile.webp')
                temporary.replace(published)
                self._save({'current': ident, 'custom': self.state['custom'] + [item]})
                return self.catalog()
            finally:
                shutil.rmtree(temporary, ignore_errors=True)
                if self.state['current'] != ident:
                    shutil.rmtree(published, ignore_errors=True)
