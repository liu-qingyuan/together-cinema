"""The viewer guide is a public, independently shareable static surface."""
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer
from cinema.server import create_app


class GuideLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.language = None
        self.styles = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'html':
            self.language = attrs.get('lang')
        if tag == 'a':
            self.links.append(attrs)
        if tag == 'link' and attrs.get('rel') == 'stylesheet':
            self.styles.append(attrs['href'])


class DiscoveryFailure(unittest.IsolatedAsyncioTestCase):
    async def test_unreachable_optional_extractor_has_an_actionable_stable_error(self):
        from aiohttp import ClientConnectionError
        from unittest.mock import AsyncMock, patch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = create_app(root, 'help-test-secret', secure=False)
            (root / 'media/current.mp4').write_bytes(b'owned fixture')
            async with TestClient(TestServer(app)) as client:
                await client.post('/api/login', json={'room': 'HELP15'})
                socket = await client.ws_connect('/ws?room=HELP15')
                await socket.receive_json()
                await socket.receive_json()
                await socket.send_json({'type': 'control', 'file': 'current.mp4', 'paused': True, 'position': 7})
                await socket.receive_json()
                with patch('cinema.server.ExternalMedia.resolve', new=AsyncMock(side_effect=ClientConnectionError('extractor unavailable'))):
                    response = await client.post('/api/network/resolve', json={'url': 'https://media.example/empty'})
                self.assertEqual(response.status, 502)
                self.assertEqual(response.headers['X-Cinema-Error'], 'network_resolve_failed')
                await socket.send_json({'type': 'ping'})
                state = await socket.receive_json()
                self.assertEqual(state['file'], 'current.mp4')
                self.assertEqual(state['position'], 7)
                await socket.close()


class PublicGuide(unittest.IsolatedAsyncioTestCase):
    async def test_gallery_and_room_link_to_the_localized_guide_in_a_new_tab(self):
        from tests.test_locale import load_messages
        messages = load_messages()
        with tempfile.TemporaryDirectory() as directory:
            async with TestClient(TestServer(create_app(Path(directory), 'help-test-secret', secure=False))) as client:
                source = await (await client.get('/')).text()
                page = GuideLinks()
                page.feed(source)
                links = [a for a in page.links if a.get('data-i18n-href') == 'guide.url']
                self.assertEqual(len(links), 2, 'Gallery and room must both offer help')
                for link in links:
                    self.assertEqual(link['target'], '_blank')
                    self.assertIn('noopener', link['rel'].split())
                    self.assertEqual(link.get('data-i18n-aria-label', link['data-i18n']), 'guide.open')
                    self.assertEqual((await client.get(link['href'])).status, 200)
                for language in ['zh-CN', 'en']:
                    url = messages['guide.url'][language]
                    self.assertEqual((await client.get(url)).status, 200)
                    self.assertNotIn('YouTube', messages['network.hint'][language])

    async def test_both_guides_are_readable_without_joining_or_authorizing(self):
        with tempfile.TemporaryDirectory() as directory:
            async with TestClient(TestServer(create_app(Path(directory), 'help-test-secret', secure=False))) as client:
                for language in ['zh-CN', 'en']:
                    with self.subTest(language=language):
                        response = await client.get('/help/' + language + '.html')
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.content_type, 'text/html')
                        self.assertEqual(response.headers['Cache-Control'], 'no-store')
                        self.assertNotIn('Set-Cookie', response.headers)
                        source = await response.text()
                        page = GuideLinks()
                        page.feed(source)
                        self.assertEqual(page.language, language)
                        self.assertNotIn('<script', source)
                        self.assertIn('/help/zh-CN.html', [a.get('href') for a in page.links])
                        self.assertIn('/help/en.html', [a.get('href') for a in page.links])
                        self.assertTrue(page.styles)
                        for stylesheet in page.styles:
                            self.assertEqual((await client.get(stylesheet)).status, 200)
                self.assertEqual((await client.get('/api/library')).status, 401)
                for url in ['/help/server.py', '/help/index.html', '/help/%2e%2e/server.py']:
                    self.assertEqual((await client.get(url)).status, 404)
