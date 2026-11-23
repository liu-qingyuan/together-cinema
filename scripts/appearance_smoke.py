"""Local Playwright smoke: day/night schedule, overrides and room isolation."""
import sys
from playwright.sync_api import sync_playwright, expect


def theme(page, name):
    expect(page.locator('html')).to_have_attribute('data-appearance', name)


def choose(page, value):
    expect(page.locator('#siteNav #appearanceMode')).to_have_count(0)
    page.locator('#comfortSettings').get_by_label('外观模式', exact=True).select_option(value)


def run(browser, url):
    ctx = browser.new_context(timezone_id='Asia/Singapore', viewport={'width':1280,'height':800})
    page = ctx.new_page()
    page.clock.install(time='2026-11-24T18:58:00+08:00')
    page.goto(url + '/?room=01#together')
    expect(page.locator('#connection')).to_contain_text('在线')
    theme(page, 'day')
    page.evaluate('window.originalPlayer = {ws, video}')
    page.clock.pause_at('2026-11-24T18:59:59+08:00')
    page.clock.fast_forward(1000)
    theme(page, 'night')
    expect(page.locator('.memory-book')).to_have_css('background-color','rgb(32, 34, 37)')
    page.clock.fast_forward(12*60*60*1000)
    theme(page,'day')
    choose(page,'night')
    theme(page,'night')
    assert page.evaluate('originalPlayer.ws===ws && ws.readyState===1 && originalPlayer.video===video')
    page.clock.fast_forward(24*60*60*1000)
    theme(page,'night')
    page.reload();theme(page,'night')
    other=ctx.new_page();other.goto(url+'/');theme(other,'night')
    expect(other.locator('#appearanceMode')).not_to_be_visible()
    choose(page,'day');theme(other,'day');theme(page,'day')
    choose(page,'auto');theme(page,'day')
    ctx.close()
    # At this instant it is 19:10 in Tokyo but still 18:10 in Singapore.
    ctx = browser.new_context(timezone_id='Asia/Tokyo', viewport={'width':390,'height':844}, has_touch=True)
    mobile=ctx.new_page();mobile.clock.set_fixed_time('2026-11-24T10:10:00Z')
    mobile.goto(url+'/?room=01#comfortSettings');theme(mobile,'night')
    choose(mobile,'day')
    theme(mobile,'day');assert mobile.evaluate('document.documentElement.scrollWidth<=innerWidth')
    ctx.close()
    print('19:00 switched to night; 07:00 switched to day; manual choice survived a whole day and reload; gallery and room tabs synced; reselecting auto restored schedule. Video and socket retained. settings-only selector on desktop and Tokyo mobile passed.')


if __name__=='__main__':
    with sync_playwright() as p:
        b=p.chromium.launch(channel='chrome');run(b,sys.argv[1]);b.close()
