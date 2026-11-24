"""Rephotograph Pages in an isolated demo: python -m scripts.capture_site_shots.

Requires ffmpeg, cwebp, Chrome, Playwright and the application's Python deps.
"""
import asyncio
from pathlib import Path
import re
import struct
import subprocess
import tempfile

from aiohttp.test_utils import TestServer
from playwright.async_api import async_playwright, expect

from cinema.server import create_app


OUT = Path(__file__).resolve().parents[1] / 'docs/site/shots'


async def capture(browser, lang, root):
    media = root / 'data'
    app = create_app(media, 'local-shots-only', secure=False)
    for title, color in [('Cloud Atlas', 'skyblue'), ('After the Rain', 'teal')]:
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', f'color=c={color}:s=320x180',
                        '-t', '2', '-c:v', 'libx264', str(media / 'media' / (title + '.mp4'))], check=True)
    demo = root / 'Sky study.mp4'
    demo.write_bytes((media / 'media/Cloud Atlas.mp4').read_bytes())
    with demo.open('ab') as fp:
        size = 12 * 1024**2
        fp.write(struct.pack('>I4s', size, b'free') + bytes(size - 8))
    async with TestServer(app) as server:
        ctx = await browser.new_context(locale=lang, viewport={'width':540, 'height':1050},
                                        device_scale_factor=1.6, reduced_motion='reduce')
        try:
            await ctx.add_init_script("if (!localStorage.getItem('together-cinema.appearance')) localStorage.setItem('together-cinema.appearance','day')")
            p = await ctx.new_page()
            async def snap(key, selector):
                png = root / (key + '.png')
                await p.locator(selector).screenshot(path=png, animations='disabled')
                subprocess.run(['cwebp', '-quiet', '-q', '88', str(png), '-o', str(OUT / f'{lang}-{key}.webp')],check=True)
            await p.goto(str(server.make_url('/?room=SKY01')))
            await expect(p.locator('#connection')).to_contain_text('Host' if lang=='en' else '房主')
            await p.locator('[data-tab=library]').click()
            await expect(p.locator('#library')).to_contain_text('After the Rain')
            await snap('library', '#tab-library')
            await p.locator('.network-video summary').click()
            await p.locator('#networkUrl').fill('https://media.example.org/sky.mp4')
            for mode in ('direct', 'relay'):
                await p.locator('#networkMode').select_option(mode)
                await p.locator('#networkMode').blur()
                await snap(mode, '.network-video')
            await p.locator('.network-video summary').click()
            await p.locator('.library-upload summary').click()
            await p.locator('#file').set_input_files(demo)
            cdp = await ctx.new_cdp_session(p)
            await cdp.send('Network.enable')
            await cdp.send('Network.emulateNetworkConditions', {'offline':False, 'latency':20,
                           'downloadThroughput':10*1024**2, 'uploadThroughput':1024**2})
            await p.locator('#upload').click()
            await expect(p.locator('#uploadStatus')).to_have_text(re.compile(r'\d\d:\d\d:\d\d'), timeout=30000)
            await snap('upload', '.library-upload')
            await expect(p.locator('#uploadStatus')).to_contain_text('Upload complete' if lang=='en' else '并行上传完成',timeout=60000)
            await p.evaluate("localStorage.setItem('together-cinema.appearance','night')")
            await p.reload()
            await p.locator('.voice-settings summary').click()
            await expect(p.locator('html')).to_have_attribute('data-appearance','night')
            await snap('voice', '.voice-dock')  # Never joins the call or opens a microphone.
        finally:
            await ctx.close()


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel='chrome')
        try:
            for lang in ('en','zh-CN'):
                with tempfile.TemporaryDirectory() as tmp:
                    await capture(browser, lang, Path(tmp))
        finally:
            await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
