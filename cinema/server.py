import asyncio
import base64
import re
from contextlib import suppress
import hashlib
import hmac
import json
import math
import os
import secrets
import logging
import sqlite3
import time
from pathlib import Path

from aiohttp import WSMsgType, web
from .parallel_upload import ParallelUploads
from .conversion import CONVERSION_EXTENSIONS, enqueue, list_jobs
from .danmaku import DanmakuStore
from .watch_history import WatchHistory, film_title
from .covers import SharedCovers
from .external_media import ExternalMedia
from .subtitles import list_subtitles, subtitle_path, remove_subtitles

WEB_DIR = Path(__file__).resolve().parent.parent / 'web'
EXTENSIONS = {'.mp4', '.m4v', '.webm'}


class Room:
    def __init__(self, code="01"):
        self.code = code
        self.members = {}
        self.chat = []
        self.remembered_file = None
        self.last_used = time.monotonic()
        self.clients = {}
        self.host = None
        self.file = None
        self.library_version = 0
        self.paused = True
        self.position = 0.0
        self.updated = time.monotonic()
        self.playback_rate = 1.0
        self.base_rate = 1.0
        self.boost_until = 0.0
        self.rate_dirty = False

    def expire_boost(self, now=None):
        now = time.monotonic() if now is None else now
        if not self.boost_until or now < self.boost_until:
            return False
        if not self.paused:
            self.position += max(0, self.boost_until - self.updated) * self.playback_rate
        self.updated = self.boost_until
        self.playback_rate, self.boost_until = self.base_rate, 0.0
        self.rate_dirty = True
        return True

    def reset_boost(self):
        now = time.monotonic()
        self.expire_boost(now)
        if not self.paused:
            self.position += max(0, now - self.updated) * self.playback_rate
        self.updated = now
        self.playback_rate, self.boost_until = self.base_rate, 0.0

    def invalidate_source(self, source):
        """Stop only if source is still selected; keep the chosen base rate and room identity.

        The caller owns source cleanup and broadcasting. Repeated or stale notices are no-ops.
        """
        if not source or self.file != source:
            return False
        self.reset_boost()
        self.file, self.paused, self.position = None, True, 0.0
        return True

    def set_boost(self, actor, active, file):
        if actor != self.host or not isinstance(active, bool) or file != self.file or not file:
            return False
        if active and self.paused:
            return False
        self.reset_boost()
        if active:
            self.playback_rate = 2.0
            self.boost_until = time.monotonic() + 3.0
        return True

    def set_rate(self, actor, rate, file):
        if (actor != self.host or file != self.file or not file or isinstance(rate,bool) or
            not isinstance(rate,(int,float)) or rate not in (.5,.75,1,1.25,1.5,2)):
            return False
        self.reset_boost()
        self.base_rate = self.playback_rate = float(rate)
        return True

    def snapshot(self):
        now = time.monotonic()
        self.expire_boost(now)
        return dict(type='state', room=self.code, members=[dict(id=k, **v) for k,v in self.members.items()], host=self.host, file=self.file, paused=self.paused,
                    position=self.position + (0 if self.paused else max(0, now - self.updated) * self.playback_rate),
                    playback_rate=self.playback_rate, boosting=bool(self.boost_until), base_rate=self.base_rate,
                    online=len(self.clients), library_version=self.library_version, server_time=time.time())

    def update(self, actor, data, available):
        if actor != self.host:
            return False
        file = data.get('file', self.file)
        position = data.get('position', 0)
        paused = data.get('paused', True)
        if (file not in available or isinstance(position, bool) or
                not isinstance(position, (int, float)) or not math.isfinite(position) or
                not 0 <= position <= 604800 or not isinstance(paused, bool)):
            return False
        self.expire_boost()
        if file != self.file:
            self.remembered_file = None
            self.base_rate = 1.0
        if file != self.file or paused:
            self.playback_rate, self.boost_until = self.base_rate, 0.0
        self.file, self.position, self.paused = file, float(position), paused
        self.updated = time.monotonic()
        return True

    async def broadcast(self, memory=None):
        state = self.snapshot()
        if memory is not None:
            state['memory'] = memory
        self.rate_dirty = False
        for ws in list(self.clients.values()):
            try:
                await ws.send_json(state)
            except (ConnectionError, RuntimeError):
                pass

    async def event(self, event):
        for ws in list(self.clients.values()):
            try:
                await ws.send_json(event)
            except (ConnectionError, RuntimeError):
                pass


