#!/usr/bin/env python3
"""Opt-in HTTP smoke against an explicitly provided test deployment.
Only uploads/deletes its own generated clip. No existing media is selected or removed.
"""
import argparse,asyncio,json,subprocess,tempfile,uuid
from pathlib import Path
import aiohttp
async def main():
 parser=argparse.ArgumentParser();parser.add_argument('url');args=parser.parse_args();base=args.url.rstrip('/')
 if not base.startswith(('http://127.0.0.1:','http://localhost:')):parser.error('Use a local test deployment, not a live user room')
 async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
  async with session.get(base+'/healthz') as r:assert r.status==200
  async with session.post(base+'/api/login',json={'room':'SMOKETST'}) as r:assert r.status==200
  with tempfile.TemporaryDirectory() as d:
   clip=Path(d)/'clip.mp4';subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=320x180:rate=10','-t','1','-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(clip)],check=True)
   filename='smoke-'+uuid.uuid4().hex+'.mp4';form=aiohttp.FormData();form.add_field('video',clip.read_bytes(),filename=filename,content_type='video/mp4')
   uploaded=None
   try:
    async with session.post(base+'/api/upload',data=form) as r:assert r.status==201,await r.text();uploaded=(await r.json())['name']
    async with session.get(base+'/api/library') as r:data=await r.json();assert any(x['name']==uploaded for x in data['files'])
    async with session.get(base+'/media/'+uploaded,headers={'Range':'bytes=0-31'}) as r:assert r.status==206;body=await r.read();assert body==clip.read_bytes()[:32]
    async with session.get(base+'/media/'+uploaded) as r:
     assert r.status==200
     fixture=clip.read_bytes();served=await r.content.readexactly(len(fixture))
     assert served==fixture and not await r.content.read(1)
    decoded=subprocess.run(['ffmpeg','-v','error','-xerror','-threads','1','-i','pipe:0','-frames:v','2','-vf','scale=16:16','-threads','1','-pix_fmt','gray','-f','rawvideo','pipe:1'],input=served,stdout=subprocess.PIPE,check=True,timeout=20)
    assert len(decoded.stdout)==512
    async with session.get(base+'/room-art/anime-thumb.webp') as r:assert r.status==200 and r.content_type=='image/webp'
    ws=await session.ws_connect(base+'/ws?room=SMOKETST');first=await ws.receive_json();state=await ws.receive_json();assert state['room']=='SMOKETST';await ws.close()
    print(json.dumps({'health_HTTP':200,'room_login_HTTP':200,'own_MP4_upload_HTTP':201,'media_range_HTTP':206,'first32bytes_exact':True,'uploaded_frames_decoded':2,'scene_HTTP':200,'websocket_room':'SMOKETST','existing_media_untouched':True}))
   finally:
    if uploaded:
     async with session.delete(base+'/api/library/'+uploaded) as r:assert r.status==200
asyncio.run(main())
