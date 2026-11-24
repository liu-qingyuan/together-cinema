from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import urlsplit

from docs.site.build import build


class Links(HTMLParser):
    def __init__(self, file):
        super().__init__()
        self.ids = set()
        self.urls = []
        self.feed(file.read_text())

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if 'id' in values:
            self.ids.add(values['id'])
        for attr in ('src', 'href'):
            if attr in values:
                self.urls.append(values[attr])


class ProjectSiteTest(unittest.TestCase):
    def test_public_files_and_project_relative_links(self):
        with TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            build(root)
            self.assertEqual({p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()},
                             {'index.html', 'zh-CN/index.html', 'help/en.html', 'help/zh-CN.html',
                              'assets/site.css', 'assets/guide.css', 'assets/hero.webp'})
            for doc in root.rglob('*.html'):
                for raw in Links(doc).urls:
                    with self.subTest(doc=doc.relative_to(root), link=raw):
                        url = urlsplit(raw)
                        if url.scheme:
                            self.assertEqual(url.scheme, 'https')
                            continue
                        self.assertFalse(url.netloc or url.path.startswith('/'))
                        target = (doc.parent / url.path).resolve() if url.path else doc
                        if target.is_dir():
                            target /= 'index.html'
                        self.assertTrue(target.is_relative_to(root.resolve()) and target.is_file())
                        if url.fragment:
                            self.assertIn(url.fragment, Links(target).ids)
