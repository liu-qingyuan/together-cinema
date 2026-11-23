"""Exercise the journal's cylinder edges in an empty local preview room."""
import argparse
from playwright.sync_api import sync_playwright, expect


def measure(page, degrees):
    page.evaluate("""angle => {
        const section = document.querySelector('#together');
        const span = section.offsetHeight - section.firstElementChild.offsetHeight;
        const index = 4 + angle * Math.PI / (180 * .54);
        scrollTo({top: scrollY + section.getBoundingClientRect().top + span * index / 9,
                  behavior: 'instant'});
    }""", degrees)
    page.evaluate("() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)))")
    return page.locator('#memoryList li b').nth(4).evaluate("""title => ({
        shown: getComputedStyle(title).visibility === 'visible',
        height: title.getBoundingClientRect().height
    })""")


def check(page, url):
    page.goto(url)
    expect(page.locator('#connection')).to_contain_text('在线')
    expect(page.locator('#together')).to_have_attribute('data-mode', 'sample')
    for direction in (1, -1):
        samples = [measure(page, a * direction) for a in (0, 55, 76, 84, 89, 91)]
        assert all(s['shown'] for s in samples[:-1]) and not samples[-1]['shown'], samples
        heights = [s['height'] for s in samples[:-1]]
        assert all(a > b for a, b in zip(heights, heights[1:])) and heights[-1] < 2, heights
        back = measure(page, 76 * direction)
        assert back['shown'] and abs(back['height'] - heights[2]) < .1, back
    page.emulate_media(reduced_motion='reduce')
    assert abs(measure(page, 0)['height'] - measure(page, 55)['height']) < 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url', help='preview URL with an empty room and #together')
    args = parser.parse_args()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome')
        for width, height in [(1280, 800), (768, 1024), (390, 844)]:
            page = browser.new_page(viewport={'width': width, 'height': height})
            check(page, args.url)
            print(f'{width}px: both edges roll continuously to <2px, reverse matches; reduced motion stays flat.')
            page.close()
        browser.close()
