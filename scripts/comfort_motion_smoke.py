"""Exercise the optional room animation in a disposable room on a local preview."""
import argparse
from uuid import uuid4
from playwright.sync_api import sync_playwright, expect

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=18881)
    args = parser.parse_args()
    base = f'http://127.0.0.1:{args.port}'
    bundle = '/assets/comfort-motion-1.js'
    count = "document.querySelector('#roomOpening').getAnimations({subtree:true}).length"
    room = 'MC' + uuid4().hex[:6]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='chrome')
        page = browser.new_page(viewport={'width':1280,'height':800})
        requests = []
        page.on('request', lambda r: requests.append(r.url) if bundle in r.url else None)
        page.goto(base+'/')
        expect(page.locator('#gallery')).to_be_visible()
        assert not requests
        page.goto(base+'/?room='+room)
        page.wait_for_selector('[data-scene-choice=anime][aria-pressed=true]')
        section = page.locator('#roomOpening')
        section.evaluate("e=>e.scrollIntoView({block:'start',behavior:'instant'})")
        page.wait_for_function(count+'===4')
        page.evaluate("scrollBy({top:innerHeight*.45,behavior:'instant'})")
        page.wait_for_function("Number(getComputedStyle(document.querySelector('.comfort-intro')).opacity)<.95")
        assert len(requests)==1
        print('gallery: no library request; opening: one local import, four animated properties; title opacity changes with scroll')
        page.emulate_media(reduced_motion='reduce');page.wait_for_function(count+'===0')
        expect(page.locator('.comfort-panel')).to_have_css('transform','none')
        page.emulate_media(reduced_motion='no-preference');page.wait_for_function(count+'===4')
        page.evaluate("document.querySelector('#advancedControls').scrollIntoView({behavior:'instant'})");page.wait_for_function(count+'===0')
        section.evaluate("e=>e.scrollIntoView({block:'start',behavior:'instant'})")
        page.wait_for_function(count+'===4');assert len(requests)==1
        print('reduce motion/offscreen: zero chapter animations; return: no duplicate animations or fetch')
        page.close()
        for mode in ('reduce','failed-download'):
            p=browser.new_page(reduced_motion='reduce' if mode=='reduce' else 'no-preference')
            attempts=[]
            def block(route):
                attempts.append(1)
                route.abort()
            p.route('**'+bundle+'*',block)
            p.goto(base+'/?room='+room)
            p.wait_for_selector('[data-scene-choice=anime][aria-pressed=true]')
            p.locator('.comfort-foot a').click(); expect(p.locator('#videoStage')).to_be_in_viewport()
            p.locator('.comfort-panel summary').first.click(); p.locator('#pictureBrightness').fill('117')
            expect(p.locator('#brightnessValue')).to_have_text('117%')
            assert len(attempts)==(0 if mode=='reduce' else 1)
            assert p.evaluate(count)==0
            print(f'{mode}: usable settings, zero chapter animations')
            p.close()
        browser.close()

if __name__=='__main__':
    main()
