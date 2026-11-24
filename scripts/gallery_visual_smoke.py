#!/usr/bin/env python3
"""Opt-in visual checks on local Compose; viewport emulation is NOT a real phone.

pip install playwright
python scripts/gallery_visual_smoke.py http://127.0.0.1:18884 --artifacts /tmp/gallery-visual
Screenshots and report.json contain no cookies or local storage. No site request mocks.
"""
import argparse
import asyncio
import json
import re
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import async_playwright, expect


async def select_cover(page, key):
    await page.get_by_role('button', name={'sky': '动漫天空', 'galaxy': '雪山银河'}[key], exact=True).click()
    await page.wait_for_function("key => {const img=document.querySelector('#galleryCover img');return img.complete && img.naturalWidth>0 && img.currentSrc.includes('/v1-'+key+'-')}", arg=key)
    await page.wait_for_load_state('networkidle')


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('--channel', default='chrome')
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args()
    url = urlsplit(args.url)
    if url.scheme not in ('http', 'https') or url.hostname not in ('localhost', '127.0.0.1') or url.path not in ('', '/'):
        parser.error('Use a local test deployment')
    args.artifacts.mkdir(parents=True, exist_ok=True)
    report, errors = [], []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel=args.channel)
        try:
            for label, viewport in [('desktop', {'width': 1440, 'height': 1000}),
                                    ('mobile-emulation', {'width': 390, 'height': 844})]:
                context = await browser.new_context(base_url=args.url.rstrip('/'), viewport=viewport, locale='zh-CN')
                page = await context.new_page()
                requests, sockets = [], []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('request', lambda request: requests.append(request))
                page.on('websocket', lambda socket: sockets.append(socket.url))
                await page.goto('/')
                for key in ['sky', 'galaxy']:
                    await select_cover(page, key)
                    cover_requests = [urlsplit(r.url).path for r in requests if '/scenes/v1-' in r.url and '.webp' in r.url]
                    size = 'mobile' if label == 'mobile-emulation' else 'desktop'
                    assert f'/scenes/v1-{key}-{size}.webp' in cover_requests, cover_requests
                    assert all(path.endswith(f'-{size}.webp') for path in cover_requests), cover_requests
                    assert all(urlsplit(r.url).hostname in ('127.0.0.1', 'localhost') for r in requests), [r.url for r in requests]
                    assert not any(r.method == 'POST' or urlsplit(r.url).path.startswith('/media/') for r in requests)
                    assert not sockets
                    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    image = page.locator('#galleryCover img')
                    await expect(image).to_have_attribute('alt', '云间留白的动漫蓝天' if key == 'sky' else '银河下的厄尔布鲁士雪山与帐篷')
                    if key == 'galaxy':
                        box = await image.bounding_box()
                        assert abs(box['width'] / box['height'] - 2 / 3) < .01, box
                        if label == 'desktop':
                            text_box = await page.locator('.login-intro').bounding_box()
                            assert box['x'] >= text_box['x'] + text_box['width'], (box, text_box)
                        assert await image.evaluate('el => getComputedStyle(el).objectFit') == 'contain'
                    # Keyboard focus and an explicit entry link remain visible on both backgrounds.
                    await page.get_by_role('button', name='雪山银河', exact=True).focus()
                    await page.keyboard.press('Tab')
                    entry = page.get_by_role('link', name='入房 ↗', exact=True)
                    await expect(entry).to_be_focused()
                    await expect(entry).to_be_in_viewport()
                    assert await entry.evaluate('el => parseFloat(getComputedStyle(el).outlineWidth) >= 2')
                    await page.screenshot(path=args.artifacts / f'{key}-{label}-focus.png', full_page=True)
                    await entry.click()
                    await expect(page.get_by_role('textbox', name='房间码', exact=True)).to_be_in_viewport()
                    await page.get_by_role('link', name='下滑浏览片库 ↓').click()
                    await expect(page.get_by_role('region', name='展厅片库')).to_be_in_viewport()
                    report.append({'cover': key, 'device': label, 'viewport': viewport,
                                   'resource': f'v1-{key}-{size}.webp', 'focus_and_library': 'passed'})
                    await page.evaluate('scrollTo(0,0)')
                    requests.clear()
                await context.close()

            # Same native form works with reduced motion, opaque material preferences,
            # and base CSS with the optional @supports enhancement removed. The latter
            # verifies the static design, NOT an actual unsupported browser engine.
            for preference in ['prefers-reduced-motion', 'prefers-reduced-transparency', 'static-base-css']:
                for key in ['sky', 'galaxy']:
                    context = await browser.new_context(base_url=args.url.rstrip('/'), viewport={'width': 390, 'height': 844}, locale='zh-CN')
                    page = await context.new_page()
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    room_requests = []
                    page.on('request', lambda request: room_requests.append(request))
                    if preference != 'static-base-css':
                        cdp = await context.new_cdp_session(page)
                        await cdp.send('Emulation.setEmulatedMedia', {'features': [{'name': preference, 'value': 'reduce'}]})
                    await page.goto('/')
                    if preference == 'static-base-css':
                        removed = await page.evaluate("""() => {
                            const sheet=document.querySelector('style[data-gallery-layout]').sheet;
                            let removed=0;
                            for(let i=sheet.cssRules.length-1;i>=0;i--)if(sheet.cssRules[i].conditionText?.includes('backdrop-filter')){sheet.deleteRule(i);removed++}
                            return removed;
                        }""")
                        assert removed == 1
                    await select_cover(page, key)
                    if preference != 'static-base-css':
                        assert await page.evaluate('(name) => matchMedia(`(${name}: reduce)`).matches', preference)
                    if preference in ('prefers-reduced-transparency', 'static-base-css'):
                        style = await page.locator('.login-card').evaluate('el => {const s=getComputedStyle(el);return {blur:s.backdropFilter,background:s.backgroundColor}}')
                        assert style['blur'] == 'none', style
                        assert style['background'].startswith('rgb('), style
                    else:
                        await expect(page.locator('body')).to_have_class(re.compile('motion-paused'))
                    await page.screenshot(path=args.artifacts / f'{key}-{preference}.png', full_page=True)
                    room = 'V4' + uuid.uuid4().hex[:6].upper()
                    await page.get_by_role('textbox', name='房间码', exact=True).fill(room)
                    await page.get_by_role('button', name='进入房间 ↗').click()
                    await expect(page.locator('#roomLabel')).to_have_text('房间 ' + room)
                    await expect(page.locator('#gallery')).to_be_hidden()
                    await expect(page.locator('body')).to_have_class(re.compile('motion-paused'))
                    assert not await page.locator('#galleryCover img').get_attribute('src')
                    assert not await page.locator('#galleryCover source').get_attribute('srcset')
                    room_requests.clear()
                    await page.set_viewport_size({'width': 1440, 'height': 1000})
                    await page.wait_for_load_state('networkidle')
                    assert not any('.webp' in r.url and '/scenes/' in r.url for r in room_requests)
                    animation = await page.locator('.scene-fx i').first.evaluate("el => {const s=getComputedStyle(el);return {name:s.animationName,state:s.animationPlayState}}")
                    assert animation['name'] == 'none' or animation['state'] == 'paused', animation
                    report.append({'cover': key, 'preference': preference, 'entry': 'passed', 'room_resize_cover_downloads': 0})
                    await context.close()

            # Narrow layout remains scrollable without losing the explicit entry link.
            context = await browser.new_context(base_url=args.url.rstrip('/'), viewport={'width': 320, 'height': 568}, locale='zh-CN')
            page = await context.new_page()
            await page.goto('/')
            for key in ['sky', 'galaxy']:
                await select_cover(page, key)
                await expect(page.get_by_role('link', name='入房 ↗', exact=True)).to_be_in_viewport()
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            await context.close()
            report.append({'narrow_viewport_only': '320x568', 'horizontal_overflow': False})

            # Direct invitations must never fetch gallery cover variants.
            context = await browser.new_context(base_url=args.url.rstrip('/'), locale='zh-CN')
            page = await context.new_page()
            requests = []
            page.on('request', lambda request: requests.append(request))
            room = 'V4' + uuid.uuid4().hex[:6].upper()
            await page.goto('/?room=' + room)
            await expect(page.locator('#roomLabel')).to_have_text('房间 ' + room)
            await page.wait_for_load_state('networkidle')
            assert not any('.webp' in r.url and '/scenes/' in r.url for r in requests)
            await context.close()
            assert not errors, errors
            report.append({'invitation_cover_downloads': 0, 'browser_runtime_errors': errors,
                           'real_phone_verified': False, 'unsupported_filter_engine_verified': False})
            (args.artifacts / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps(report, ensure_ascii=False))
        finally:
            await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
