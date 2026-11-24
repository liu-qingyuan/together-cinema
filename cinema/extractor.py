"""Bounded trusted-tool execution; never stores video files or browser cookies."""
import asyncio,contextlib,hmac,json,os,re,signal,sys,tempfile
from pathlib import Path
import ctypes
from urllib.parse import urlsplit,parse_qs
from aiohttp import web
from .external_media import public_url
MAX_OUTPUT=4*1024*1024
class Extractor:
 def __init__(self,command=None,timeout=35,temp_root='/tmp'):
  self.command=command or [sys.executable,'-m','yt_dlp','--no-cache-dir','--no-playlist','--skip-download','--socket-timeout','8','--retries','0','--extractor-retries','0','--js-runtimes','node:/usr/local/bin/node','--dump-single-json']
  self.timeout=timeout;self.temp_root=temp_root;self.busy=False;self.pid=None;self.healthy=True
  if sys.platform=='linux' and ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)!=0:raise OSError(ctypes.get_errno(),'cannot enable job child subreaper')
 async def resolve(self,url):
  parsed=urlsplit(url);query=parse_qs(parsed.query)
  if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in (None,443):raise ValueError('仅支持HTTPS YouTube视频地址')
  if parsed.hostname in ('youtube.com','www.youtube.com','m.youtube.com'):
   video_id=query.get('v',[''])[0] if parsed.path=='/watch' else parsed.path.split('/')[-1] if parsed.path.startswith(('/shorts/','/embed/')) else ''
  elif parsed.hostname=='youtu.be':video_id=parsed.path.strip('/')
  else:raise ValueError('此解析器仅支持YouTube视频')
  if not re.fullmatch(r'[A-Za-z0-9_-]{11}',video_id):raise ValueError('无效YouTube视频地址')
  data=await self.execute(self.command,'https://www.youtube.com/watch?v='+video_id)
  return self.candidates(data)
 async def resolve_page(self,url):
  public_url(url)
  command=[sys.executable,'-m','cinema.browser_resolver']
  return (await self.execute(command,url))['choices']
 async def execute(self,command,url):
  if not self.healthy:raise RuntimeError('解析子进程回收异常，已禁止新任务，请重启解析容器')
  if self.busy:raise RuntimeError('已有视频正在解析，请稍后重试')
  self.busy=True;process=None;readers=[]
  try:
   with tempfile.TemporaryDirectory(prefix='watch-extract-',dir=self.temp_root) as temporary:
    env={'PATH':os.environ.get('PATH','/usr/local/bin:/usr/bin:/bin'),'LANG':'C.UTF-8','HOME':temporary,'TMPDIR':temporary,'NODE_OPTIONS':'--max-old-space-size=96','PLAYWRIGHT_BROWSERS_PATH':os.environ.get('PLAYWRIGHT_BROWSERS_PATH','/ms-playwright')}
    # Keep the private job cwd while allowing only our trusted package root, not an inherited search path.
    env['PYTHONPATH']=str(Path(__file__).resolve().parent.parent)
    process=await asyncio.create_subprocess_exec(*command,url,cwd=temporary,env=env,start_new_session=True,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    self.pid=process.pid
    async def bounded(stream,limit):
     chunks=[];size=0
     while chunk:=await stream.read(32768):
      size+=len(chunk)
      if size>limit:raise RuntimeError('解析输出超出资源上限')
      chunks.append(chunk)
     return b''.join(chunks)
    readers=[asyncio.create_task(bounded(process.stdout,MAX_OUTPUT)),asyncio.create_task(bounded(process.stderr,65536))]
    try:
     stdout,stderr,_=await asyncio.wait_for(asyncio.gather(*readers,process.wait()),self.timeout)
     if process.returncode:raise RuntimeError('片源解析失败：'+(stderr.decode(errors='replace')[:900]+'\n'+stderr.decode(errors='replace')[-900:]))
     data=json.loads(stdout)
     return data
    except asyncio.TimeoutError:raise RuntimeError('解析超时，子进程已回收')
    finally:
     with contextlib.suppress(ProcessLookupError):os.killpg(process.pid,signal.SIGKILL)
     await self.reap_children(process)
     if process.returncode is None:await asyncio.shield(process.wait())
     for task in readers:
      if not task.done():task.cancel()
     await asyncio.gather(*readers,return_exceptions=True)
  finally:self.busy=False;self.pid=None
 async def reap_children(self,process):
  if sys.platform!='linux':return
  children=Path('/proc/self/task')/str(os.getpid())/'children'
  for _ in range(300):
   pids=[int(value) for value in children.read_text().split() if int(value)!=process.pid]
   for pid in pids:
    with contextlib.suppress(ProcessLookupError):os.kill(pid,signal.SIGKILL)
    with contextlib.suppress(ChildProcessError):os.waitpid(pid,os.WNOHANG)
   if not pids and process.returncode is not None:return
   await asyncio.sleep(.01)
  self.healthy=False
  raise RuntimeError('解析后代未完全回收，已禁止新任务')
 @staticmethod
 def candidates(data):
  formats=data.get('formats') or []
  def usable(f):return isinstance(f.get('url'),str) and f['url'].startswith('https://') and f.get('protocol') in ('https','m3u8','m3u8_native')
  audio=next((f for f in reversed(formats) if usable(f) and f.get('vcodec')=='none' and (str(f.get('acodec','')).startswith('mp4a') or (f.get('acodec') is None and f.get('ext')=='mp4')) and f.get('protocol') in ('m3u8','m3u8_native')),None)
  choices=[];heights=set()
  for f in reversed(formats):
   if not usable(f) or not str(f.get('vcodec','')).startswith(('avc1','h264')):continue
   height=f.get('height') or 0
   if not 0<height<=720 or height in heights:continue
   if f.get('acodec') not in ('none',None):kind='hls' if f['protocol'].startswith('m3u8') else 'mp4';a=None
   elif audio and f['protocol'].startswith('m3u8'):kind='hls';a=audio
   else:continue
   choices.append({'title':str(data.get('title') or data.get('id') or 'YouTube视频')[:180],'duration':data.get('duration'),'height':height,'width':f.get('width'),'bitrate':int((f.get('tbr') or 1500)*1000),'codec':f.get('vcodec'),'audio_codec':a.get('acodec') if a else f.get('acodec'),'url':f['url'],'audio_url':a['url'] if a else None,'kind':kind})
   heights.add(height)
   if len(choices)>=5:break
  if not choices:raise RuntimeError('未找到本版本支持的H.264/AAC网络片源；没有下载或转码视频')
  return choices

def create_app(engine=None,token=None):
 engine=engine or Extractor();token=token or os.environ['WATCH_PASSWORD']
 async def resolve(request):
  if not hmac.compare_digest(request.headers.get('X-Extractor-Token',''),token):raise web.HTTPForbidden()
  try:
   body=await request.json();url=body.get('url');
   if not isinstance(url,str) or len(url)>4096:raise ValueError('无效网址')
   method=engine.resolve_page if request.path=='/resolve-page' else engine.resolve
   return web.json_response({'choices':await method(url)})
  except (ValueError,AttributeError,json.JSONDecodeError) as e:raise web.HTTPBadRequest(text=str(e))
  except RuntimeError as e:raise web.HTTPBadGateway(text=str(e))
 app=web.Application(client_max_size=8192);app.router.add_post('/resolve',resolve);app.router.add_post('/resolve-page',resolve)
 async def health(request):return web.json_response({'ok':getattr(engine,'healthy',True),'busy':engine.busy})
 app.router.add_get('/healthz',health)
 return app
if __name__=='__main__':
 os.nice(10)
 web.run_app(create_app(),host='0.0.0.0',port=8081,access_log=None,handler_cancellation=True)
