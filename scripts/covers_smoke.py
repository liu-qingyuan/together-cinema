#!/usr/bin/env python3
"""Real-browser cover/playback isolation acceptance on a disposable local Compose.

Optional: pip install playwright; local Chrome and ffmpeg. Start watch + converter
with WATCH_TURN_URLS=stun:127.0.0.1:9 and a disposable WATCH_TURN_SECRET for local
host-candidate WebRTC. Two independent Chrome processes use fake test microphones;
negotiation and audio transport are real, not mocked. No production deployment.
Run: python scripts/covers_smoke.py http://127.0.0.1:18885 --artifacts /tmp/covers-smoke
Only generated test uploads are removed; the original selected cover is restored.
"""
import argparse
import asyncio
import io
import json
import re
import subprocess
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image
from playwright.async_api import async_playwright, expect


async def current(page):
    return (await (await page.request.get('/api/covers')).json())['current']


async def audio_bytes(page):
    return await page.evaluate("""async () => {
        let bytes=0;
        for(const peer of voicePeers.values())for(const stat of (await peer.pc.getStats()).values())
            if(stat.type==='inbound-rtp' && stat.kind==='audio')bytes+=stat.bytesReceived;
        return bytes;
    }""")


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('--channel', default='chrome')
    parser.add_argument('--artifacts', type=Path)
    args = parser.parse_args()
    url = urlsplit(args.url)
    if url.scheme not in ('http', 'https') or url.hostname not in ('localhost', '127.0.0.1') or url.path not in ('', '/'):
        parser.error('Use a disposable local test deployment')
    if args.artifacts:
        args.artifacts.mkdir(parents=True, exist_ok=True)
    report, errors, custom, uploaded = [], [], [], None
    async with async_playwright() as playwright:
        options = dict(channel=args.channel, args=['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'])
        first = await playwright.chromium.launch(**options)
        second = await playwright.chromium.launch(**options)
        try:
            member = await first.new_page(base_url=args.url)
            friend = await second.new_page(base_url=args.url)
            visitor = await second.new_page(base_url=args.url)  # Separate context: no room cookie.
            for page in (member, friend, visitor):
                page.on('pageerror', lambda error: errors.append(str(error)))
            original = await current(visitor)
            await visitor.goto('/')
            self_guard = await visitor.request.put('/api/covers/current', data={'id': 'galaxy'})
            assert self_guard.status == 401
            # Even a successfully issued login cookie alone must not authorize writes.
            assert (await visitor.request.post('/api/login', data={'room': 'CV5'})).status == 200
            assert (await visitor.request.put('/api/covers/current', data={'id': 'galaxy'})).status == 403
            await visitor.request.post('/api/logout')
            assert not await visitor.locator('.cover-manager').is_visible()
            room = 'C5' + uuid.uuid4().hex[:6].upper()
            for page in (member, friend):
                await page.goto('/?room=' + room)
                await expect(page.locator('#roomLabel')).to_have_text('房间 ' + room)
            await expect(member.locator('#connection')).to_contain_text('2 人在线')
            manager = member.get_by_role('region', name='全站展厅封面', exact=True)
            await expect(manager).to_have_count(0)
            headers = {'X-Room-Member': await member.evaluate('memberToken')}

            # Generated movie with a real text subtitle goes through the normal converter.
            with tempfile.TemporaryDirectory() as directory:
                clip, subtitle = Path(directory) / 'clip.mkv', Path(directory) / 'test.srt'
                subtitle.write_text('1\n00:00:00,000 --> 00:03:00,000\nCover change must keep this subtitle.\n')
                subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
                                'testsrc2=size=320x180:rate=10', '-f', 'lavfi', '-i', 'sine=frequency=440',
                                '-i', str(subtitle), '-t', '180', '-map', '0:v', '-map', '1:a', '-map', '2:s',
                                '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
                                '-c:a', 'aac', '-c:s', 'srt', str(clip)], check=True)
                response = await member.request.post('/api/upload', multipart={
                    'video': {'name': 'cover-smoke-' + uuid.uuid4().hex + '.mkv', 'mimeType': 'video/x-matroska', 'buffer': clip.read_bytes()}})
                assert response.status == 202, await response.text()
                job_id = (await response.json())['id']
                async with asyncio.timeout(90):
                    while True:
                        jobs = (await (await member.request.get('/api/conversions')).json())['jobs']
                        job = next(job for job in jobs if job['id'] == job_id)
                        assert job['status'] not in ('failed', 'cancelled'), job['error']
                        if job['status'] == 'done':
                            uploaded = job['output']
                            break
                        await asyncio.sleep(.25)  # Poll the observable conversion status, not a fixed delay.
            await member.get_by_role('tab', name='片库', exact=True).click()
            await member.locator('#library').get_by_role('button', name=re.compile(re.escape(uploaded.split('-', 1)[1]))).click()
            for page in (member, friend):
                await page.wait_for_function("document.querySelector('#video').readyState>=2 && document.querySelector('#subtitleSelect').options.length>1")
                # User-facing Artplayer subtitle selector (legacy select is intentionally hidden).
                await page.locator('#videoStage').hover()
                await page.locator('.art-control-setting').click()
                await page.locator('.art-setting-item').filter(has_text=re.compile('^字幕')).first.click()
                await page.locator('.art-setting-item').filter(has_text=re.compile(r'^\s*und\s*$')).click()
                await page.locator('#videoStage').click(position={'x': 20, 'y': 20})
                await page.get_by_role('button', name='加入语音', exact=True).click()
            for page in (member, friend):
                await expect(page.locator('#voiceStatus')).to_contain_text('语音已连通', timeout=20000)
                await page.wait_for_function("[...voicePeers.values()].length===1 && [...voicePeers.values()].every(p=>p.pc.connectionState==='connected')")
                assert await audio_bytes(page) > 0
            await member.locator('#videoStage').hover()
            if await member.get_by_label('播放', exact=True).is_visible():
                await member.get_by_label('播放', exact=True).click()
            for page in (member, friend):
                await page.wait_for_function("!video.paused && video.currentTime>1")
                await page.evaluate("""() => {
                    window.coverBaseline={source:video.currentSrc,time:video.currentTime,subtitle:document.querySelector('#subtitleSelect').value,
                        theme:localStorage.getItem('watchScene'),scene:document.body.dataset.scene,peers:[...voicePeers.values()].map(p=>p.pc),loads:0};
                    video.addEventListener('loadstart',()=>coverBaseline.loads++);
                    video.addEventListener('emptied',()=>coverBaseline.loads++);
                }""")
                assert await page.locator('#subtitleSelect').input_value() != 'off'
            received = [await audio_bytes(page) for page in (member, friend)]

            async def upload(name, color):
                image = io.BytesIO()
                Image.new('RGB', (640, 360), color).save(image, 'PNG')
                response = await member.request.post('/api/covers', headers=headers, multipart={'cover':{
                    'name': name, 'mimeType': 'image/png', 'buffer': image.getvalue()}})
                assert response.ok, await response.text()
                ident = await current(member)
                custom.append(ident)
                return ident

            async def verify(expected):
                await visitor.reload()
                assert await current(visitor) == expected
                await visitor.wait_for_function("() => {const img=document.querySelector('#galleryCover img');return img.complete&&img.naturalWidth>0}")
                if expected not in ('sky', 'galaxy'):
                    assert '/covers/' + expected + '/' in await visitor.locator('#galleryCover img').evaluate('img=>img.currentSrc')
                else:
                    assert '/v1-' + expected + '-' in await visitor.locator('#galleryCover img').evaluate('img=>img.currentSrc')
                for page in (member, friend):
                    await page.wait_for_function('video.currentTime > coverBaseline.time+1')
                    assert await page.evaluate("""() => video.currentSrc===coverBaseline.source && !video.paused && !coverBaseline.loads
                        && document.querySelector('#subtitleSelect').value===coverBaseline.subtitle
                        && [...video.textTracks].some(track=>track.mode==='showing' && track.activeCues?.length)
                        && localStorage.getItem('watchScene')===coverBaseline.theme && document.body.dataset.scene===coverBaseline.scene
                        && [...voicePeers.values()].every((p,i)=>p.pc===coverBaseline.peers[i] && p.pc.connectionState==='connected')
                        && voiceStream.getTracks().every(track=>track.readyState==='live')""")
                drift = abs(await member.locator('#video').evaluate('v=>v.currentTime') - await friend.locator('#video').evaluate('v=>v.currentTime'))
                assert drift < 1.5, drift
                report.append({'current': expected if expected in ('sky', 'galaxy') else 'custom', 'no_media_reload': True,
                               'subtitles_preserved': True, 'voice_connected': True, 'drift_seconds': round(drift, 3)})
                if len(report) == 1:
                    for label, viewport in [('desktop', {'width': 1280, 'height': 900}),
                                            ('mobile-emulation', {'width': 390, 'height': 844})]:
                        await visitor.set_viewport_size(viewport)
                        await expect(visitor.get_by_role('link', name='入房 ↗', exact=True)).to_be_in_viewport()
                        assert await visitor.evaluate('document.documentElement.scrollWidth<=innerWidth')
                        if args.artifacts:
                            await visitor.screenshot(path=args.artifacts / ('custom-' + label + '.png'), full_page=True)
                    await visitor.set_viewport_size({'width': 1280, 'height': 720})

            first_id = await upload('test-one.png', '#8bc9dc')
            await verify(first_id)
            # A selected existing picture and both presets use the same public write seam.
            for ident in ('galaxy', first_id):
                assert (await member.request.put('/api/covers/current',headers=headers,data={'id':ident})).ok
                await verify(ident)
            second_id = await upload('test-two.png', '#edb8be')
            await verify(second_id)
            bad = await member.request.post('/api/covers', headers=headers, multipart={'cover':{
                'name':'broken.png','mimeType':'image/png','buffer':b'not an image'}})
            assert 400 <= bad.status < 500
            await verify(second_id)
            member.on('dialog', lambda dialog: dialog.accept())
            for ident, expected in ((first_id, second_id), (second_id, 'sky')):
                assert (await member.request.delete('/api/covers/'+ident,headers=headers)).ok
                await verify(expected)
                custom.remove(ident)
            for page, before in zip((member, friend), received):
                assert await audio_bytes(page) > before
            assert not errors, errors
            report.append({'independent_browser_processes': 2, 'read_only_visitor': True, 'login_only_write_HTTP': 403,
                           'fake_test_microphones': True, 'real_WebRTC_audio_bytes_increased': True, 'browser_errors': errors})
            if args.artifacts:
                await member.locator('#player').scroll_into_view_if_needed()
                await member.screenshot(path=args.artifacts / 'screening-after-cover-delete.png')
                await visitor.screenshot(path=args.artifacts / 'visitor-fallback.png', full_page=True)
                (args.artifacts / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps(report, ensure_ascii=False))
        finally:
            try:
                if 'member' in locals():
                    # Cleanup only our generated files, using the real active member credential.
                    token = await member.evaluate('memberToken')
                    for ident in custom:
                        await member.request.delete('/api/covers/' + ident, headers={'X-Room-Member': token})
                    if 'original' in locals():
                        await member.request.put('/api/covers/current', data={'id': original}, headers={'X-Room-Member': token})
                    if uploaded:
                        response = await member.request.delete('/api/library/' + uploaded)
                        assert response.status == 200, await response.text()
            finally:
                await second.close()
                await first.close()


if __name__ == '__main__':
    asyncio.run(main())
