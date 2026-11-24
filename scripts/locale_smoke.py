"""Opt-in: python -m scripts.locale_smoke [--output evidence.json] [--artifacts DIR].

Requires optional Playwright + local Chrome and ffmpeg. Starts a loopback-only
app with temporary generated media; never reads a deployment or personal library.
"""
import argparse
import asyncio
import json
import re
import subprocess
import tempfile
from pathlib import Path

from aiohttp.test_utils import TestServer
from playwright.async_api import async_playwright, expect
from cinema.server import create_app


OBSERVE = """(() => {
  window.localeEvidence={controls:[],mediaEvents:[],sockets:0};
  let languageEvent=false;
  document.addEventListener('change',e=>{if(e.target.id==='interfaceLanguage')languageEvent=true},true);
  document.addEventListener('change',()=>{languageEvent=false});
  const send=WebSocket.prototype.send;
  WebSocket.prototype.send=function(data){
    if(languageEvent)localeEvidence.controls.push(JSON.parse(data));
    return send.call(this,data);
  };
  const NativeSocket=WebSocket;
  window.WebSocket=class extends NativeSocket {constructor(...args){super(...args);localeEvidence.sockets++}};
})();"""


async def run(args):
    with tempfile.TemporaryDirectory(prefix='cinema-locale-') as directory:
        root = Path(directory)
        app = create_app(root, 'locale-synthetic-secret', secure=False)
        name = '原片名-original.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=10',
                        '-f', 'lavfi', '-i', 'sine=frequency=440', '-t', '90', '-c:v', 'libx264',
                        '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags',
                        '+faststart', str(root / 'media' / name)], check=True, capture_output=True)
        subtitles = root / 'subtitles' / name
        subtitles.mkdir(parents=True)
        (subtitles / 'tracks.json').write_text(json.dumps({'tracks': [
            {'id': '1', 'label': '原文字幕 Original track', 'lang': 'zh', 'default': True}], 'unsupported_count': 0}))
        cue = '原文字幕 Original cue'
        (subtitles / '1.vtt').write_text('WEBVTT\n\n00:00.000 --> 01:30.000\n' + cue + '\n')
        async with TestServer(app, host='127.0.0.1') as server, async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel='chrome')
            errors = []
            try:
                contexts = [await browser.new_context(locale='zh-CN', timezone_id='Asia/Shanghai') for _ in range(2)]
                pages = []
                for index, context in enumerate(contexts):
                    await context.add_init_script(OBSERVE)
                    await context.add_init_script("localStorage.setItem('watchNickname', '原昵称" + str(index) + "')")
                    page = await context.new_page()
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    await page.goto(str(server.make_url('/?room=LANG14')))
                    await expect(page.locator('#connection')).to_contain_text('在线')
                    await page.locator('#roomLabel').click()  # Real audio activation for the guest.
                    pages.append(page)
                host, guest = pages
                await expect(host.locator('#connection')).to_contain_text('2 人在线')
                await host.get_by_role('tab', name='片库', exact=True).click()
                await host.locator('#library').get_by_role('button', name=re.compile(re.escape(name))).click()
                for page in pages:
                    await page.wait_for_function("document.querySelector('#video').readyState>=2 && document.querySelector('#video').textTracks[0]?.mode==='showing'")
                await host.locator('#videoStage').hover()
                await host.get_by_label('播放', exact=True).click()
                for page in pages:
                    await page.wait_for_function("!document.querySelector('#video').paused && document.querySelector('#video').currentTime>1")
                    await expect(page.locator('#memoryList time')).to_have_count(1)
                await host.get_by_role('tab', name='聊天', exact=True).click()
                await host.get_by_role('textbox', name='聊天消息', exact=True).fill('聊天原文 Original chat')
                await host.get_by_role('button', name='发送', exact=True).click()
                await host.get_by_role('textbox', name='弹幕内容', exact=True).fill('弹幕原文 Original comment')
                await host.get_by_role('button', name='发送弹幕', exact=True).click()
                for page in pages:
                    await expect(page.locator('.chat-bubble')).to_have_text('聊天原文 Original chat')
                    await expect(page.locator('#danmakuText')).to_have_value('')
                await expect(host.locator('#danmakuLayer')).to_contain_text('弹幕原文 Original comment')
                comments_url = '/api/danmaku/' + name + '?room=LANG14'
                comments_before = await (await host.request.get(str(server.make_url(comments_url)))).json()
                assert comments_before['comments'][0]['text'] == '弹幕原文 Original comment'
                before_dates = [await page.locator('#memoryList time').inner_text() for page in pages]
                before_times = []
                for page in pages:
                    before_times.append(await page.locator('#video').evaluate("v=>{window.originalMedia={video:v,player:watchArt,track:v.textTracks[0]};for(const event of ['loadstart','emptied'])v.addEventListener(event,()=>localeEvidence.mediaEvents.push(event));return v.currentTime}"))
                await host.get_by_role('combobox', name='界面语言', exact=True).select_option('en')
                await expect(host.locator('html')).to_have_attribute('lang', 'en')
                await expect(guest.locator('html')).to_have_attribute('lang', 'zh-CN')
                await expect(host.locator('#comfortSheetTitle')).to_have_text('Viewing settings')
                await expect(host.get_by_role('button', name='Copy invite', exact=True)).to_be_visible()
                await expect(host.get_by_role('textbox', name='Timed comment text', exact=True)).to_have_attribute('placeholder', 'Comment…')
                await expect(host.locator('#hostHint')).to_contain_text('You are the host')
                assert await host.locator('#memoryList time').inner_text() != before_dates[0]
                assert await guest.locator('#memoryList time').inner_text() == before_dates[1]
                for page, before in zip(pages, before_times):
                    await expect(page.locator('#title')).to_have_text(name)
                    await expect(page.locator('.chat-bubble')).to_have_text('聊天原文 Original chat')
                    await expect(page.locator('.chat-meta')).to_contain_text('原昵称0')
                    await page.wait_for_function("before=>document.querySelector('#video').currentTime>before+1 && !document.querySelector('#video').paused", arg=before)
                    assert await page.evaluate("originalMedia.video===document.querySelector('#video') && originalMedia.player===watchArt && originalMedia.track===document.querySelector('#video').textTracks[0]")
                    assert await page.locator('#video').evaluate("v=>v.textTracks[0].activeCues[0].text") == cue
                    evidence = await page.evaluate('localeEvidence')
                    assert evidence == {'controls': [], 'mediaEvents': [], 'sockets': 1}, evidence
                assert await (await host.request.get(str(server.make_url(comments_url)))).json() == comments_before
                drift = abs(await host.locator('#video').evaluate('v=>v.currentTime') - await guest.locator('#video').evaluate('v=>v.currentTime'))
                assert drift < 1.5, drift
                await host.locator('#videoStage').hover()
                await host.get_by_label('Show settings', exact=True).click()
                await expect(host.locator('.art-settings')).to_contain_text('Synchronized speed')
                await expect(host.locator('.art-settings')).to_contain_text('Subtitles')
                await expect(host.locator('.art-settings')).to_contain_text('Aspect ratio')
                await expect(host.locator('.art-settings')).to_contain_text('Video flip')
                await host.locator('.art-setting-item[data-name="aspect-ratio"]').click()
                await expect(host.locator('.art-setting-panel.art-current')).to_contain_text('Default')
                # Switch back and forth with cached player submenu/header nodes.
                for language in ['zh-CN', 'en']:
                    await host.locator('#interfaceLanguage').select_option(language)
                await host.get_by_role('tab', name='Library', exact=True).click()
                await host.locator('details.network-video summary').click()
                await host.get_by_role('textbox', name='Video webpage or HTTPS media URL', exact=True).fill('http://localhost/private')
                await host.get_by_role('button', name='Find videos', exact=True).click()
                await expect(host.locator('#networkStatus')).to_contain_text('No playable public media')
                await expect(host.locator('#title')).to_have_text(name)
                await expect(host.locator('#connection')).to_contain_text('2 online')
                await expect(host.locator('#library')).to_contain_text(name)
                if args.artifacts:
                    args.artifacts.mkdir(parents=True, exist_ok=True)
                    await host.locator('#videoStage').scroll_into_view_if_needed()
                    await host.screenshot(path=args.artifacts / 'english-screening.png')
                    await host.locator('#comfortSettings').scroll_into_view_if_needed()
                    await host.screenshot(path=args.artifacts / 'english-settings.png')
                # Refresh restores the explicit choice even with a Chinese browser.
                await host.reload()
                await expect(host.locator('html')).to_have_attribute('lang', 'en')
                await expect(host.locator('#interfaceLanguage')).to_have_value('en')
                for locale, expected in [('en-GB', 'en'), ('ja-JP', 'zh-CN')]:
                    context = await browser.new_context(locale=locale)
                    page = await context.new_page()
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    await page.goto(str(server.make_url('/')))
                    await expect(page.locator('html')).to_have_attribute('lang', expected)
                    await context.close()
                blocked = await browser.new_context(locale='en-US')
                await blocked.add_init_script("Object.defineProperty(window,'localStorage',{get(){throw new DOMException('Storage blocked','SecurityError')}})")
                page = await blocked.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                await page.goto(str(server.make_url('/?room=NOSAVE')))
                await expect(page.locator('#connection')).to_contain_text('online')
                await page.get_by_role('combobox', name='Interface language', exact=True).select_option('zh-CN')
                await expect(page.get_by_role('button', name='复制邀请', exact=True)).to_be_visible()
                await page.get_by_role('combobox', name='界面语言', exact=True).select_option('en')
                await expect(page.get_by_role('button', name='Copy invite', exact=True)).to_be_visible()
                await blocked.close()
                assert not errors, errors
                result = {'fixture': 'temporary generated 90s H.264/AAC film and original VTT',
                          'independent_contexts': 2, 'host_language': 'en', 'guest_language': 'zh-CN',
                          'media_reloads': 0, 'socket_reconnects': 0, 'language_triggered_messages': 0,
                          'playback_drift_seconds': round(drift, 3), 'original_title_nickname_chat_danmaku_subtitle': 'unchanged',
                          'player_menus_dates_accessible_names': 'passed', 'refresh_preference': 'passed',
                          'browser_matching_fallback': 'passed', 'blocked_storage': 'passed',
                          'stable_network_error': 'passed', 'browser_errors': errors,
                          'not_verified': ['production deployment', 'real mobile devices', 'external media providers']}
                print(json.dumps(result, ensure_ascii=False, indent=2))
                if args.output:
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
            finally:
                await browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--artifacts', type=Path)
    asyncio.run(run(parser.parse_args()))
