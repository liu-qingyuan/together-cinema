#!/usr/bin/env python3
"""Opt-in real-browser journeys on a local Compose test deployment.

Install the optional test dependency: pip install playwright
Run: python scripts/gallery_smoke.py http://127.0.0.1:18883
Uses local Chrome (--channel chromium for a Playwright-installed Chromium).
Only generated test media is uploaded/deleted; never select existing media.
"""
import argparse
import asyncio
import json
import re
import subprocess
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import async_playwright, expect


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('--channel', default='chrome')
    parser.add_argument('--artifacts', type=Path, help='Optional screenshot directory (no cookies or storage)')
    args = parser.parse_args()
    url = urlsplit(args.url)
    if url.scheme not in ('http', 'https') or url.hostname not in ('localhost', '127.0.0.1') or url.path not in ('', '/'):
        parser.error('Use a local test deployment, not a live user room')
    base = args.url.rstrip('/')
    if args.artifacts:
        args.artifacts.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel=args.channel)
        guest_browser = None
        uploaded = None
        try:
            context = await browser.new_context(base_url=base)
            page = await context.new_page()
            requests, sockets, page_errors = [], [], []
            page.on('pageerror', lambda error: page_errors.append(str(error)))
            page.on('request', lambda request: requests.append(request))
            page.on('websocket', lambda socket: sockets.append(socket.url))
            await page.goto('/')
            await page.wait_for_load_state('networkidle')
            await expect(page.get_by_role('heading', name=re.compile('好电影，'))).to_be_visible()
            await expect(page.get_by_role('button', name='进入房间 ↗')).to_be_visible()
            library = page.get_by_role('region', name='展厅片库')
            await library.scroll_into_view_if_needed()
            await expect(library).to_contain_text('入房授权后可浏览私人片库')
            assert not sockets, sockets
            assert not any(request.method == 'POST' and urlsplit(request.url).path == '/api/login' for request in requests)
            assert not any(urlsplit(request.url).path.startswith('/media/') for request in requests)
            assert (await page.request.get('/api/library')).status == 401
            assert (await page.request.get('/media/private.mp4')).status == 401
            print(json.dumps({'anonymous_gallery': 'passed', 'private_library_HTTP': 401,
                              'auto_login': False, 'room_websockets': 0, 'media_downloads': 0}))

            room = 'G3' + uuid.uuid4().hex[:6].upper()
            await page.goto('/?room=' + room)
            await expect(page.locator('#roomLabel')).to_have_text('房间 ' + room)
            await expect(page.locator('#connection')).to_contain_text('1 人在线')
            await expect(page.locator('#gallery')).to_be_hidden()
            await expect(page.locator('body')).to_have_class(re.compile('motion-paused'))
            assert len(sockets) == 1 and 'room=' + room in sockets[0], sockets
            login_requests = [request for request in requests if urlsplit(request.url).path == '/api/login']
            assert len(login_requests) == 1 and login_requests[0].post_data_json == {'room': room}
            assert await page.locator('.scene-fx i').first.evaluate("el => getComputedStyle(el).animationPlayState") == 'paused'
            print(json.dumps({'validated_invitation': room, 'gallery_skipped': True, 'decoration_paused': True}))

            # A remembered room and valid cookie must not turn ordinary / into an invitation.
            initial_files = (await (await page.request.get('/api/library')).json())['files']
            requests.clear()
            sockets.clear()
            await page.goto('/')
            await page.wait_for_load_state('networkidle')
            await expect(library).to_be_visible()
            if not initial_files:
                await expect(library).to_contain_text('片库还空着')
            assert not sockets
            assert not any(request.method == 'POST' or urlsplit(request.url).path.startswith('/media/') for request in requests)
            if args.artifacts:
                await page.screenshot(path=args.artifacts / 'gallery-desktop.png', full_page=True)
            await page.set_viewport_size({'width': 390, 'height': 844})
            await page.emulate_media(reduced_motion='reduce')
            await page.goto('/')
            await expect(page.get_by_role('button', name='进入房间 ↗')).to_be_in_viewport()
            await page.get_by_role('link', name='下滑浏览片库 ↓').click()
            await expect(library).to_be_in_viewport()
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            if args.artifacts:
                await page.screenshot(path=args.artifacts / 'gallery-mobile-emulation.png', full_page=True)
            await page.set_viewport_size({'width': 1280, 'height': 900})
            await page.emulate_media(reduced_motion='no-preference')
            print(json.dumps({'authorized_gallery_without_join': 'passed', 'empty_library': not initial_files,
                              'mobile_viewport_only': '390x844', 'reduced_motion': 'passed'}))

            # Invalid invitations may not silently use the remembered room, even with a valid cookie.
            requests.clear()
            sockets.clear()
            await page.goto('/?room=A')
            await expect(page.get_by_role('alert')).to_contain_text('房间码为 2～8 位字母或数字')
            await expect(page.locator('#app')).to_be_hidden()
            await expect(library).to_be_hidden()
            assert not sockets
            await page.get_by_role('textbox', name='房间码', exact=True).fill(room)
            await page.get_by_role('button', name='进入房间 ↗').click()
            await expect(page.locator('#roomLabel')).to_have_text('房间 ' + room)
            await expect(page.locator('#connection')).to_contain_text('房主')
            print(json.dumps({'invalid_invitation_rejected': True, 'manual_entry_after_error': 'passed'}))

            with tempfile.TemporaryDirectory() as directory:
                clip = Path(directory) / 'clip.mp4'
                subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
                                'testsrc2=size=320x180:rate=10', '-f', 'lavfi', '-i', 'sine=frequency=440',
                                '-t', '60', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
                                '-c:a', 'aac', '-movflags', '+faststart', str(clip)], check=True)
                filename = 'gallery-smoke-' + uuid.uuid4().hex + '.mp4'
                response = await page.request.post('/api/upload', multipart={
                    'video': {'name': filename, 'mimeType': 'video/mp4', 'buffer': clip.read_bytes()}})
                assert response.status == 201, await response.text()
                uploaded = (await response.json())['name']

            # Use a second browser process with completely independent cookies/storage.
            guest_browser = await playwright.chromium.launch(channel=args.channel)
            guest = await guest_browser.new_page(base_url=base)
            guest_sockets, guest_requests = [], []
            guest.on('pageerror', lambda error: page_errors.append(str(error)))
            guest.on('websocket', lambda socket: guest_sockets.append(socket.url))
            guest.on('request', lambda request: guest_requests.append(request))
            await guest.goto('/')
            await expect(guest.get_by_role('region', name='展厅片库')).to_contain_text('入房授权后可浏览私人片库')
            await expect(guest.locator('#galleryFiles')).not_to_contain_text(filename)
            assert (await guest.request.get('/media/' + uploaded)).status == 401
            assert not guest_sockets
            assert not any(urlsplit(request.url).path.startswith('/media/') for request in guest_requests)
            await guest.goto('/?room=' + room)
            await expect(guest.locator('#roomLabel')).to_have_text('房间 ' + room)
            await expect(guest.locator('#connection')).to_contain_text('2 人在线')
            await expect(guest.locator('#gallery')).to_be_hidden()
            await guest.locator('#roomLabel').click()  # Real user activation for browser audio policy.

            await page.get_by_role('tab', name='片库', exact=True).click()
            await page.locator('#library').get_by_role('button', name=re.compile(re.escape(filename))).click()
            for member in (page, guest):
                await member.wait_for_function("document.querySelector('#video').readyState >= 2")
                assert uploaded in await member.locator('#video').evaluate('video => video.currentSrc')
            await page.locator('#videoStage').hover()
            await page.get_by_label('播放', exact=True).click()
            for member in (page, guest):
                await member.wait_for_function("!document.querySelector('#video').paused && document.querySelector('#video').currentTime > 1")

            # Browsing with an authorized cookie during a screening neither joins nor loads its media.
            browsing = await page.context.new_page()
            browse_requests, browse_sockets = [], []
            browsing.on('pageerror', lambda error: page_errors.append(str(error)))
            browsing.on('request', lambda request: browse_requests.append(request))
            browsing.on('websocket', lambda socket: browse_sockets.append(socket.url))
            await browsing.goto('/')
            await expect(browsing.locator('#galleryFiles')).to_contain_text(filename)
            await browsing.wait_for_load_state('networkidle')
            assert not browse_sockets
            assert not any(request.method == 'POST' or urlsplit(request.url).path.startswith('/media/') for request in browse_requests)
            await browsing.close()
            times = [await member.locator('#video').evaluate('video => video.currentTime') for member in (page, guest)]
            for member, before in zip((page, guest), times):
                await member.wait_for_function('before => !document.querySelector("#video").paused && document.querySelector("#video").currentTime > before + 1', arg=before)
            drift = abs(await page.locator('#video').evaluate('video => video.currentTime') -
                        await guest.locator('#video').evaluate('video => video.currentTime'))
            assert drift < 1.5, drift
            await page.locator('#videoStage').hover()
            await page.get_by_label('暂停', exact=True).click()
            await guest.wait_for_function('document.querySelector("#video").paused')
            await page.locator('#videoStage').focus()
            await page.keyboard.press('ArrowRight')
            target = await page.locator('#video').evaluate('video => video.currentTime')
            await guest.wait_for_function('target => Math.abs(document.querySelector("#video").currentTime - target) < .8', arg=target)
            for member in (page, guest):
                await expect(member.locator('body')).to_have_class(re.compile('motion-paused'))
            if args.artifacts:
                await page.screenshot(path=args.artifacts / 'screening-room.png')
            print(json.dumps({'private_media_hidden_from_guest': True, 'independent_browsers': 2,
                              'real_playback_pause_seek': 'passed', 'playback_drift_seconds': round(drift, 3),
                              'authorized_gallery_media_downloads': 0}))

            # Exit must return to /, not reload the invitation and log in again.
            await guest.get_by_role('button', name='退出', exact=True).click()
            await guest.wait_for_url(base + '/')
            await expect(guest.get_by_role('region', name='展厅片库')).to_contain_text('入房授权后可浏览私人片库')
            assert (await guest.request.get('/api/library')).status == 401
            await guest.get_by_role('textbox', name='房间码', exact=True).fill(room)
            await guest.get_by_role('button', name='进入房间 ↗').click()
            await expect(guest.locator('#roomLabel')).to_have_text('房间 ' + room)
            await expect(guest.locator('#connection')).to_contain_text('2 人在线')
            assert not page_errors, page_errors
            print(json.dumps({'logout_returns_to_gallery': 'passed', 'ordinary_gallery_manual_entry': 'passed',
                              'browser_runtime_errors': 0}))
        finally:
            try:
                if uploaded:
                    response = await page.request.delete('/api/library/' + uploaded)
                    assert response.status == 200, await response.text()
            finally:
                if guest_browser:
                    await guest_browser.close()
                await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
