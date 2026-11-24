"""Opt-in: python -m scripts.mobile_header_smoke [--artifacts DIR] [--output evidence.json].

Requires optional Playwright and local Chrome. Uses only a temporary loopback app
and synthetic room/viewers; never opens a personal deployment or invitation.
"""
import argparse
import asyncio
import json
import tempfile
from pathlib import Path

from aiohttp.test_utils import TestServer
from playwright.async_api import async_playwright, expect
from cinema.server import create_app


async def check_layout(page, ids, width, height, touch_ids=()):
    rects = []
    for ident in ids:
        control = page.locator('#' + ident)
        await expect(control).to_be_visible()
        box = await control.bounding_box()
        assert box['x'] >= 0 and box['y'] >= 0 and box['x'] + box['width'] <= width + 1 and box['y'] + box['height'] <= height, (ident, box)
        if ident in touch_ids:
            assert box['width'] >= 44 and box['height'] >= 44, (ident, box)
        for previous, other in rects:
            overlap_x = min(box['x'] + box['width'], other['x'] + other['width']) - max(box['x'], other['x'])
            overlap_y = min(box['y'] + box['height'], other['y'] + other['height']) - max(box['y'], other['y'])
            assert overlap_x <= 0 or overlap_y <= 0, (ident, previous, box, other)
        rects.append((ident, box))
        assert await control.evaluate('e=>e.scrollWidth<=e.clientWidth'), ident
    return rects


async def check_navigation(page, mobile):
    nav = page.locator('#siteNav')
    toggle = nav.locator('.nav-toggle')
    if mobile:
        await toggle.tap()
    else:
        await nav.hover()
    links = nav.locator('.nav-links a:visible')
    await expect(links.last).to_be_visible()
    # A visible label may still paint outside the glass, without overflowing the page.
    await page.wait_for_function("""() => {
      const nav=document.querySelector('#siteNav'), compact=nav.hasAttribute('data-compact');
      const box=nav.querySelector(compact ? '.nav-links' : '.nav-bar').getBoundingClientRect();
      const brand=nav.querySelector('.nav-name');
      return (compact || brand.scrollWidth<=brand.clientWidth+1) &&
        [...nav.querySelectorAll('.nav-links a')].filter(a=>a.offsetWidth).every(a=>{
          const r=a.getBoundingClientRect();return r.left>=box.left-1 && r.right<=box.right+1;
        });
    }""", timeout=2000)
    if mobile:
        label = await links.last.inner_text()
        await links.last.tap()
        await expect(nav.locator('.nav-current')).to_have_text(label)
        current = nav.locator('.nav-current')
        assert await current.evaluate("""e=>{const range=document.createRange();range.selectNodeContents(e);
          return range.getClientRects().length===1 && range.getBoundingClientRect().right<=
            e.parentElement.querySelector('.nav-dots').getBoundingClientRect().left+1}""")
        await page.evaluate("window.scrollTo({top:0,behavior:'instant'})")
    else:
        await page.mouse.move(0, 0)


async def check_actions(page, english, base_url):
    menu = page.get_by_role('button', name='Room actions' if english else '房间操作', exact=True)
    switch = page.get_by_role('button', name='Switch room' if english else '切换房间', exact=True)
    leave = page.get_by_role('button', name='Leave' if english else '退出', exact=True)
    await menu.focus()
    await page.keyboard.press('Enter')
    await page.keyboard.press('Tab')
    await expect(switch).to_be_focused()
    await page.keyboard.press('Tab')
    await expect(leave).to_be_focused()
    await page.keyboard.press('Escape')
    await expect(menu).to_be_focused()
    await expect(menu).to_have_attribute('aria-expanded', 'false')
    await page.keyboard.press('Space')
    await page.keyboard.press('Tab')
    await expect(switch).to_be_focused()
    await page.keyboard.press('Shift+Tab')
    await expect(menu).to_be_focused()
    await page.keyboard.press('Space')
    await expect(switch).to_be_hidden()
    await menu.tap()
    await page.keyboard.press('Tab')
    await page.keyboard.press('Tab')
    await page.keyboard.press('Tab')
    await expect(menu).to_have_attribute('aria-expanded', 'false')
    await menu.tap()
    await page.locator('#roomLabel').tap()
    await expect(menu).to_have_attribute('aria-expanded', 'false')
    await menu.tap()
    await switch.tap()
    await expect(page.get_by_role('dialog')).to_be_visible()
    await page.keyboard.press('Escape')
    await expect(page.get_by_role('dialog')).to_be_hidden()
    await expect(menu).to_be_focused()
    # Selecting the existing action really changes room, not just its label.
    await menu.tap()
    await switch.tap()
    await page.get_by_role('textbox', name='Room code' if english else '房间码', exact=True).fill('NEXT16')
    await page.get_by_role('textbox', name='Your nickname' if english else '你的昵称', exact=True).fill('Synthetic viewer')
    await page.get_by_role('button', name='Enter room' if english else '进入房间', exact=True).click()
    await expect(page.locator('#roomLabel')).to_contain_text('NEXT16')
    await expect(page.locator('#connection')).to_contain_text('Host' if english else '房主')
    await expect(menu).to_be_focused()
    await page.get_by_role('button', name='Copy invite' if english else '复制邀请', exact=True).tap()
    assert await page.evaluate('navigator.clipboard.readText()') == base_url + '?room=NEXT16'
    await menu.tap()
    await leave.tap()
    await page.wait_for_url(base_url)
    await expect(menu).to_be_hidden()
    assert (await page.request.get(base_url + 'api/library')).status == 401


