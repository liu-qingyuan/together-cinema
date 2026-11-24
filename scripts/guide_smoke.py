"""Opt-in: python -m scripts.guide_smoke --output docs/evidence/guide.json.

Uses Chrome/Playwright and ffmpeg, temporary generated clips and a controlled
non-YouTube origin. Only transport to https://media.example is mapped to a local
HTTP fixture; production discovery, selection, relay and room code run unchanged.
This does not verify public DNS/TLS, real providers, production or mobile devices.
"""
import argparse
import asyncio
import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from aiohttp import web
from aiohttp.test_utils import TestServer
from playwright.async_api import async_playwright, expect
from yarl import URL

from cinema.external_media import ExternalMedia, public_url
from cinema.server import create_app


OBSERVE = """(() => {
  window.guideEvidence={controls:0,loads:0,sockets:0};
  const send=WebSocket.prototype.send;
  WebSocket.prototype.send=function(data){
    if(['control','rate','boost'].includes(JSON.parse(data).type))guideEvidence.controls++;
    return send.call(this,data);
  };
  const Socket=WebSocket;
  window.WebSocket=class extends Socket {constructor(...args){super(...args);guideEvidence.sockets++}};
  document.addEventListener('DOMContentLoaded',()=>{
    for(const event of ['loadstart','emptied'])document.querySelector('#video')?.addEventListener(event,()=>guideEvidence.loads++);
  });
})();"""


async def assert_playing(pages):
    for page in pages:
        await page.wait_for_function("document.querySelector('#video').currentTime>1 && !document.querySelector('#video').paused")
    drift = abs(await pages[0].locator('#video').evaluate('v=>v.currentTime') -
                await pages[1].locator('#video').evaluate('v=>v.currentTime'))
    assert drift < 1.5, drift
    return round(drift, 3)


async def pause_resume(host, pages):
    await host.locator('#videoStage').hover()
    await host.get_by_label('Pause', exact=True).click()
    for page in pages:
        await page.wait_for_function("document.querySelector('#video').paused")
    await host.get_by_label('Play', exact=True).click()
    return await assert_playing(pages)


