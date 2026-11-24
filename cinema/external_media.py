"""HTTPS-only media catalogue and backpressured relay. No disk media cache."""
import asyncio,base64,hashlib,hmac,ipaddress,json,re,secrets,socket,time
from dataclasses import dataclass,field
from collections import OrderedDict
from html.parser import HTMLParser
from urllib.parse import urlsplit,urljoin,quote
import aiohttp
from aiohttp import web
from aiohttp.abc import AbstractResolver
from yarl import URL
MAX_SOURCES=16
MAX_MANIFEST=1024*1024
CHUNK_SIZE=32768

def public_url(value):
 if not isinstance(value,str) or len(value)>16384 or any(ord(c)<32 for c in value):raise ValueError('无效网络网址')
 try:
  p=urlsplit(value)
  if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443):raise ValueError('只支持不含账号密码的HTTPS地址')
  try:address=ipaddress.ip_address(p.hostname)
  except ValueError:address=None
  if address and (not address.is_global or address.is_multicast):raise ValueError('禁止本机、内网或特殊网络地址')
  if p.hostname.lower() in ('localhost','localhost.localdomain') or p.hostname.lower().endswith(('.localhost','.local','.internal')):raise ValueError('禁止内网地址')
 except (ValueError,TypeError) as e:raise ValueError(str(e))
 return value
class PublicResolver(AbstractResolver):
 async def resolve(self,host,port=443,family=socket.AF_INET):
  rows=await asyncio.get_running_loop().getaddrinfo(host,port,type=socket.SOCK_STREAM,family=family)
  result=[]
  for f,_,proto,_,address in rows:
   ip=ipaddress.ip_address(address[0])
   if not ip.is_global or ip.is_multicast:raise OSError('目标DNS包含内网或特殊地址')
   result.append(dict(hostname=host,host=str(ip),port=port,family=f,proto=proto,flags=0))
  if not result:raise OSError('目标无法解析')
  return result
 async def close(self):pass
class VideoLinks(HTMLParser):
 def __init__(self):super().__init__();self.urls=[]
 def handle_starttag(self,tag,attrs):
  if tag in ('video','source'):
   value=dict(attrs).get('src')
   if value and len(self.urls)<8:self.urls.append(value)
@dataclass
class Source:
 id:str
 info:dict
 mode:str
 page:str
 secret:bytes=field(default_factory=lambda:secrets.token_bytes(32))
 touched:float=field(default_factory=time.monotonic)
 was_active:bool=False
 completed:bool=False
 tasks:set=field(default_factory=set)
@dataclass
class FragmentData:
    body: bytes
    status: int
    headers: dict

class SharedFragments:
    """Bounded source-scoped fragments; coalesce loads and own their cancellation."""
    LIMIT = 16 * 1024**2
    FRAGMENT_LIMIT = 2 * 1024**2
    LOAD_RESERVATION = 2 * FRAGMENT_LIMIT
    MAX_ENTRIES = 128
    TTL = 45

    def __init__(self):
        self.entries = OrderedDict()
        self.jobs = {}
        self.bytes = self.reserved = 0
        self.hits = self.coalesced = self.loads = self.skips = 0

    def _remove(self, key):
        data, _ = self.entries.pop(key)
        self.bytes -= len(data.body)

    def sweep(self):
        now = time.monotonic()
        for key, (_, expires) in list(self.entries.items()):
            if expires <= now:
                self._remove(key)

    def _unreserve(self, job):
        if job['reserved']:
            self.reserved -= self.LOAD_RESERVATION
            job['reserved'] = False

    async def _load(self, key, loader, job):
        try:
            data = await loader()
            if data is not None:
                self.sweep()
                while len(self.entries) >= self.MAX_ENTRIES:
                    self._remove(next(iter(self.entries)))
                self.entries[key] = (data, time.monotonic() + self.TTL)
                self.bytes += len(data.body)
            else:
                self.skips += 1
            return data
        finally:
            self._unreserve(job)

    async def obtain(self, key, loader, alive):
        self.sweep()
        if key in self.entries:
            self.hits += 1
            self.entries.move_to_end(key)
            return self.entries[key][0]
        job = self.jobs.get(key)
        if job is None:
            while self.entries and self.bytes + self.reserved + self.LOAD_RESERVATION > self.LIMIT:
                self._remove(next(iter(self.entries)))
            if self.bytes + self.reserved + self.LOAD_RESERVATION > self.LIMIT:
                self.skips += 1
                return None
            self.reserved += self.LOAD_RESERVATION
            self.loads += 1
            job = {'waiters': 0, 'reserved': True}
            job['task'] = asyncio.create_task(self._load(key, loader, job))
            job['task'].add_done_callback(lambda _: self._unreserve(job))
            self.jobs[key] = job
        else:
            self.coalesced += 1
        job['waiters'] += 1
        task = job['task']
        try:
            while not task.done():
                if not alive():
                    raise asyncio.CancelledError
                await asyncio.wait({task}, timeout=.1)
            if not alive():
                raise asyncio.CancelledError
            return task.result()
        finally:
            job['waiters'] -= 1
            if not job['waiters']:
                if self.jobs.get(key) is job:
                    self.jobs.pop(key)
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def release(self, source_id):
        tasks = [job['task'] for key, job in list(self.jobs.items()) if key[0] == source_id]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for key in list(self.entries):
            if key[0] == source_id:
                self._remove(key)

    def stats(self):
        return {'bytes': self.bytes, 'reserved_bytes': self.reserved,
                'limit_bytes': self.LIMIT, 'fragment_limit_bytes': self.FRAGMENT_LIMIT,
                'ttl_seconds': self.TTL, 'entries': len(self.entries),
                'inflight': sum(not job['task'].done() for job in self.jobs.values()),
                'hits': self.hits, 'coalesced': self.coalesced,
                'upstream_fetches': self.loads, 'skips': self.skips}

