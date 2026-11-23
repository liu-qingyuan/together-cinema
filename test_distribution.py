import tempfile,unittest
from pathlib import Path
from aiohttp.test_utils import TestClient,TestServer
from server import create_app
class SceneDistributionTests(unittest.IsolatedAsyncioTestCase):
 async def test_shipped_scene_and_credits_work_without_external_nginx(self):
  with tempfile.TemporaryDirectory() as d:
   async with TestClient(TestServer(create_app(Path(d),'distribution-fixture-secret',secure=False))) as c:
    r=await c.get('/scenes/v1-anime.svg');self.assertEqual(r.status,200);self.assertEqual(r.content_type,'image/webp');self.assertEqual(r.url.path,'/room-art/anime-wide.webp')
    r=await c.get('/scenes/sources.json');self.assertEqual(r.status,200);rooms=[x for x in await r.json() if x.get('collection')=='room'];self.assertEqual(len(rooms),8)
    for work in rooms:
     self.assertTrue(work['author']);self.assertTrue(work['source'].startswith('https://'));self.assertTrue(work['license'])
     for variant in ('thumb','compact','wide'):
      image=await c.get(f"/room-art/{work['key']}-{variant}.webp");self.assertEqual(image.status,200);self.assertEqual((await image.read())[:4],b'RIFF')
    self.assertEqual((await c.get('/room-art/missing-wide.webp')).status,404)
    for name in ['secret.svg','sources.json.bak','v1-anime.svg%2f..%2fserver.py']:
     self.assertEqual((await c.get('/scenes/'+name)).status,404)
 async def test_gallery_variants_and_attribution_ship_through_existing_asset_route(self):
  with tempfile.TemporaryDirectory() as d:
   async with TestClient(TestServer(create_app(Path(d),'distribution-fixture-secret',secure=False))) as c:
    for key in ['sky','galaxy']:
     for size in ['desktop','mobile']:
      r=await c.get(f'/scenes/v1-{key}-{size}.webp');self.assertEqual(r.status,200)
      self.assertEqual(r.content_type,'image/webp');self.assertEqual((await r.read())[:4],b'RIFF')
      self.assertEqual(r.headers['X-Content-Type-Options'],'nosniff')
    credits=await (await c.get('/scenes/sources.json')).json()
    for key in ['sky','galaxy']:
     credit=next(row for row in credits if row['key']==key)
     self.assertEqual(credit['license'],'CC BY 4.0');self.assertTrue(credit['author']);self.assertTrue(credit['changes'])
     self.assertTrue(credit['source'].startswith('https://'))
     self.assertEqual(len(credit['files']),2)
    r=await c.get('/scenes/LICENSE-CC-BY-4.0.txt');self.assertEqual(r.status,200)
    self.assertIn('Attribution 4.0 International',await r.text())
    self.assertEqual((await c.get('/scenes/v1-galaxy-original.jpg')).status,404)
