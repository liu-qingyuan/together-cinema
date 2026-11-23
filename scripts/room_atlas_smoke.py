"""Check room-local scenery with Chrome on the loopback preview; no library or cover writes."""
import argparse
import uuid
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=18880)
    parser.add_argument('--artifacts', type=Path)
    args = parser.parse_args()
    room = 'SC' + uuid.uuid4().hex[:6].upper()
    url = f'http://127.0.0.1:{args.port}/?room={room}#atmosphere'
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='chrome', args=['--autoplay-policy=no-user-gesture-required'])
        for size in [(1360,870), (390,844)]:
            context = browser.new_context(viewport=dict(zip(('width','height'),size)))
            page = context.new_page()
            errors, writes, media_events = [], [], []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.on('request', lambda r: writes.append(r.url) if '/covers' in r.url and r.method not in ('GET','HEAD') else None)
            page.on('websocket', lambda ws: ws.on('framesent', lambda f: media_events.append(f) if any(x in str(f) for x in ('"type":"control"','"type":"boost"')) else None))
            page.goto(url)
            expect(page.locator('.cover-manager,#coverUpload')).to_have_count(0)
            art = page.locator('.atlas-art')
            expect(page.locator('#atlasTitle')).to_be_visible()
            expect(page.locator('[data-scene-choice]')).to_have_count(8)
            expect(page.locator('.scene-choice[aria-pressed=true]')).to_have_count(1)
            initial = page.evaluate(r"performance.getEntriesByType('resource').map(r=>new URL(r.name).pathname).filter(n=>/\/room-art\/.*-(wide|compact)\.webp$/.test(n))")
            assert len(set(initial)) == 1, initial
            expect(page.locator('#atlasName')).to_have_text('盛夏晴空')
            expect(page.locator('#atlasCredit')).to_have_text('Unicorn Creates · 原作 ↗')
            for c in page.locator('[data-scene-choice]').all():
                c.click()
                expect(c).to_have_attribute('aria-pressed','true')
                expect(page.locator('#atlasName')).to_have_text(c.locator('b').inner_text())
                key = c.get_attribute('data-scene-choice')
                assert page.locator('#atlasCredit').get_attribute('href').startswith('https://')
                assert key in art.evaluate('(e)=>getComputedStyle(e).backgroundImage')
                assert key in page.locator('.comfort-photo').evaluate('(e)=>getComputedStyle(e).backgroundImage')
            assert not writes and not media_events
            page.reload()
            expect(page.locator('[data-scene-choice=tech]')).to_have_attribute('aria-pressed','true')
            page.locator('[data-scene-choice=anime]').click()
            page.wait_for_timeout(560)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            if args.artifacts:
                args.artifacts.mkdir(parents=True,exist_ok=True)
                page.locator('#atmosphere').screenshot(path=str(args.artifacts/f'room-{size[0]}.jpg'),type='jpeg',quality=87)
            page.locator('#sceneMotion').uncheck()
            expect(page.locator('body')).not_to_have_attribute('data-room-motion','')
            page.locator('#sceneMotion').check()
            page.emulate_media(reduced_motion='reduce')
            expect(page.locator('body')).not_to_have_attribute('data-room-motion','')
            page.emulate_media(reduced_motion='no-preference')
            page.evaluate("""async () => {const c=document.createElement('canvas'); c.width=80;c.height=60;
              const v=document.querySelector('#video'); v.muted=true; v.srcObject=c.captureStream(1); c.getContext('2d').fillRect(0,0,80,60); await v.play();}""")
            expect(page.locator('body')).not_to_have_attribute('data-room-motion','')
            page.locator('[data-scene-choice=tech]').click()
            expect(page.locator('#atlasName')).to_have_text('涩谷十字路口')
            assert page.evaluate('!document.querySelector("#video").paused && !!document.querySelector("#video").srcObject && !document.querySelector(".atlas-art").getAnimations().length')
            assert not errors, errors
            context.close()
            print(f'{size}: eight licensed image scenes, hero match, private persistence, no cover writes/control, motion fallback and uninterrupted local stream OK')
        browser.close()
if __name__=='__main__':
    main()