async def run(args):
    with tempfile.TemporaryDirectory(prefix='cinema-guide-') as directory:
        root = Path(directory)
        for name, color, frequency in [('one', 'red', '440'), ('two', 'blue', '660')]:
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', f'color=c={color}:size=320x180:rate=10',
                            '-f', 'lavfi', '-i', 'sine=frequency=' + frequency, '-t', '120', '-c:v', 'libx264',
                            '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart',
                            str(root / (name + '.mp4'))], check=True, capture_output=True)
        origin_reads = []

        async def origin_page(request):
            return web.Response(text='<h1>Owned, generated test clips</h1><h2>First: red</h2><video src="/one.mp4"></video>'
                                     '<h2>Second: blue</h2><video src="/two.mp4"></video>', content_type='text/html')

        async def origin_media(request):
            origin_reads.append(request.path)
            return web.FileResponse(root / request.match_info['name'], headers={'Access-Control-Allow-Origin': '*'})

        async def empty_page(request):
            return web.Response(text='<h1>No media here</h1>', content_type='text/html')

        async def no_candidates(request):
            return web.json_response({'choices': []})

        origin_app = web.Application()
        origin_app.router.add_get('/clips', origin_page)
        origin_app.router.add_get('/{name:one.mp4|two.mp4}', origin_media)
        origin_app.router.add_get('/empty', empty_page)
        origin_app.router.add_post('/resolve-page', no_candidates)
        async with TestServer(origin_app, host='127.0.0.1') as origin:
            class FixtureTransport(ExternalMedia):
                async def request(self, url, method='GET', headers=None):
                    public_url(url)
                    assert urlsplit(url).hostname == 'media.example'
                    response = await self.session.request(method, origin.make_url(urlsplit(url).path),
                                                          headers=headers, allow_redirects=False)
                    response._url = URL(url)  # Keep relative discovery URLs on the fixture origin.
                    return response

            media = FixtureTransport('http://127.0.0.1:9', 'guide-test-secret')
            with patch('cinema.server.ExternalMedia', return_value=media):
                app = create_app(root / 'data', 'guide-test-secret', secure=False)
            (root / 'data/media/local-original.mp4').write_bytes((root / 'one.mp4').read_bytes())
            async with TestServer(app, host='127.0.0.1') as server, async_playwright() as playwright:
                browser = await playwright.chromium.launch(channel='chrome')
                errors, browser_reads, blocked = [], [[], []], []
                deny_guest_origin = False
                try:
                    pages = []
                    for index, language in enumerate(['en-US', 'zh-CN']):
                        context = await browser.new_context(locale=language)
                        await context.add_init_script(OBSERVE)

                        async def route_origin(route, request, index=index):
                            path = urlsplit(route.request.url).path
                            if index == 1 and deny_guest_origin:
                                blocked.append(path)
                                await route.abort('blockedbyclient')
                            else:
                                response = await route.fetch(url=str(origin.make_url(path)))
                                await route.fulfill(response=response)

                        await context.route('https://media.example/**', route_origin)
                        page = await context.new_page()
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        page.on('request', lambda request, index=index: browser_reads[index].append(request.url))
                        pages.append(page)
                    host, guest = pages
                    # Gallery help is public, opens separately, and does not enter a room.
                    await host.goto(str(server.make_url('/')))
                    async with host.expect_popup() as popup:
                        await host.get_by_role('link', name='Viewer guide (new tab) ↗', exact=True).click()
                    guide = await popup.value
                    await expect(guide.locator('html')).to_have_attribute('lang', 'en')
                    await expect(guide.get_by_role('heading', name='First watch together', exact=True)).to_be_visible()
                    await guide.get_by_role('link', name='简体中文', exact=True).click()
                    await expect(guide.locator('html')).to_have_attribute('lang', 'zh-CN')
                    await guide.close()
                    assert (await host.request.get(str(server.make_url('/api/library')))).status == 401
                    await host.get_by_role('textbox', name='Room code', exact=True).fill('GUIDE15')
                    await host.get_by_role('button', name='Enter room ↗', exact=True).click()
                    await expect(host.locator('#connection')).to_contain_text('Host')
                    # This is the same invitation form as Copy invite produces, not a separate room.
                    await guest.goto(str(server.make_url('/?room=GUIDE15')))
                    await expect(host.locator('#connection')).to_contain_text('2 online')
                    await expect(guest.locator('#connection')).to_contain_text('2 人在线')
                    await guest.locator('#roomLabel').click()  # Enable guest audio through a real gesture.
                    await host.get_by_role('tab', name='Library', exact=True).click()
                    await host.locator('#library').get_by_role('button', name='local-original.mp4', exact=False).click()
                    for page in pages:
                        await page.wait_for_function("document.querySelector('#video').readyState>=2")
                    await host.locator('#videoStage').hover()
                    await host.get_by_label('Play', exact=True).click()
                    await assert_playing(pages)
                    before = []
                    for page in pages:
                        before.append(await page.evaluate("({e:{...guideEvidence},time:document.querySelector('#video').currentTime})"))
                    async with host.expect_popup() as popup:
                        await host.get_by_role('link', name='Viewer guide (new tab) ↗', exact=True).click()
                    guide = await popup.value
                    await expect(guide.get_by_role('heading', name='Direct playback or server relay?', exact=True)).to_be_visible()
                    await guide.get_by_role('link', name='简体中文', exact=True).click()
                    await expect(guide.get_by_role('heading', name='直连还是服务器中转？', exact=True)).to_be_visible()
                    await guide.close()
                    for page, previous in zip(pages, before):
                        await page.wait_for_function("time=>document.querySelector('#video').currentTime>time+.5", arg=previous['time'])
                        assert await page.evaluate('guideEvidence') == previous['e']
                        await expect(page.locator('#title')).to_have_text('local-original.mp4')
                    await expect(host.locator('html')).to_have_attribute('lang', 'en')
                    await host.locator('details.network-video summary').click()
                    await host.get_by_role('textbox', name='Video webpage or HTTPS media URL', exact=True).fill('https://media.example/clips')
                    await host.get_by_role('combobox', name='Online playback mode', exact=True).select_option('direct')
                    await host.get_by_role('button', name='Find videos', exact=True).click()
                    await expect(host.locator('#networkResults button')).to_have_count(2)
                    await expect(host.locator('#title')).to_have_text('local-original.mp4')  # Never auto-pick result one.
                    await host.locator('#videoStage').hover()
                    await host.get_by_label('Pause', exact=True).click()
                    browser_reads = [[], []]
                    await host.locator('#networkResults button').nth(1).click()
                    for page in pages:
                        await expect(page.locator('#title')).to_contain_text('网页视频 2')
                        await page.wait_for_function("document.querySelector('#video').readyState>=2")
                    await host.locator('#videoStage').hover()
                    await host.get_by_label('Play', exact=True).click()
                    direct_drift = await pause_resume(host, pages)
                    for reads in browser_reads:
                        assert any(url == 'https://media.example/two.mp4' for url in reads), reads
                        assert not any('/play' in url and '/api/network/' in url for url in reads), reads
                    assert '/one.mp4' not in origin_reads  # The first candidate was not fetched.
                    # The guest genuinely cannot reach the origin, while the server still can.
                    deny_guest_origin = True
                    could_fetch = await guest.evaluate("async()=>{try{return (await fetch('https://media.example/two.mp4',{cache:'no-store'})).ok}catch{return false}}")
                    assert not could_fetch, 'Guest origin block did not take effect'
                    assert blocked == ['/two.mp4'], blocked
                    await host.locator('#videoStage').hover()
                    await host.get_by_label('Pause', exact=True).click()
                    browser_reads = [[], []]
                    await host.get_by_role('combobox', name='Online playback mode', exact=True).select_option('relay')
                    await host.get_by_role('button', name='Find videos', exact=True).click()
                    await expect(host.locator('#networkResults button')).to_have_count(2)
                    await host.locator('#networkResults button').nth(1).click()
                    for page in pages:
                        await expect(page.locator('#title')).to_contain_text('网页视频 2')
                        await page.wait_for_function("document.querySelector('#video').readyState>=2")
                    await expect(host.locator('#title')).to_contain_text('Server relay')
                    await expect(guest.locator('#title')).to_contain_text('中转')
                    await host.locator('#videoStage').hover()
                    await host.get_by_label('Play', exact=True).click()
                    relay_drift = await pause_resume(host, pages)
                    for reads in browser_reads:
                        assert any('/api/network/' in url and '/play' in url for url in reads), reads
                        assert not any('media.example' in url for url in reads), reads
                    assert blocked == ['/two.mp4'], blocked
                    assert media.bytes_sent > 0
                    # Both discovery failure paths preserve the selected relay film and progress.
                    current = await host.locator('#video').evaluate('v=>v.currentSrc')
                    await host.get_by_role('textbox', name='Video webpage or HTTPS media URL', exact=True).fill('https://media.example/empty')
                    for extractor, error in [('http://127.0.0.1:9', 'Discovery unavailable'), (str(origin.make_url('')).rstrip('/'), 'No playable public media')]:
                        media.extractor_url = extractor
                        await host.get_by_role('button', name='Find videos', exact=True).click()
                        await expect(host.locator('#networkStatus')).to_contain_text(error)
                        await expect(host.locator('#networkResults button')).to_have_count(0)
                        assert await host.locator('#video').evaluate('v=>v.currentSrc') == current
                        await assert_playing(pages)
                    # Stable quota/expired errors and guide instructions; neither probe changes selection.
                    media.bytes_sent = media.daily_limit
                    response = await host.request.get(current)
                    assert response.status == 429 and response.headers['x-cinema-error'] == 'relay_quota'
                    response = await host.request.get(str(server.make_url('/api/network/expired/source')))
                    assert response.status == 410 and response.headers['x-cinema-error'] == 'source_expired'
                    assert await host.locator('#video').evaluate('v=>v.currentSrc') == current
                    assert not errors, errors
                    result = {'fixture': 'owned generated red/440Hz and blue/660Hz H.264/AAC clips, non-YouTube two-video page',
                              'transport': 'only media.example mapped to local HTTP fixture; public URL policy retained',
                              'independent_contexts': 2, 'public_bilingual_gallery_help': 'passed',
                              'room_help_media_reloads_reconnects_controls': 0, 'guide_language_changes_room_language': False,
                              'explicit_second_candidate_no_auto_selection': 'passed',
                              'direct_browser_media_path': 'https://media.example/two.mp4',
                              'relay_browser_media_path': '/api/network/<source>/play',
                              'pause_resume_direct_drift_seconds': direct_drift, 'pause_resume_relay_drift_seconds': relay_drift,
                              'guest_origin_blocked_server_relay_plays': 'passed',
                              'dynamic_disabled_and_empty_candidates_keep_current_film': 'passed',
                              'quota_expired_http_errors_keep_current_selection': 'passed',
                              'browser_errors': errors,
                              'not_verified': ['public origin DNS/TLS', 'real third-party providers', 'production', 'real mobile devices', 'mid-stream quota exhaustion']}
                    print(json.dumps(result, ensure_ascii=False, indent=2))
                    if args.output:
                        args.output.parent.mkdir(parents=True, exist_ok=True)
                        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
                finally:
                    await browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    asyncio.run(run(parser.parse_args()))
