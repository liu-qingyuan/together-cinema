import tempfile,unittest
from pathlib import Path
from aiohttp.test_utils import TestClient,TestServer
from server import create_app
class SceneDistributionTests(unittest.IsolatedAsyncioTestCase):
 async def test_shipped_scene_and_credits_work_without_external_nginx(self):
  with tempfile.TemporaryDirectory() as d:
   async with TestClient(TestServer(create_app(Path(d),'distribution-fixture-secret',secure=False))) as c:
    r=await c.get('/scenes/v1-anime.svg');self.assertEqual(r.status,200);self.assertIn('<svg',await r.text());self.assertEqual(r.content_type,'image/svg+xml')
    r=await c.get('/scenes/sources.json');self.assertEqual(r.status,200);self.assertEqual(len(await r.json()),6)
    for name in ['secret.svg','sources.json.bak','v1-anime.svg%2f..%2fserver.py']:
     self.assertEqual((await c.get('/scenes/'+name)).status,404)
