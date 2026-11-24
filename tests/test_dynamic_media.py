import asyncio,unittest,tempfile,json,sys
from pathlib import Path
from aiohttp import web
from aiohttp.test_utils import TestServer
from yarl import URL
from cinema.external_media import ExternalMedia

class DynamicFallback(unittest.IsolatedAsyncioTestCase):
 async def test_html_without_static_video_uses_generic_fixed_worker(self):
  calls=[]
  async def dynamic(request):
   calls.append((request.path,await request.json(),request.headers.get('X-Extractor-Token')))
   return web.json_response({'choices':[{'url':'https://cdn.example/video.m3u8','kind':'hls','title':'dynamic','headers':{'User-Agent':'fixture-browser','Origin':'https://page.example'}}]})
  app=web.Application();app.router.add_post('/resolve-page',dynamic);worker=TestServer(app);await worker.start_server()
  class HTMLMedia(ExternalMedia):
   async def request(self,url,method='GET',headers=None):
    class Response:
     status=200;headers={'Content-Type':'text/html'};url=URL('https://page.example/watch')
     class Content:
      async def iter_chunked(self,n):yield b'<html><script>loadPlayer()</script><div id="player"></div></html>'
     content=Content()
     def release(self):pass
    return Response()
  media=HTMLMedia(str(worker.make_url('')).rstrip('/'),'fixture-token');await media.start()
  try:
   choices=await media.resolve('https://page.example/watch','relay');self.assertEqual(choices[0]['kind'],'hls');self.assertEqual(calls,[('/resolve-page',{'url':'https://page.example/watch'},'fixture-token')]);self.assertFalse(media.resolve_busy)
  finally:await media.close();await worker.close()

class GatewayPolicy(unittest.IsolatedAsyncioTestCase):
 async def test_private_urls_and_credentials_never_reach_transport(self):
  from cinema.browser_resolver import BrowserResolver
  from types import SimpleNamespace
  class Request:
   resource_type='xhr';method='GET';post_data_buffer=None
   async def all_headers(self):return {'cookie':'SECRET','authorization':'SECRET','referer':'https://page.example','user-agent':'browser'}
  class Route:
   def __init__(self,url):self.request=Request();self.request.url=url;self.aborted=False;self.result=None
   async def abort(self):self.aborted=True
   async def fulfill(self,**kwargs):self.result=kwargs
  class Content:
   async def read(self,n):raise AssertionError('media body must not be read')
  response=SimpleNamespace(status=200,headers={'Content-Type':'application/vnd.apple.mpegurl'},content=Content(),release=lambda:None)
  class Session:
   def __init__(self):self.calls=[]
   async def request(self,*args,**kwargs):self.calls.append((args,kwargs));return response
  session=Session();resolver=BrowserResolver(session)
  for url in ['https://127.0.0.1/a','https://169.254.169.254/a','https://localhost/a','http://example.com/a','https://user:pass@example.com/a']:
   route=Route(url);await resolver.route(route);self.assertTrue(route.aborted)
  self.assertEqual(session.calls,[])
  route=Route('https://cdn.example/a%3Bb%3D1/index.m3u8');await resolver.route(route)
  self.assertTrue(route.aborted);self.assertEqual(resolver.received,0);self.assertEqual(len(resolver.choices),1)
  args,kwargs=session.calls[0];self.assertEqual(str(args[1]),route.request.url);self.assertNotIn('cookie',kwargs['headers']);self.assertNotIn('authorization',kwargs['headers']);self.assertEqual(resolver.choices[0]['headers']['Referer'],'https://page.example')

 async def test_body_and_total_budget_are_bounded(self):
  from cinema.browser_resolver import BrowserResolver,MAX_RESPONSE,MAX_TOTAL
  from types import SimpleNamespace
  class Content:
   async def read(self,n):return b'x'*n
  resolver=BrowserResolver(object());response=SimpleNamespace(content=Content())
  with self.assertRaises(ValueError):await resolver.read(response)
  self.assertLessEqual(resolver.received,MAX_RESPONSE+1);self.assertLessEqual(resolver.spent,MAX_TOTAL)

class ExtractorPageLifecycle(unittest.IsolatedAsyncioTestCase):
 async def test_worker_page_job_timeout_and_secret_not_inherited(self):
  from cinema.extractor import Extractor
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as root:
   engine=Extractor(timeout=5,temp_root=root)
   with patch.dict('os.environ',{'WATCH_PASSWORD':'NEVER-PASS-TO-CHILD','PYTHONPATH':'/untrusted-search-path'}):
    result=await engine.execute([sys.executable,'-c','from cinema.browser_resolver import BrowserResolver; import os,json; print(json.dumps({"secret":os.getenv("WATCH_PASSWORD"),"cwd":os.getcwd(),"path":os.getenv("PYTHONPATH")}))'],'https://example.com')
   self.assertIsNone(result['secret'])
   self.assertEqual(Path(result['cwd']).parent,Path(root).resolve())
   self.assertEqual(Path(result['path']),Path(__file__).resolve().parents[1])
   engine.timeout=.05
   with self.assertRaises(RuntimeError):await engine.execute([sys.executable,'-c','import time;time.sleep(20)'],'https://example.com')
   self.assertFalse(engine.busy);self.assertIsNone(engine.pid);self.assertEqual(list(Path(root).iterdir()),[])
