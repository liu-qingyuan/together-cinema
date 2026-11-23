"""Ephemeral, budgeted public-page media discovery. No site-specific adapters."""
import asyncio,json,os,sys
from urllib.parse import urlsplit
from pathlib import Path
import aiohttp
from yarl import URL
from external_media import public_url,PublicResolver
MAX_REQUESTS=120
MAX_TOTAL=16*1024**2
MAX_RESPONSE=2*1024**2
MAX_POST=16384
FORWARD=('user-agent','referer','origin','accept','content-type','range')
MEDIA_HEADERS=('user-agent','referer','origin')
class BrowserResolver:
    def __init__(self,session=None):
        self.session=session
        self.count=0;self.spent=0;self.received=0;self.blocked=0
        self.choices=[];self.seen=set();self.ready=asyncio.Event();self.failure=None
        self.sem=asyncio.Semaphore(4)

    def fail(self,message):
        self.failure=message;self.ready.set()

    def record(self,url,kind,headers):
        public_url(url)
        if url in self.seen or len(self.choices)>=5:return
        self.seen.add(url)
        selected={key.title():headers[key] for key in MEDIA_HEADERS if key in headers}
        self.choices.append({'url':url,'kind':kind,'title':'网页动态视频 '+str(len(self.choices)+1),'headers':selected})
        self.ready.set()

    async def read(self,response):
        size=0;chunks=[]
        while True:
            take=min(32768,MAX_TOTAL-self.spent,MAX_RESPONSE+1-size)
            if take<=0:raise ValueError('动态页面超过传输预算')
            self.spent+=take
            chunk=b''
            try:chunk=await response.content.read(take)
            finally:self.spent-=take-len(chunk)
            self.received+=len(chunk);size+=len(chunk)
            if size>MAX_RESPONSE:raise ValueError('动态页面单个响应超过2MiB')
            if not chunk:return b''.join(chunks)
            chunks.append(chunk)

    async def route(self,route):
        request=route.request;response=None
        try:
            self.count+=1
            if self.count>MAX_REQUESTS:raise ValueError('动态页面请求次数超过120次')
            public_url(request.url)
            if request.resource_type in ('image','font'):
                self.blocked+=1;return await route.abort()
            if request.method not in ('GET','HEAD','POST'):
                self.blocked+=1;return await route.abort()
            post=request.post_data_buffer
            if post and len(post)>MAX_POST:raise ValueError('动态页面请求正文超过16KiB')
            incoming=await request.all_headers()
            headers={k:incoming[k] for k in FORWARD if k in incoming and len(incoming[k])<=4096}
            headers['Accept-Encoding']='identity'
            async with self.sem:
                # Browser handles redirects as new routed requests. No browser network fallback.
                response=await self.session.request(request.method,URL(request.url,encoded=True),headers=headers,data=post,allow_redirects=False)
                content=response.headers.get('Content-Type','').lower()
                path=urlsplit(request.url).path.lower()
                if response.status in (200,206):
                    if 'mpegurl' in content or path.endswith('.m3u8'):
                        self.record(request.url,'hls',incoming);return await route.abort()
                    if path.endswith(('.mp4','.webm','.mov')) or content.startswith(('video/','audio/')) or request.resource_type=='media':
                        self.record(request.url,'mp4',incoming);return await route.abort()
                    if path.endswith('.mpd') or 'dash+xml' in content:
                        self.blocked+=1;return await route.abort()
                body=await self.read(response)
                if response.status==200 and body.lstrip().startswith(b'#EXTM3U'):
                    self.record(request.url,'hls',incoming);return await route.abort()
                outgoing={k:v for k,v in response.headers.items() if k.lower() not in ('content-length','transfer-encoding','connection','content-encoding')}
                # Accept-Encoding identity; do not silently corrupt an unexpectedly compressed body.
                if response.headers.get('Content-Encoding'):
                    outgoing['Content-Encoding']=response.headers['Content-Encoding']
                await route.fulfill(status=response.status,headers=outgoing,body=body)
        except asyncio.CancelledError:raise
        except ValueError as e:
            # A private/subnet attempt is denied but does not grant or expand access.
            self.blocked+=1
            if '超过' in str(e):self.fail(str(e))
            try:await route.abort()
            except Exception:pass
        except (aiohttp.ClientError,OSError,asyncio.TimeoutError):
            self.blocked+=1
            try:await route.abort()
            except Exception:pass
        finally:
            if response is not None:response.release()

    async def discover(self,url):
        public_url(url)
        if sys.platform=='linux':
            available=next(int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
            if available<512*1024**2:raise RuntimeError('当前可用内存不足，已保留现有播放，请稍后解析动态网页')
        from playwright.async_api import async_playwright
        owned=self.session is None
        if owned:
            self.session=aiohttp.ClientSession(connector=aiohttp.TCPConnector(resolver=PublicResolver(),limit=4,use_dns_cache=False),timeout=aiohttp.ClientTimeout(total=12,connect=6,sock_read=8),auto_decompress=False,trust_env=False)
        try:
            async with async_playwright() as playwright:
                browser=await playwright.chromium.launch(headless=True,chromium_sandbox=True,
                    proxy={'server':'http://127.0.0.1:9'},
                    args=['--proxy-bypass-list=<-loopback>','--host-resolver-rules=MAP * ~NOTFOUND',
                          '--disable-quic','--force-webrtc-ip-handling-policy=disable_non_proxied_udp',
                          '--disable-gpu','--disable-software-rasterizer','--renderer-process-limit=2',
                          '--disable-dev-shm-usage','--autoplay-policy=no-user-gesture-required',
                          '--js-flags=--max-old-space-size=64'])
                try:
                    context=await browser.new_context(service_workers='block',accept_downloads=False,viewport={'width':1280,'height':720})
                    await context.route('**/*',self.route)
                    await context.route_web_socket('**/*',lambda ws:ws.close())
                    await context.add_init_script("""(()=>{for(const n of ['RTCPeerConnection','webkitRTCPeerConnection','WebTransport'])try{Object.defineProperty(window,n,{value:undefined})}catch{};document.addEventListener('DOMContentLoaded',()=>{document.querySelectorAll('video').forEach(v=>{v.muted=true})})})()""")
                    page=await context.new_page()
                    async def close_popup(other):
                        if other is not page:await other.close()
                    context.on('page',close_popup)
                    navigation=asyncio.create_task(page.goto(url,wait_until='domcontentloaded',timeout=20000))
                    try:
                        await asyncio.wait_for(self.ready.wait(),28)
                        await asyncio.sleep(.5)
                        if self.failure:raise RuntimeError(self.failure)
                        if not self.choices:raise RuntimeError('未发现公开可用片源；不处理登录、DRM或验证码绕过')
                        title=(await page.title())[:160]
                        if title:
                            for i,choice in enumerate(self.choices):choice['title']=title+' · 片源'+str(i+1)
                        return {'choices':self.choices,'discovery':{'requests':self.count,'bytes':self.received,'blocked':self.blocked,'browser_persistent':False,'media_downloaded':False}}
                    except asyncio.TimeoutError:raise RuntimeError('动态页面28秒内未发现可用媒体；浏览器已关闭')
                    finally:
                        if not navigation.done():navigation.cancel()
                        await asyncio.gather(navigation,return_exceptions=True)
                        await context.close()
                finally:await browser.close()
        finally:
            if owned and self.session:await self.session.close();self.session=None

async def main():
    try:print(json.dumps(await BrowserResolver().discover(sys.argv[1]),ensure_ascii=False))
    except Exception as e:
        print(str(e)[:12000],file=sys.stderr);raise SystemExit(1)
if __name__=='__main__':asyncio.run(main())