class ExternalMedia:
 def __init__(self,extractor_url,token,resolver=None,daily_limit=5*1024**3):
  self.extractor_url=extractor_url;self.token=token;self.resolver=resolver or PublicResolver();self.session=None;self.internal=None;self.sources={};self.sem=asyncio.Semaphore(6);self.resolve_busy=False;self.daily_limit=daily_limit;self.bytes_sent=0;self.period=time.monotonic();self.streams=0;self.fragments=SharedFragments()
 async def start(self):
  self.internal=aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=1),timeout=aiohttp.ClientTimeout(total=42),trust_env=False)
  self.session=aiohttp.ClientSession(connector=aiohttp.TCPConnector(resolver=self.resolver,limit=8,limit_per_host=4,use_dns_cache=False),timeout=aiohttp.ClientTimeout(total=90,connect=10,sock_read=20),trust_env=False,auto_decompress=False)
 async def close(self):
  for source_id in list(self.sources):await self.release(source_id)
  if self.session:await self.session.close();self.session=None
  if self.internal:await self.internal.close();self.internal=None
 async def request(self,url,method='GET',headers=None):
  public_url(url)
  for _ in range(4):
   response=await self.session.request(method,URL(url,encoded=True),allow_redirects=False,headers={'User-Agent':'Mozilla/5.0','Accept-Encoding':'identity',**(headers or {})})
   if response.status in (301,302,303,307,308):
    location=response.headers.get('Location','');response.release();url=public_url(urljoin(url,location));continue
   return response
  raise ValueError('跳转次数超出限制')
 async def limited(self,response):
  chunks=[];size=0
  async for chunk in response.content.iter_chunked(CHUNK_SIZE):
   size+=len(chunk)
   if size>MAX_MANIFEST:raise ValueError('网页或播放列表超出1MiB上限')
   chunks.append(chunk)
  return b''.join(chunks)
 async def resolve(self,url,mode):
  public_url(url)
  if mode not in ('direct','relay'):raise ValueError('请选择直连或中转')
  if self.resolve_busy:raise RuntimeError('已有网址正在解析，请稍后重试')
  if len(self.sources)>=MAX_SOURCES:raise RuntimeError('网络片源数量达到上限，请清理未使用片源')
  self.resolve_busy=True
  try:
   host=urlsplit(url).hostname
   if host in ('youtube.com','www.youtube.com','m.youtube.com','youtu.be'):
    # Internal extractor is a fixed trusted endpoint, never a user URL.
    async with self.internal.post(self.extractor_url+'/resolve',json={'url':url},headers={'X-Extractor-Token':self.token},timeout=aiohttp.ClientTimeout(total=42)) as response:
     body=await self.limited(response)
     if response.status!=200:raise RuntimeError(body.decode(errors='replace')[-1600:])
     choices=json.loads(body)['choices']
   else:
    response=await self.request(url)
    try:
     if response.status not in (200,206):raise ValueError('原站返回HTTP '+str(response.status))
     content=response.headers.get('Content-Type','').split(';')[0];path=urlsplit(str(response.url)).path.lower()
     if content.startswith('video/') or path.endswith(('.mp4','.webm','.m3u8')) or 'mpegurl' in content:
      choices=[{'url':str(response.url),'kind':'hls' if 'mpegurl' in content or path.endswith('.m3u8') else 'mp4','title':path.rsplit('/',1)[-1] or '网络视频'}]
     else:
      parser=VideoLinks();parser.feed((await self.limited(response)).decode('utf-8',errors='replace'));choices=[{'url':urljoin(str(response.url),value),'kind':'hls' if '.m3u8' in urlsplit(value).path.lower() else 'mp4','title':'网页视频 '+str(i+1)} for i,value in enumerate(parser.urls)]
    finally:response.release()
   if not choices:
    async with self.internal.post(self.extractor_url+'/resolve-page',json={'url':url},headers={'X-Extractor-Token':self.token},timeout=aiohttp.ClientTimeout(total=42)) as response:
     body=await self.limited(response)
     if response.status!=200:raise RuntimeError(body.decode(errors='replace')[-1600:])
     choices=json.loads(body)['choices']
   if not choices:raise ValueError('未发现可播放的公开媒体')
   registered=[]
   for choice in choices[:min(5,MAX_SOURCES-len(self.sources))]:
    public_url(choice['url'])
    if choice.get('audio_url'):public_url(choice['audio_url'])
    source_id=secrets.token_hex(12);self.sources[source_id]=Source(source_id,choice,mode,url);registered.append(self.describe(source_id))
   return registered
  finally:self.resolve_busy=False
 def describe(self,source_id):
  source=self.sources.get(source_id)
  if not source:raise web.HTTPGone(text='网络片源已过期，请重新解析',headers={'X-Cinema-Error':'source_expired'})
  source.touched=time.monotonic();info=source.info
  path=f'/api/network/{source_id}/play'
  return {'file':'net:'+source_id,'title':str(info.get('title') or '网络视频')[:180],'height':info.get('height'),'duration':info.get('duration'),'kind':info['kind'],'mode':source.mode,'url':info['url'] if source.mode=='direct' and info['kind']=='mp4' else path}
 def link(self,source,url):
  public_url(url)
  if source.mode=='direct':return url
  encoded=base64.urlsafe_b64encode(url.encode()).decode().rstrip('=');signature=hmac.new(source.secret,url.encode(),hashlib.sha256).hexdigest()
  return f'/api/network/{source.id}/play?u={quote(encoded)}&s={signature}'
 def rewrite(self,source,body,url):
  text=body.decode('utf-8-sig')
  if not text.lstrip().startswith('#EXTM3U'):raise ValueError('原站返回的不是HLS播放列表')
  if re.search(r'KEYFORMAT="(?!identity")',text):raise ValueError('本版本不处理DRM播放列表')
  lines=[]
  for line in text.splitlines():
   if line and not line.startswith('#'):line=self.link(source,urljoin(url,line.strip()))
   elif 'URI="' in line:line=re.sub(r'URI="([^"]+)"',lambda m:'URI="'+self.link(source,urljoin(url,m[1]))+'"',line)
   lines.append(line)
  return '\n'.join(lines)+'\n'
 async def release(self,source_id):
  source=self.sources.pop(source_id,None)
  if not source:return
  await self.fragments.release(source_id)
  current=asyncio.current_task();tasks=[task for task in list(source.tasks) if task is not current and not task.done()]
  for task in tasks:task.cancel()
  if tasks:await asyncio.gather(*tasks,return_exceptions=True)
 async def sweep(self,active):
  self.fragments.sweep()
  now=time.monotonic()
  for source_id,source in list(self.sources.items()):
   if 'net:'+source_id in active:source.was_active=True
   elif source.was_active or now-source.touched>120:await self.release(source_id)
 def stats(self):return {'sources':len(self.sources),'streams':self.streams,'resolve_busy':self.resolve_busy,'video_disk_cache_bytes':0,'bytes_relayed_24h':self.bytes_sent,'daily_limit':self.daily_limit,'max_sources':MAX_SOURCES,'max_streams':6,'shared_cache':self.fragments.stats()}
 async def load_fragment(self,url,headers):
  response=await self.request(url,'GET',headers)
  try:
   if response.status not in (200,206):raise ValueError('原站拒绝请求 HTTP '+str(response.status))
   content=response.headers.get('Content-Type','');size=response.content_length
   if ('mpegurl' in content or urlsplit(str(response.url)).path.lower().endswith('.m3u8')
       or response.headers.get('Content-Encoding','identity')!='identity'
       or (size is not None and not 0<size<=self.fragments.FRAGMENT_LIMIT)):return None
   chunks=[];received=0
   async for chunk in response.content.iter_chunked(CHUNK_SIZE):
    received+=len(chunk)
    if received>self.fragments.FRAGMENT_LIMIT:return None
    chunks.append(chunk)
   if size is not None and received!=size:raise ValueError('分片未完整接收')
   if not received:return None
   body=b''.join(chunks)
   outgoing={key:response.headers[key] for key in ['Content-Type','Content-Length','Content-Range','Accept-Ranges'] if key in response.headers}
   outgoing['Cache-Control']='no-store';outgoing['Content-Length']=str(received)
   return FragmentData(body,response.status,outgoing)
  finally:response.release()
 async def play(self,request):
  source=self.sources.get(request.match_info['source_id'])
  if not source:raise web.HTTPGone(text='片源已释放，请重新解析',headers={'X-Cinema-Error':'source_expired'})
  if self.sem.locked():raise web.HTTPTooManyRequests(text='中转并发达到上限',headers={'X-Cinema-Error':'relay_busy'})
  if time.monotonic()-self.period>86400:self.bytes_sent=0;self.period=time.monotonic()
  if self.bytes_sent>=self.daily_limit:raise web.HTTPTooManyRequests(text='中转24小时流量额度已用完',headers={'X-Cinema-Error':'relay_quota'})
  source.touched=time.monotonic();source.was_active=True;url=source.info['url'];encoded=request.query.get('u')
  if encoded:
   try:url=base64.urlsafe_b64decode(encoded+'='*((-len(encoded))%4)).decode()
   except Exception:raise web.HTTPBadRequest(text='无效片源链接')
   if len(url)>16384 or not hmac.compare_digest(request.query.get('s',''),hmac.new(source.secret,url.encode(),hashlib.sha256).hexdigest()):raise web.HTTPForbidden(text='片源签名无效')
  elif source.info.get('audio_url'):
   info=source.info;video=self.link(source,info['url']);audio=self.link(source,info['audio_url']);codec=str(info.get('codec') or 'avc1.4D401F');acodec=str(info.get('audio_codec') or '')
   if not re.fullmatch(r'[A-Za-z0-9._-]+',codec+acodec):raise web.HTTPBadGateway(text='不支持的编码标记')
   codecs=f',CODECS="{codec},{acodec}"' if acodec else ''
   body=f'#EXTM3U\n#EXT-X-VERSION:6\n#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="Audio",DEFAULT=YES,AUTOSELECT=YES,URI="{audio}"\n#EXT-X-STREAM-INF:BANDWIDTH={int(info.get("bitrate") or 1500000)}{codecs},AUDIO="audio"\n{video}\n'
   return web.Response(text=body,content_type='application/vnd.apple.mpegurl',headers={'Cache-Control':'no-store'})
  task=asyncio.current_task();source.tasks.add(task)
  try:
   async with self.sem:
    self.streams+=1;response=None
    try:
     headers=source.info.get('headers',{'Referer':source.page}).copy();byte_range=request.headers.get('Range')
     if byte_range:
      if not re.fullmatch(r'bytes=\d+-\d*',byte_range):raise web.HTTPBadRequest(text='仅支持单段字节范围')
      headers['Range']=byte_range
     if source.mode=='relay' and source.info['kind']=='hls' and encoded and request.method=='GET' and not urlsplit(url).path.lower().endswith('.m3u8'):
      key=(source.id,hashlib.sha256(url.encode()).digest(),byte_range)
      alive=lambda:request.transport is not None and not request.transport.is_closing()
      data=await self.fragments.obtain(key,lambda:self.load_fragment(url,headers),alive)
      if data is not None:
       downstream=web.StreamResponse(status=data.status,headers=data.headers);await downstream.prepare(request)
       view=memoryview(data.body)
       for offset in range(0,len(view),CHUNK_SIZE):
        chunk=view[offset:offset+CHUNK_SIZE]
        if self.bytes_sent+len(chunk)>self.daily_limit:raise ConnectionResetError('中转流量额度已达上限')
        self.bytes_sent+=len(chunk);await downstream.write(chunk)
       await downstream.write_eof();return downstream
     response=await self.request(url,request.method,headers)
     if response.status not in (200,206):raise web.HTTPBadGateway(text='原站拒绝请求 HTTP '+str(response.status))
     content=response.headers.get('Content-Type','application/octet-stream');manifest='mpegurl' in content or urlsplit(str(response.url)).path.lower().endswith('.m3u8')
     if manifest:
      text=self.rewrite(source,await self.limited(response),str(response.url));return web.Response(text=text,content_type='application/vnd.apple.mpegurl',headers={'Cache-Control':'no-store'})
     outgoing={key:response.headers[key] for key in ['Content-Type','Content-Length','Content-Range','Accept-Ranges'] if key in response.headers};outgoing['Cache-Control']='no-store';downstream=web.StreamResponse(status=response.status,headers=outgoing);await downstream.prepare(request)
     if request.method!='HEAD':
      async for chunk in response.content.iter_chunked(CHUNK_SIZE):
       if self.bytes_sent+len(chunk)>self.daily_limit:raise ConnectionResetError('中转流量额度已达上限')
       self.bytes_sent+=len(chunk);await downstream.write(chunk)
     await downstream.write_eof();return downstream
    finally:
     if response:response.release()
     self.streams-=1
  except (aiohttp.ClientError,asyncio.TimeoutError,ValueError) as e:raise web.HTTPBadGateway(text='网络片源错误：'+str(e)[:400],headers={'X-Cinema-Error':'network_source_failed'})
  finally:source.tasks.discard(task)
