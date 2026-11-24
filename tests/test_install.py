import os,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class InstallerTests(unittest.TestCase):
 def test_help_is_usable_without_docker_or_secret_creation(self):
  p=subprocess.run(['sh',str(ROOT/'install.sh'),'--help'],capture_output=True,text=True)
  self.assertEqual(p.returncode,0,p.stderr)
  self.assertIn('--network',p.stdout)
 def sandbox(self):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
  for n in ['install.sh','uninstall.sh']:shutil.copy2(ROOT/n,root/n)
  (root/'bin').mkdir();stub=root/'bin/docker';stub.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$DOCKER_LOG"\nif [ "$1" = info ] && [ "${FAKE_DOWN:-}" = 1 ]; then exit 1; fi\nif [ "$1" = context ]; then echo fixture-context; fi\nexit 0\n');stub.chmod(0o755)
  env=os.environ.copy();env['PATH']=str(root/'bin')+os.pathsep+env['PATH'];env['DOCKER_LOG']=str(root/'commands');return root,env
 def run_install(self,root,env,*args):return subprocess.run(['sh',str(root/'install.sh'),*args],env=env,capture_output=True,text=True)
 def test_check_generates_private_unique_secrets_without_starting(self):
  root,env=self.sandbox();p=self.run_install(root,env,'--check');self.assertEqual(p.returncode,0,p.stderr);data=dict(x.split('=',1) for x in (root/'.env').read_text().splitlines());self.assertEqual(len(data['WATCH_PASSWORD']),64);self.assertNotEqual(data['WATCH_PASSWORD'],data['SITE_PASSWORD']);self.assertEqual((root/'.env').stat().st_mode&0o777,0o600);self.assertNotIn(' up ',(root/'commands').read_text());self.assertNotIn(data['WATCH_PASSWORD'],p.stdout+p.stderr)
 def test_repeat_preserves_secret_and_merges_profiles(self):
  root,env=self.sandbox();self.assertEqual(self.run_install(root,env,'--check').returncode,0);old=(root/'.env').read_text().splitlines()[0];p=self.run_install(root,env,'--check','--network','--domain','cinema.example.com','--port','18080');self.assertEqual(p.returncode,0,p.stderr);text=(root/'.env').read_text();self.assertEqual(text.splitlines()[0],old);self.assertIn('COMPOSE_PROFILES=network,https',text);self.assertIn('COOKIE_SECURE=true',text);self.assertIn('HOST_PORT=18080',text);self.assertFalse((root/'.install.lock').exists())
 def test_install_waits_and_preserves_data_no_backup_or_prune(self):
  root,env=self.sandbox();p=self.run_install(root,env);self.assertEqual(p.returncode,0,p.stderr);commands=(root/'commands').read_text();self.assertIn('up --build --detach --wait',commands);self.assertNotIn('prune',commands);self.assertNotIn(' save ',commands);self.assertNotIn('down',commands)
 def test_bad_domain_port_or_unknown_flags_have_no_side_effect(self):
  for args in [('--domain','bad.example;touch pwn'),('--domain','https://example.com'),('--port','70000'),('--port','abc'),('--unknown',)]:
   root,env=self.sandbox();p=self.run_install(root,env,*args);self.assertNotEqual(p.returncode,0);self.assertFalse((root/'.env').exists());self.assertFalse((root/'commands').exists())
 def test_no_daemon_no_env_creation(self):
  root,env=self.sandbox();env['FAKE_DOWN']='1';p=self.run_install(root,env);self.assertNotEqual(p.returncode,0);self.assertFalse((root/'.env').exists())
 def test_existing_placeholder_is_not_accepted(self):
  root,env=self.sandbox();(root/'.env').write_text('WATCH_PASSWORD=CHANGE_ME_TO_AT_LEAST_32_RANDOM_CHARACTERS\nSITE_PASSWORD=CHANGE_ME_TO_A_DIFFERENT_RANDOM_SECRET\n');p=self.run_install(root,env,'--check');self.assertNotEqual(p.returncode,0)
 def test_uninstall_requires_explicit_data_purge(self):
  root,env=self.sandbox()
  for args,expected in [((),0),(('--purge-data',),64),(('--purge-data','--yes'),0)]:
   log=root/'commands';log.unlink(missing_ok=True);p=subprocess.run(['sh',str(root/'uninstall.sh'),*args],env=env,capture_output=True,text=True);self.assertEqual(p.returncode,expected)
   if expected==64:self.assertFalse(log.exists())
   elif not args:self.assertNotIn('--volumes',log.read_text())
   else:self.assertIn('--volumes',log.read_text())
@unittest.skipUnless(shutil.which('docker'),'Compose CLI not installed')
class ComposeShapeTests(unittest.TestCase):
 def test_tmpfs_options_are_one_mount_not_yaml_flow_items(self):
  import json
  env=os.environ.copy();env['WATCH_PASSWORD']='fixture-signing-secret-not-for-deployment';env['SITE_PASSWORD']='fixture-site-password-not-for-deployment'
  p=subprocess.run(['docker','compose','--profile','network','--profile','https','config','--format','json'],cwd=ROOT,env=env,capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr);data=json.loads(p.stdout)
  for service in ['watch','converter','extractor','https']:
   mounts=data['services'][service]['tmpfs'];self.assertEqual(len(mounts),1,(service,mounts));self.assertTrue(mounts[0].startswith('/tmp:'));self.assertIn('mode=',mounts[0])
 def test_core_shared_image_has_one_build_owner(self):
  import json
  env=os.environ.copy();env['WATCH_PASSWORD']='fixture-signing-secret-not-for-deployment';env['SITE_PASSWORD']='fixture-site-password-not-for-deployment'
  p=subprocess.run(['docker','compose','config','--format','json'],cwd=ROOT,env=env,capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr);s=json.loads(p.stdout)['services'];self.assertIn('build',s['watch']);self.assertNotIn('build',s['converter']);self.assertEqual(s['watch']['image'],s['converter']['image']);self.assertEqual(s['converter']['pull_policy'],'never')
