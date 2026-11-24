import unittest
from unittest.mock import patch
from deploy import release_live as live


class ReleaseOrder(unittest.TestCase):
    def sequence(self, failure):
        events = []
        def step(name):
            def run():
                events.append(name)
                if name == failure:
                    raise RuntimeError(name)
            return run
        steps = map(step, ['canary', 'activate', 'public-decode', 'rollback', 'cleanup'])
        if failure:
            with self.assertRaisesRegex(RuntimeError, failure):
                live.transaction(*steps)
        else:
            live.transaction(*steps)
        return events

    def test_cleans_only_after_public_playback(self):
        self.assertEqual(self.sequence(None), ['canary','activate','public-decode','cleanup'])

    def test_canary_failure_never_switches(self):
        self.assertEqual(self.sequence('canary'), ['canary'])

    def test_bad_live_playback_rolls_back_without_cleanup(self):
        self.assertEqual(self.sequence('public-decode'), ['canary','activate','public-decode','rollback'])

    def test_cleanup_failure_does_not_undo_verified_release(self):
        self.assertEqual(self.sequence('cleanup'), ['canary','activate','public-decode','cleanup'])

    def test_activation_error_rolls_back(self):
        self.assertEqual(self.sequence('activate'), ['canary','activate','rollback'])


class Retirement(unittest.TestCase):
    def test_preserves_old_image_referenced_by_other_container_or_compose(self):
        with patch.object(live,'docker') as cmd, patch.object(live,'container_images',return_value={'old-id'}):
            live.retire('old-tag','old-id',set())
            live.retire('other-tag','other-id',{'other-tag'})
            cmd.assert_not_called()

    def test_only_exact_old_tag_removed_without_force(self):
        with patch.object(live,'container_images',return_value={'new-id'}), patch.object(live,'docker',return_value=b'old-id\n') as cmd:
            live.retire('old-tag','old-id',{'new-tag'})
            self.assertEqual(cmd.call_args.args,('image','rm','old-tag'))

    def test_refuses_retag_and_unexpected_config(self):
        with patch.object(live,'container_images',return_value=set()), patch.object(live,'docker',return_value=b'moved') as cmd:
            with self.assertRaises(RuntimeError):
                live.retire('old-tag','old-id',set())
            self.assertEqual(cmd.call_count,1)
        with self.assertRaises(RuntimeError):
            live.replace_once(b'x x', b'x', b'y')


class ReleaseFixture(unittest.TestCase):
    """Exercise real configuration replacements on disk, with simulated Docker/Nginx."""
    def exercise(self, bad_public, previous_web=False):
        import json
        from contextlib import ExitStack
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from types import SimpleNamespace

        with TemporaryDirectory() as temp, ExitStack() as patches:
            root=Path(temp).resolve(); old,new='a'*12,'b'*12
            prev,dest=[root/'releases'/v for v in (old,new)]
            prev.mkdir(parents=True); (dest/'web').mkdir(parents=True)
            previous_static=prev/'web' if previous_web else prev
            previous_static.mkdir(exist_ok=True)
            config=root/'compose.yml'; site=root/'nginx'
            tag=lambda rev:'fixture:release-'+rev
            initial=f'    build: {prev}\n    image: {tag(old)}\n'
            original_site=f'root {previous_static};\nalias {previous_static}/assets/scenes/;'
            config.write_text(initial); site.write_text(original_site)
            media=root/'data/media'; media.mkdir(parents=True)
            sub=root/'data/subtitles'; sub.mkdir()
            for path in (media/'film',sub/'text'): path.write_bytes(b'preserve')
            actual=[old]; calls=[]
            def cli(*args,**kwargs):
                calls.append(args)
                selected=old if config.read_text()==initial else new
                if args[:1]==('compose',):
                    cmd=args[3]
                    if cmd=='config':
                        return json.dumps({'services':{'watch':{'image':tag(selected),'build':{'context':str(prev if selected==old else dest)}}}}).encode()
                    if cmd=='port':return b'127.0.0.1:8080'
                    if cmd=='ps':return b'watch'
                    if cmd=='up':actual[0]=selected;return b''
                if args[0]=='inspect':
                    return f'{tag(actual[0])} id-{actual[0]}'.encode()
                if args[:2]==('image','inspect'):return ('id-'+(old if args[-1]==tag(old) else new)).encode()
                if args[0]=='ps':return b''
                if args[0]=='buildx' or args[:2] in [('image','ls'),('image','rm')]:return b''
                self.fail(args)
            def verify(url,source,image):
                static=dest/'web' if source==dest else previous_static
                self.assertEqual(site.read_text(),f'root {static};\nalias {static}/assets/scenes/;')
                self.assertEqual(image,'id-'+actual[0])
                if bad_public and source==dest:raise RuntimeError('stale public bytes')
            for name,fn in [('docker',cli),('run',lambda *a:b''),('canary',lambda image:None),
                            ('gate',verify),('retry',lambda f:f())]:
                patches.enter_context(patch.object(live,name,fn))
            patches.enter_context(patch.object(live.subprocess,'run',return_value=SimpleNamespace(returncode=0)))
            args=SimpleNamespace(root=root,nginx_site=site,public_url='https://cinema.example',
                                 revision='b'*40,check_current=False)
            if bad_public:
                with self.assertRaisesRegex(RuntimeError,'stale public'):live.release(args)
                self.assertEqual(config.read_text(),initial);self.assertEqual(site.read_text(),original_site)
                self.assertEqual(actual,[old]);self.assertNotIn(('image','rm',tag(old)),calls)
                self.assertFalse(any(c[:2]==('buildx','rm') for c in calls))
            else:
                live.release(args);self.assertEqual(actual,[new])
                owned=next(c[-1] for c in calls if c[:2]==('buildx','create'))
                self.assertIn(('buildx','rm',owned),calls);self.assertIn(('image','rm',tag(old)),calls)
                self.assertFalse(list(root.glob('.watch-publish-*')))
            for path in (media/'film',sub/'text'):self.assertEqual(path.read_bytes(),b'preserve')

    def test_success_removes_owned_builder_and_scratch_only(self):
        for previous_web in (False,True):
            with self.subTest(previous_web=previous_web):self.exercise(False,previous_web)

    def test_bad_live_bytes_restore_original_config_and_keep_rollback(self):
        for previous_web in (False,True):
            with self.subTest(previous_web=previous_web):self.exercise(True,previous_web)
