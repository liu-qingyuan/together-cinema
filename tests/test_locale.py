"""Translation completeness is part of the root CI regression command."""
import json
import re
import tempfile
import unittest
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer
from cinema.server import create_app

ROOT = Path(__file__).resolve().parents[1]


def load_messages():
    source = (ROOT / 'web/assets/locale-messages.js').read_text()
    return json.loads(source.split('globalThis.CinemaMessages = ', 1)[1].removesuffix(';\n'))


def validate_messages(messages):
    for key, variants in messages.items():
        if set(variants) != {'zh-CN', 'en'} or any(not isinstance(v, str) or not v.strip() for v in variants.values()):
            raise ValueError('Missing locale: ' + key)
        placeholders = [set(re.findall(r'\{(\w+)\}', text)) for text in variants.values()]
        if placeholders[0] != placeholders[1]:
            raise ValueError('Interpolation mismatch: ' + key)


class TranslationContract(unittest.TestCase):
    def test_dictionary_and_first_party_references_are_complete(self):
        messages = load_messages()
        validate_messages(messages)
        paths = [ROOT / 'web/index.html'] + [ROOT / ('web/assets/' + name) for name in
            ['site-nav.js', 'memory-reel.js', 'room-atlas-v2.js', 'locale.js']]
        prefixes = '|'.join(sorted({key.split('.')[0] for key in messages}))
        for path in paths:
            source = path.read_text()
            # Includes ternary branches and lookup tables, not just direct t() calls.
            keys = re.findall(r"['\"]((?:" + prefixes + r")\.[A-Za-z][\w.]*)['\"]", source)
            keys += re.findall(r'data-i18n(?:-html|-aria-label|-title|-placeholder|-href)?="([\w.]+)"', source)
            keys += re.findall(r"\b(?:t|m|message|failure|localeHTML)\('([\w]+\.[\w.]+)'\)", source)
            for key in keys:
                if key.endswith('.'):
                    continue
                with self.subTest(path=str(path.relative_to(ROOT)), key=key):
                    self.assertTrue(key in messages, 'Missing translation key: ' + key)
        for work in json.loads((ROOT / 'web/assets/scenes/sources.json').read_text()):
            if work.get('collection') == 'room':
                for prefix in ['atlas.scene.', 'atlas.genre.']:
                    self.assertIn(prefix + work['key'], messages)
        for path in [ROOT / 'cinema/server.py', ROOT / 'cinema/external_media.py']:
            for code in re.findall(r"['\"](?:X-Cinema-Error|code|error_code)['\"]\s*[:=]\s*['\"]([\w]+)['\"]", path.read_text()):
                self.assertIn('error.' + code, messages)

    def test_missing_language_and_mismatched_interpolation_are_rejected(self):
        for broken in [{'key': {'zh-CN': '中文'}}, {'key': {'zh-CN': '{name}', 'en': '{other}'}}]:
            with self.subTest(broken=broken), self.assertRaises(ValueError):
                validate_messages(broken)


class LocalizedErrors(unittest.IsolatedAsyncioTestCase):
    async def test_errors_add_stable_ids_without_changing_legacy_text(self):
        with tempfile.TemporaryDirectory() as directory:
            async with TestClient(TestServer(create_app(Path(directory), 'locale-test-secret', secure=False))) as client:
                response = await client.post('/api/login', json={'room': 'A'})
                self.assertEqual(response.status, 400)
                self.assertEqual(response.headers.get('X-Cinema-Error'), 'room_code_invalid')
                self.assertEqual(await response.text(), '房间码为 2～8 位字母或数字')
                response = await client.get('/api/library')
                self.assertEqual(response.headers.get('X-Cinema-Error'), 'login_required')
                self.assertEqual(await response.text(), '请先登录')
                await client.post('/api/login', json={'room': 'AB'})
                response = await client.post('/api/network/resolve', json={'url': 'http://localhost/private'})
                self.assertEqual(response.headers.get('X-Cinema-Error'), 'network_invalid')
                self.assertTrue(await response.text())
                socket = await client.ws_connect('/ws?room=AB')
                await socket.receive_json()
                await socket.receive_json()
                await socket.send_json({'type': 'chat', 'text': ''})
                message = await socket.receive_json()
                self.assertEqual(message['code'], 'chat_invalid')
                self.assertEqual(message['error'], '消息为1～300字，请勿连续刷屏')
                await socket.close()