async def run(args):
    with tempfile.TemporaryDirectory(prefix='cinema-mobile-header-') as directory:
        app = create_app(Path(directory), 'header-synthetic-secret', secure=False)
        async with TestServer(app, host='127.0.0.1') as server, async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel='chrome')
            errors, checked = [], []
            base_url = str(server.make_url('/'))
            try:
                for language in ['zh-CN', 'en-US']:
                    english = language == 'en-US'
                    context = await browser.new_context(locale=language, has_touch=True, viewport={'width': 1440, 'height': 900},
                                                        permissions=['clipboard-read', 'clipboard-write'])
                    await context.add_init_script("localStorage.setItem('watchNickname','Synthetic viewer')")
                    host = await context.new_page()
                    await host.goto(base_url + '?room=MOBILE16')
                    await expect(host.locator('#connection')).to_contain_text('Host' if english else '房主')
                    page = await context.new_page()
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    await page.goto(base_url + '?room=MOBILE16')
                    await expect(page.locator('#connection')).to_contain_text('Following' if english else '同步中')
                    menu = page.get_by_role('button', name='Room actions' if english else '房间操作', exact=True)
                    for width, height in [(320, 740), (390, 844), (844, 390), (1440, 900)]:
                        await page.set_viewport_size({'width': width, 'height': height})
                        mobile = width <= 1280
                        if mobile:
                            await expect(menu).to_be_visible()
                        else:
                            await expect(menu).to_be_hidden()
                            await expect(page.locator('#openRoom')).to_be_visible()
                        ids = ['roomLabel', 'connection', 'copyInvite', 'siteNav']
                        ids += ['roomActionsToggle'] if mobile else ['openRoom', 'logout']
                        rects = await check_layout(page, ids, width, height, ['copyInvite', 'roomActionsToggle'] if mobile else [])
                        title = await page.locator('#roomOpening .comfort-kicker').bounding_box()
                        assert all(box['y'] + box['height'] <= title['y'] for _, box in rects), (width, height, title)
                        await expect(page.locator('#roomLabel')).to_contain_text('MOBILE16')
                        await page.get_by_role('button', name='Copy invite' if english else '复制邀请', exact=True).click()
                        assert await page.evaluate('navigator.clipboard.readText()') == base_url + '?room=MOBILE16'
                        await check_navigation(page, mobile)
                        if args.artifacts:
                            args.artifacts.mkdir(parents=True, exist_ok=True)
                            await page.screenshot(path=args.artifacts / f'{language}-{width}x{height}.png')
                        if mobile:
                            await menu.tap()
                            await expect(menu).to_have_attribute('aria-expanded', 'true')
                            await check_layout(page, ['openRoom', 'logout'], width, height, ['openRoom', 'logout'])
                            if args.artifacts and width == 320:
                                await page.screenshot(path=args.artifacts / f'{language}-320-menu.png')
                            await page.keyboard.press('Escape')
                            await expect(menu).to_be_focused()
                            await expect(menu).to_have_attribute('aria-expanded', 'false')
                        checked.append({'language': language, 'viewport': [width, height], 'layout_copy_invite_menu': 'passed'})
                    # Desktop still exposes its existing actions and main navigation.
                    await page.locator('#openRoom').click()
                    await expect(page.get_by_role('dialog')).to_be_visible()
                    await page.keyboard.press('Escape')
                    nav = page.get_by_role('navigation', name='Site navigation' if english else '网站导航', exact=True)
                    await nav.locator('.nav-toggle').focus()
                    await page.keyboard.press('Enter')
                    await expect(nav.get_by_role('link', name='Viewing settings' if english else '观影设置')).to_be_visible()
                    await page.keyboard.press('Escape')
                    await page.set_viewport_size({'width': 320, 'height': 740})
                    await expect(menu).to_be_visible()
                    await check_actions(page, english, base_url)
                    await expect(host.locator('#connection')).to_contain_text('1 online' if english else '1 人在线')
                    await context.close()
                assert not errors, errors
                result = {'fixture': 'temporary loopback app, synthetic MOBILE16/NEXT16 rooms and viewers',
                          'matrix': checked, 'keyboard_touch_dismiss_and_dialog_focus': 'passed',
                          'switch_room_and_leave_authorization': 'passed', 'desktop_navigation': 'passed',
                          'browser_errors': errors,
                          'not_verified': ['real mobile devices', 'production deployment']}
                print(json.dumps(result, ensure_ascii=False, indent=2))
                if args.output:
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
            finally:
                await browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--output', type=Path)
    asyncio.run(run(parser.parse_args()))