def create_app(data_dir=None, password=None, secure=None):
    data_dir = Path(data_dir or os.environ.get('DATA_DIR', '/data'))
    media = data_dir / 'media'
    media.mkdir(parents=True, exist_ok=True)
    password = password or os.environ['WATCH_PASSWORD']
    if len(password) < 12:
        raise ValueError('WATCH_PASSWORD must have at least 12 characters')
    key = hashlib.sha256(('watch-session:' + password).encode()).digest()
    secure = secure if secure is not None else os.environ.get('COOKIE_SECURE', 'true') == 'true'
    rooms = {'01': Room('01')}
    cover_members = {}

    def room_code(value):
        if not isinstance(value, str):
            raise web.HTTPBadRequest(text='房间码为 2～8 位字母或数字', headers={'X-Cinema-Error': 'room_code_invalid'})
        code = value.strip().upper()
        if not re.fullmatch(r'[A-Z0-9]{2,8}', code):
            raise web.HTTPBadRequest(text='房间码为 2～8 位字母或数字', headers={'X-Cinema-Error': 'room_code_invalid'})
        return code

    def resolve_room(code):
        if code not in rooms:
            if len(rooms) >= 32:
                idle = [r for r in rooms.values() if not r.clients and r.code != '01']
                if not idle:
                    raise web.HTTPServiceUnavailable(text='房间数量已满')
                rooms.pop(min(idle, key=lambda r:r.last_used).code)
            rooms[code] = Room(code)
        return rooms[code]

    # Only a deployment checkpoint, never a client-provided file or URL.
    checkpoint = data_dir / 'room-checkpoint.json'
    if checkpoint.is_file():
        try:
            saved = json.loads(checkpoint.read_text())
            r = rooms['01']
            candidate = media / saved['file'] if isinstance(saved.get('file'), str) else None
            if candidate and candidate.parent == media and candidate.is_file() and not candidate.is_symlink():
                r.file = saved['file']
                r.position = max(0,min(604800,float(saved.get('position',0))))
                age = max(0,time.time()-float(saved.get('server_time',0)))
                rate = saved.get('base_rate',1)
                r.base_rate = r.playback_rate = float(rate) if isinstance(rate,(int,float)) and not isinstance(rate,bool) and rate in (.5,.75,1,1.25,1.5,2) else 1.0
                r.paused = saved.get('paused') is not False or age>120
                if not r.paused:
                    r.position += min(age,60)*r.base_rate
            checkpoint.unlink(missing_ok=True)
        except (OSError, ValueError, KeyError, TypeError):
            pass
    network = ExternalMedia(os.environ.get('WATCH_EXTRACTOR_URL','http://extractor:8081'),password)
    comments = DanmakuStore(data_dir)
    history = WatchHistory(data_dir)
    last_comment = {}
    attempts = {}
    upload_lock = asyncio.Lock()
    reserve = int(os.environ.get('RESERVE_BYTES', str(2 * 1024**3)))
    max_upload = int(os.environ.get('MAX_UPLOAD_BYTES', str(8 * 1024**3)))
    parallel_uploads = ParallelUploads(media, max_upload, reserve)
    covers = SharedCovers(data_dir, reserve)

    def files():
        return {p.name: p for p in media.iterdir()
                if p.is_file() and not p.is_symlink() and not p.name.startswith('.')
                and p.suffix.lower() in EXTENSIONS}

    def available():
        return set(files()) | {'net:'+key for key in network.sources}

    def signed(expiry):
        value = str(expiry)
        return value + '.' + hmac.new(key, value.encode(), hashlib.sha256).hexdigest()

    def authenticated(request):
        token = request.cookies.get('watch_session', '')
        try:
            expiry = int(token.split('.')[0])
            return expiry > time.time() and hmac.compare_digest(token, signed(expiry))
        except (ValueError, IndexError):
            return False

    @web.middleware
    async def identify_errors(request, handler):
        # Keep status and legacy text for old clients; new UIs use the identifier.
        try:
            return await handler(request)
        except web.HTTPException as error:
            if error.status >= 400:
                error.headers.setdefault('X-Cinema-Error', 'http_' + str(error.status))
            raise

    @web.middleware
    async def guard(request, handler):
        origin = request.headers.get('Origin')
        if (request.method not in ('GET', 'HEAD') or request.path == '/ws') and origin:
            scheme = 'https' if secure else request.scheme
            if origin != scheme + '://' + request.host:
                raise web.HTTPForbidden(text='来源不匹配', headers={'X-Cinema-Error': 'origin_mismatch'})
        public_cover_read = request.path == '/api/covers' and request.method in ('GET', 'HEAD')
        if (request.path.startswith('/api/') and request.path != '/api/login' and not public_cover_read or
                request.path.startswith('/media/') or request.path == '/ws'):
            if not authenticated(request):
                raise web.HTTPUnauthorized(text='请先登录', headers={'X-Cinema-Error': 'login_required'})
        return await handler(request)

    async def index(request):
        return web.FileResponse(WEB_DIR / 'index.html', headers={'Cache-Control': 'no-store'})

    async def player_asset(request):
        name = request.match_info['name']
        if name not in {'locale.js', 'locale-messages.js', 'appearance.js', 'appearance.css', 'memory-reel.js', 'room-groups.css', 'site-nav.css', 'site-nav.js', 'comfort-motion-1.js', 'room-comfort.css', 'room-atlas-v2.css', 'room-atlas-v2.js', 'libpgs-0.9.0.js', 'libpgs-0.9.0.worker.js', 'danmaku-2.0.10.dom.js', 'artplayer-5.4.0.js', 'hls-1.7.4.js'}:
            raise web.HTTPNotFound()
        return web.FileResponse(WEB_DIR / 'assets' / name, headers={'Cache-Control': 'public, max-age=31536000, immutable'})

    async def scene_asset(request):
        name = request.match_info['name']
        legacy = re.fullmatch(r'v1-(anime|tech|cartoon|cute|minimal|real)(-thumb)?\.svg', name)
        if legacy:
            raise web.HTTPFound('/room-art/' + legacy[1] + ('-thumb.webp' if legacy[2] else '-wide.webp'))
        names = {f'v1-{key}-{size}.webp' for key in ('sky', 'galaxy') for size in ('desktop', 'mobile')}
        if name not in names and name not in {'sources.json', 'LICENSE-CC-BY-4.0.txt'}:
            raise web.HTTPNotFound()
        return web.FileResponse(WEB_DIR / 'assets' / 'scenes' / name,
                                headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'public, max-age=3600'})

    async def room_art(request):
        name = request.match_info['name']
        if name != 'anime-opening-v1.mp4' and not re.fullmatch(r'(anime|minimal|cute|portrait|real|cartoon|future|tech)-(wide|compact|thumb)\.webp', name):
            raise web.HTTPNotFound()
        return web.FileResponse(WEB_DIR / 'assets' / 'room-art' / name,
                                headers={'X-Content-Type-Options':'nosniff','Cache-Control':'public, max-age=3600'})

    def require_cover_member(request):
        member = cover_members.get(request.headers.get('X-Room-Member', ''))
        if not member or member[0].closed or member[1] != request.cookies.get('watch_session'):
            raise web.HTTPForbidden(text='请先连接放映室，再修改全站封面')

    async def cover_catalog(request):
        return web.json_response(covers.catalog(), headers={'Cache-Control': 'no-store'})

    async def cover_asset(request):
        path = covers.asset(request.match_info['id'], request.match_info['size'])
        return web.FileResponse(path, headers={'Content-Type': 'image/webp',
                                               'X-Content-Type-Options': 'nosniff',
                                               'Cache-Control': 'no-store'})

    async def cover_select(request):
        require_cover_member(request)
        try:
            body = await request.clone(client_max_size=4096).json()
            ident = body.get('id')
        except (ValueError, AttributeError):
            raise web.HTTPBadRequest(text='封面信息无效')
        return web.json_response(await covers.select(ident))

    async def cover_delete(request):
        require_cover_member(request)
        return web.json_response(await covers.delete(request.match_info['id']))

    async def cover_upload(request):
        require_cover_member(request)
        if request.content_type != 'multipart/form-data':
            raise web.HTTPBadRequest(text='请选择图片文件')
        reader = await request.multipart()
        part = await reader.next()
        if part is None or part.name != 'cover' or not part.filename:
            raise web.HTTPBadRequest(text='请选择图片文件')
        return web.json_response(await covers.upload(part), status=201)

    async def login(request):
        # X-Real-IP is overwritten by our loopback-only reverse proxy.
        ip = request.headers.get('X-Real-IP', request.remote or 'unknown')
        now = time.monotonic()
        attempts[ip] = [t for t in attempts.get(ip, []) if now - t < 300]
        if len(attempts[ip]) >= 10:
            raise web.HTTPTooManyRequests(text='尝试过多，请五分钟后再试')
        if request.content_length and request.content_length > 4096:
            raise web.HTTPRequestEntityTooLarge(max_size=4096, actual_size=request.content_length)
        try:
            data = await request.clone(client_max_size=4096).json()
            supplied = data.get('password', '')
        except (ValueError, AttributeError):
            raise web.HTTPBadRequest(text='无效请求')
        code = None
        if 'room' in data:
            code = room_code(data['room'])
        elif not isinstance(supplied, str) or not hmac.compare_digest(supplied.encode(), password.encode()):
            # Preserve already-open old clients during the entry migration only.
            attempts[ip].append(now)
            raise web.HTTPUnauthorized(text='请使用房间码进入')
        attempts.pop(ip, None)
        response = web.json_response({'ok': True, **({'room': code} if code else {})})
        response.set_cookie('watch_session', signed(int(time.time()) + 7 * 86400),
                            httponly=True, secure=secure, samesite='Strict', max_age=7 * 86400)
        return response

    async def logout(request):
        response = web.json_response({'ok': True})
        response.del_cookie('watch_session')
        return response

    async def library(request):
        usage = os.statvfs(media)
        return web.json_response({'files': [{'name': n, 'bytes': p.stat().st_size}
                                           for n, p in sorted(files().items())],
                                  'free_bytes': usage.f_bavail * usage.f_frsize, 'reserve_bytes': reserve},
                                 headers={'Cache-Control': 'no-store'})

    async def stream(request):
        name = request.match_info['name']
        p = files().get(name)
        if p is None:
            raise web.HTTPNotFound()
        return web.FileResponse(p, headers={'Cache-Control': 'private, no-store',
                                            'X-Content-Type-Options': 'nosniff'})

    async def subtitle_list(request):
        name = request.match_info['name']
        if name not in files():
            raise web.HTTPNotFound(text='影片不存在')
        return web.json_response(list_subtitles(data_dir, name), headers={'Cache-Control': 'no-store'})

    async def subtitle_track(request):
        name = request.match_info['name']
        if name not in files():
            raise web.HTTPNotFound()
        path = subtitle_path(data_dir, name, request.match_info['track'])
        if path is None or path.suffix != '.' + request.match_info['extension']:
            raise web.HTTPNotFound()
        content_type = 'application/octet-stream' if path.suffix == '.sup' else 'text/vtt; charset=utf-8'
        return web.FileResponse(path, headers={'Content-Type': content_type,
                                               'Cache-Control': 'private, no-store',
                                               'X-Content-Type-Options': 'nosniff'})

    async def danmaku_history(request):
        name = request.match_info['name']
        if name not in available():
            raise web.HTTPNotFound()
        return web.json_response({'comments': comments.list(name, room_code(request.query.get('room','01')))}, headers={'Cache-Control': 'private, no-store'})

    async def delete_video(request):
        name = request.match_info['name']
        path = files().get(name)
        if path is None:
            raise web.HTTPNotFound(text='影片不存在或已经删除')
        try:
            path.unlink()
        except FileNotFoundError:
            raise web.HTTPNotFound(text='影片不存在或已经删除')
        remove_subtitles(data_dir, name)
        comments.remove(name)
        for room in list(rooms.values()):
            room.invalidate_source(name)
            room.library_version += 1
            await room.broadcast()
        return web.json_response({'ok': True, 'deleted': name})

    def validate_upload_name(original):
        if not isinstance(original, str):
            raise web.HTTPBadRequest(text='请选择视频文件')
        if (Path(original).name != original or '\\' in original or
                Path(original).suffix.lower() not in EXTENSIONS | CONVERSION_EXTENSIONS or len(original) > 180):
            raise web.HTTPBadRequest(text='仅支持 MP4 / M4V / WebM / MKV / AVI 文件')

    def check_conversion_capacity(original):
        if (Path(original).suffix.lower() in CONVERSION_EXTENSIONS and
                sum(j['status'] in ('queued', 'running') for j in list_jobs(data_dir)) >= 3):
            raise web.HTTPConflict(text='已有 3 个待处理任务，请等待处理完成')

    async def publish_upload(temporary, original, total):
        check_conversion_capacity(original)
        name = secrets.token_hex(4) + '-' + original
        if Path(original).suffix.lower() in CONVERSION_EXTENSIONS:
            disk = os.statvfs(media)
            if disk.f_bavail * disk.f_frsize < reserve + total * 1.25:
                raise web.HTTPInsufficientStorage(text='空间不足：视频处理需同时容纳原文件和输出文件，并保留 2 GiB')
            return web.json_response(enqueue(data_dir, temporary, original), status=202)
        temporary.chmod(0o644)
        temporary.replace(media / name)
        for room in list(rooms.values()):
            room.library_version += 1
            await room.broadcast()
        return web.json_response({'name': name, 'bytes': total}, status=201)

    async def upload(request):
        if upload_lock.locked() or parallel_uploads.active:
            raise web.HTTPConflict(text='已有上传任务，请稍后再试')
        async with upload_lock:
            reader = await request.multipart()
            part = await reader.next()
            if part is None or part.name != 'video' or not part.filename:
                raise web.HTTPBadRequest(text='请选择视频文件')
            original = part.filename
            validate_upload_name(original)
            check_conversion_capacity(original)
            temporary = media / ('.upload-' + secrets.token_hex(8))
            total = 0
            try:
                with temporary.open('xb') as f:
                    while chunk := await part.read_chunk(256 * 1024):
                        total += len(chunk)
                        if total > max_upload:
                            raise web.HTTPRequestEntityTooLarge(max_size=max_upload, actual_size=total)
                        disk = os.statvfs(media)
                        if disk.f_bavail * disk.f_frsize - len(chunk) < reserve:
                            raise web.HTTPInsufficientStorage(text='空间不足，保留 2 GiB 系统余量')
                        f.write(chunk)
                if total == 0:
                    raise web.HTTPBadRequest(text='空文件')
                return await publish_upload(temporary, original, total)
            finally:
                temporary.unlink(missing_ok=True)

    async def upload_start(request):
        if upload_lock.locked():
            raise web.HTTPConflict(text='已有上传任务，请稍后再试')
        try:
            raw = bytearray()
            async with asyncio.timeout(15):
                async for block in request.content.iter_chunked(1024):
                    if len(raw) + len(block) > 4096:
                        raise web.HTTPRequestEntityTooLarge(max_size=4096, actual_size=len(raw)+len(block))
                    raw.extend(block)
            body = json.loads(raw)
            if not isinstance(body, dict): raise ValueError()
        except (ValueError, TypeError):
            raise web.HTTPBadRequest(text='上传信息无效')
        except TimeoutError:
            raise web.HTTPRequestTimeout(text='上传信息读取超时')
        original = body.get('filename')
        validate_upload_name(original)
        check_conversion_capacity(original)
        async with upload_lock:
            return web.json_response(parallel_uploads.start(original, body.get('size')), status=201)

    async def upload_chunk(request):
        try: index = int(request.match_info['index'])
        except ValueError: raise web.HTTPBadRequest(text='分片编号无效')
        return web.json_response(await parallel_uploads.write(request.match_info['id'], index, request,
                                                             request.headers.get('X-Chunk-SHA256')))

    async def upload_complete(request):
        async with upload_lock:
            session = parallel_uploads.ready(request.match_info['id'])
            try:
                return await publish_upload(session.path, session.name, session.size)
            finally:
                parallel_uploads.cancel(session.ident)

    async def upload_cancel(request):
        parallel_uploads.cancel(request.match_info['id'])
        return web.json_response({'ok': True})

    async def conversions(request):
        jobs = list_jobs(data_dir)[:30]
        for job in jobs:
            if job.get('error'):
                job['error_code'] = 'conversion_failed'
        return web.json_response({'jobs': jobs}, headers={'Cache-Control': 'no-store'})

    async def cancel_conversion(request):
        job = next((j for j in list_jobs(data_dir) if j['id'] == request.match_info['id']), None)
        if job is None:
            raise web.HTTPNotFound(text='任务不存在')
        if job['status'] not in ('queued', 'running', 'failed'):
            raise web.HTTPConflict(text='已完成或已清理的任务不能取消')
        (data_dir / 'conversions' / (job['id'] + '.cancel')).write_text('cancel')
        return web.json_response({'ok': True}, status=202)

    async def voice_config(request):
        secret = os.environ.get('WATCH_TURN_SECRET','')
        urls = [u for u in os.environ.get('WATCH_TURN_URLS','').split(',') if u]
        if not secret or not urls:
            return web.json_response({'enabled':False,'iceServers':[]},headers={'Cache-Control':'private, no-store'})
        username = str(int(time.time())+43200)+':'+secrets.token_hex(6)
        credential = base64.b64encode(hmac.new(secret.encode(),username.encode(),hashlib.sha1).digest()).decode()
        return web.json_response({'enabled':True,'iceServers':[{'urls':urls,'username':username,'credential':credential}]},headers={'Cache-Control':'private, no-store'})

    async def websocket(request):
        room = resolve_room(room_code(request.query.get('room','01')))
        if len(room.clients) >= 8:
            raise web.HTTPServiceUnavailable(text='房间已满')
        ws = web.WebSocketResponse(heartbeat=20, max_msg_size=16384)
        await ws.prepare(request)
        peer = secrets.token_hex(8)
        room.clients[peer] = ws
        room.last_used = time.monotonic()
        name = ' '.join(request.query.get('name','朋友').split())[:20] or '朋友'
        room.members[peer] = dict(name=name,voice=False,muted=False)
        last_chat = -1000.0
        signal_times = []
        if room.host is None:
            room.host = peer
        member_token = secrets.token_urlsafe(32)
        cover_members[member_token] = (ws, request.cookies.get('watch_session'))
        try:
            try:
                memories = history.list(room.code)
            except sqlite3.Error:
                logging.exception('Could not read screening history')
                memories = []
            await ws.send_json({'memories':memories,'type':'hello','id':peer,'room':room.code,'chat':room.chat,'member_token':member_token})
            await room.broadcast()
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                try:
                    data = json.loads(msg.data)
                    if not isinstance(data, dict):
                        continue
                    if data.get('type') == 'control':
                        if room.update(peer, data, available()):
                            entry = None
                            if not room.paused and room.file != room.remembered_file:
                                try:
                                    entry = history.record(room.code, film_title(room.file, network))
                                    room.remembered_file = room.file
                                except sqlite3.Error:
                                    logging.exception('Could not save screening history')
                            await room.broadcast(entry)
                    elif data.get('type') == 'danmaku':
                        name = data.get('file')
                        now = time.monotonic()
                        try:
                            if name != room.file or name not in available():
                                raise ValueError('请先选择正在观看的影片')
                            if now - last_comment.get(peer, -1000) < 1.0:
                                raise ValueError('弹幕发送太快，每秒最多一条')
                            comment = comments.add(name, data.get('text'), room.snapshot()['position'], room.code)
                            last_comment[peer] = now
                            event = dict(type='danmaku', file=name, comment=comment, sender=peer)
                            for client in list(room.clients.values()):
                                try:
                                    await client.send_json(event)
                                except (ConnectionError, RuntimeError):
                                    pass
                        except ValueError as error:
                            await ws.send_json({'type': 'error', 'code': 'danmaku_invalid', 'error': str(error)})
                    elif data.get('type') == 'chat':
                        text = data.get('text')
                        now = time.monotonic()
                        if not isinstance(text,str) or not 1<=len(text.strip())<=300 or now-last_chat<.5:
                            await ws.send_json({'type':'error','code':'chat_invalid','error':'消息为1～300字，请勿连续刷屏'})
                            continue
                        last_chat = now
                        row = dict(id=secrets.token_hex(8),sender=peer,name=room.members[peer]['name'],text=text.strip(),time=time.time())
                        room.chat.append(row)
                        del room.chat[:-100]
                        await room.event(dict(type='chat',message=row))
                    elif data.get('type') in ('voice_join','voice_leave','voice_state'):
                        member = room.members[peer]
                        if data['type']=='voice_join':
                            member['voice'],member['muted'] = True,False
                        elif data['type']=='voice_leave':
                            member['voice'],member['muted'] = False,False
                        elif member['voice'] and isinstance(data.get('muted'),bool):
                            member['muted'] = data['muted']
                        await room.broadcast()
                    elif data.get('type') == 'signal':
                        target = data.get('to')
                        signal = data.get('signal')
                        now = time.monotonic()
                        signal_times = [t for t in signal_times if now-t<10]
                        if (not isinstance(target,str) or target==peer or target not in room.clients or
                            not room.members[peer]['voice'] or not room.members[target]['voice'] or
                            not isinstance(signal,dict) or len(json.dumps(signal))>12000 or len(signal_times)>=100):
                            continue
                        description = signal.get('description')
                        candidate = signal.get('candidate')
                        if description is not None:
                            if (not isinstance(description,dict) or description.get('type') not in ('offer','answer') or
                                not isinstance(description.get('sdp'),str) or len(description['sdp'])>10000 or 'm=video' in description['sdp']):
                                continue
                            signal = {'description':{'type':description['type'],'sdp':description['sdp']}}
                        elif not isinstance(candidate,dict) or not isinstance(candidate.get('candidate'),str):
                            continue
                        else:
                            if (len(candidate['candidate'])>3000 or
                                (candidate.get('sdpMid') is not None and (not isinstance(candidate['sdpMid'],str) or len(candidate['sdpMid'])>64)) or
                                (candidate.get('sdpMLineIndex') is not None and (isinstance(candidate['sdpMLineIndex'],bool) or not isinstance(candidate['sdpMLineIndex'],int) or not 0<=candidate['sdpMLineIndex']<=10)) or
                                (candidate.get('usernameFragment') is not None and (not isinstance(candidate['usernameFragment'],str) or len(candidate['usernameFragment'])>256))):
                                continue
                            signal = {'candidate':{k:v for k,v in candidate.items() if k in ('candidate','sdpMid','sdpMLineIndex','usernameFragment')}}
                        signal_times.append(now)
                        await room.clients[target].send_json(dict(type='signal',sender=peer,signal=signal))
                    elif data.get('type') == 'rate':
                        if room.set_rate(peer,data.get('rate'),data.get('file')):
                            await room.broadcast()
                    elif data.get('type') == 'boost':
                        if room.set_boost(peer, data.get('active'), data.get('file')):
                            await room.broadcast()
                    elif data.get('type') == 'claim':
                        room.reset_boost()
                        room.host = peer
                        await room.broadcast()
                    elif data.get('type') == 'ping':
                        await ws.send_json(room.snapshot())
                except (ValueError, TypeError):
                    continue
        finally:
            cover_members.pop(member_token, None)
            room.clients.pop(peer, None)
            room.members.pop(peer,None)
            room.last_used = time.monotonic()
            last_comment.pop(peer, None)
            if room.host == peer:
                room.reset_boost()
                room.host = next(iter(room.clients), None)
            if not room.clients:
                room.remembered_file = None
                room.position = room.snapshot()['position']
                room.updated = time.monotonic()
                room.paused = True
            await room.broadcast()
        return ws

    async def network_resolve(request):
        job = None
        try:
            body = await request.json()
            if not isinstance(body, dict) or not isinstance(body.get('url'), str) or len(body['url']) > 4096:
                raise ValueError('无效网址')
            job = asyncio.create_task(network.resolve(body['url'], body.get('mode', 'relay')))
            while not job.done():
                await asyncio.wait({job}, timeout=.25)
                if request.transport is None or request.transport.is_closing():
                    raise ConnectionResetError('解析客户端已断开')
            return web.json_response({'choices': await job, 'resources': network.stats()})
        except (ValueError, TypeError, AttributeError) as e:
            raise web.HTTPBadRequest(text=str(e), headers={'X-Cinema-Error': 'network_invalid'})
        except (RuntimeError, asyncio.TimeoutError, ConnectionError) as e:
            raise web.HTTPBadGateway(text=str(e)[:1600], headers={'X-Cinema-Error': 'network_resolve_failed'})
        finally:
            if job and not job.done():
                job.cancel()
                with suppress(asyncio.CancelledError):
                    await job

    async def network_describe(request):
        return web.json_response(network.describe(request.match_info['source_id']))

    async def network_complete(request):
        source = network.sources.get(request.match_info['source_id'])
        if source:
            source.completed = True
        return web.json_response({'ok': True})

    async def network_stats(request):
        return web.json_response(network.stats())

    app = web.Application(middlewares=[identify_errors, guard], client_max_size=max_upload + 1024**2)
    async def boost_watchdog(app):
        async def run():
            while True:
                await asyncio.sleep(0.2)
                for room in list(rooms.values()):
                    if room.expire_boost() or room.rate_dirty:
                        await room.broadcast()
                active = set()
                for room in list(rooms.values()):
                    if not room.file or not room.file.startswith('net:'):
                        continue
                    source = network.sources.get(room.file[4:])
                    if source:
                        duration = source.info.get('duration')
                        ended = source.completed or (room.paused and isinstance(duration,(int,float)) and duration>0 and room.snapshot()['position']>=duration-.5)
                        if room.clients and not ended:
                            active.add(room.file)
                await network.sweep(active)
                for room in list(rooms.values()):
                    source = room.file
                    if (source and source.startswith('net:') and source[4:] not in network.sources
                            and room.invalidate_source(source)):
                        await room.broadcast()
        task = asyncio.create_task(run())
        yield
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def network_lifecycle(app):
        await network.start()
        try:
            yield
        finally:
            await network.close()

    app.cleanup_ctx.append(parallel_uploads.lifecycle)
    app.cleanup_ctx.append(network_lifecycle)
    app.cleanup_ctx.append(boost_watchdog)
    app.router.add_get('/', index)
    async def health(request):
        return web.json_response({'ok': True})

    app.router.add_get('/healthz', health)
    app.router.add_get('/scenes/{name}', scene_asset)
    app.router.add_get('/room-art/{name}', room_art)
    app.router.add_get('/api/covers', cover_catalog)
    app.router.add_post('/api/covers', cover_upload)
    app.router.add_put('/api/covers/current', cover_select)
    app.router.add_delete('/api/covers/{id}', cover_delete)
    app.router.add_get('/covers/{id}/{size}.webp', cover_asset)
    app.router.add_post('/api/network/resolve', network_resolve)
    app.router.add_get('/api/network/stats', network_stats)
    app.router.add_get('/api/network/{source_id}/source', network_describe)
    app.router.add_post('/api/network/{source_id}/complete', network_complete)
    app.router.add_get('/api/network/{source_id}/play', network.play)
    app.router.add_get('/assets/{name}', player_asset)
    app.router.add_post('/api/login', login)
    app.router.add_post('/api/logout', logout)
    app.router.add_get('/api/library', library)
    app.router.add_get('/api/subtitles/{name}', subtitle_list)
    app.router.add_get('/api/subtitles/{name}/{track}.{extension}', subtitle_track)
    app.router.add_get('/api/danmaku/{name}', danmaku_history)
    app.router.add_delete('/api/library/{name}', delete_video)
    app.router.add_post('/api/upload', upload)
    app.router.add_post('/api/uploads', upload_start)
    app.router.add_put('/api/uploads/{id}/{index}', upload_chunk)
    app.router.add_post('/api/uploads/{id}/complete', upload_complete)
    app.router.add_delete('/api/uploads/{id}', upload_cancel)
    app.router.add_get('/api/conversions', conversions)
    app.router.add_post('/api/conversions/{id}/cancel', cancel_conversion)
    app.router.add_get('/media/{name}', stream)
    app.router.add_get('/ws', websocket)
    app.router.add_get('/api/voice-config',voice_config)
    return app


if __name__ == '__main__':
    web.run_app(create_app(), host='0.0.0.0', port=8080, access_log=None)
