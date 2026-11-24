#!/usr/bin/env python3
"""Release one versioned Compose watch service behind a static-root Nginx site."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import tempfile
import time
from urllib.request import Request, urlopen


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def run(*args, data=None, timeout=90, env=None):
    return subprocess.check_output(args, input=data, timeout=timeout, env=env)


def docker(*args, **kwargs):
    return run('docker', *args, **kwargs)


def replace_once(data, old, new):
    require(data.count(old) == 1, 'Unexpected config layout; no change made')
    return data.replace(old, new)


def atomic(path, data):
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            os.fchmod(f.fileno(), stat.S_IMODE(path.stat().st_mode))
            f.write(data)
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def retry(action):
    for attempt in range(12):
        try:
            return action()
        except Exception:
            if attempt == 11:
                raise
            time.sleep(1)


def static_root(source):
    # Old staged releases remain valid rollback/check-current targets.
    return source / 'web' if (source / 'web').is_dir() else source


def gate(origin, source, image):
    source = static_root(source)
    def fetch(path, maximum, span=False):
        req = Request(origin + path, headers={'Range': 'bytes=0-31'} if span else {})
        with urlopen(req, timeout=8) as r:
            require(r.geturl() == req.full_url and r.status == (206 if span else 200),
                    'Unexpected origin, redirect or HTTP status: ' + path)
            data = r.read(maximum + 1)
            require(len(data) <= maximum, 'Oversized response: ' + path)
            return data

    require(json.loads(fetch('/healthz', 1024)).get('ok') is True, 'Health gate failed')
    for url, file in [('/', 'index.html'), ('/assets/site-nav.css', 'assets/site-nav.css')]:
        expected = (source / file).read_bytes()
        require(fetch(url, len(expected)) == expected, 'Stale public asset: ' + url)
    url = '/room-art/anime-opening-v1.mp4'
    clip = (source / ('assets' + url)).read_bytes()
    require(0 < len(clip) <= 2**21 and fetch(url, 32, True) == clip[:32], 'Range gate failed')
    media = fetch(url, len(clip))
    require(media == clip, 'Public MP4 differs from this release')
    # Decoding the served bytes is stronger than a health check or just a 206.
    raw = docker('run', '--rm', '--network', 'none', '--read-only', '--cap-drop=ALL',
                 '--memory=128m', '--cpus=.5', '-i', image, 'ffmpeg', '-v', 'error',
                 '-xerror', '-threads', '1', '-i', 'pipe:0', '-frames:v', '2',
                 '-vf', 'scale=16:16', '-threads', '1', '-pix_fmt', 'gray',
                 '-f', 'rawvideo', 'pipe:1', data=media)
    require(len(raw) == 2 * 16 * 16, 'Playback gate: did not decode two frames')


def canary(image):
    cid = docker('run', '-d', '--network', 'none', '--read-only', '--cap-drop=ALL',
                 '--memory=192m', '--cpus=1', '--pids-limit=64',
                 '--tmpfs', '/tmp:size=24m,mode=1777', '--tmpfs', '/data:size=32m,uid=10001,gid=10001',
                 '-e', 'WATCH_PASSWORD=' + secrets.token_hex(24), '-e', 'COOKIE_SECURE=false',
                 '-e', 'RESERVE_BYTES=1048576', image).decode().strip()
    try:
        retry(lambda: docker('exec', cid, 'python', '-c',
              "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/healthz')"))
        smoke = (Path(__file__).resolve().parents[1] / 'scripts/smoke.py').read_bytes()
        print(docker('exec', '-i', cid, 'python', '-', 'http://127.0.0.1:8080', data=smoke).decode().strip())
    finally:
        # Only our disposable, network-isolated container and its tmpfs, never a live volume.
        docker('rm', '-f', cid)


def container_images():
    cids = docker('ps', '-aq', '--no-trunc').decode().split()
    if not cids:
        return set()
    return set(docker('inspect', '-f', '{{.Image}}', *cids).decode().split())


def retire(tag, original_id, configured):
    if tag in configured or original_id in container_images():
        print('KEEP: another service/container references the previous image')
        return
    actual = docker('image', 'inspect', '-f', '{{.Id}}', tag).decode().strip()
    require(actual == original_id, 'Previous tag moved; skipping removal')
    docker('image', 'rm', tag)  # never force, never prune the daemon


def transaction(canary_check, activate, live_check, rollback, cleanup):
    canary_check()
    try:
        activate()
        live_check()
    except BaseException:
        rollback()
        raise
    # A cleanup error must not roll a verified release back to an already retired image.
    cleanup()


def release(args):
    root = args.root.resolve(strict=True)
    config = root / 'compose.yml'
    site = args.nginx_site.resolve(strict=True)
    def compose(*a):
        return docker('compose', '-f', str(config), *a)
    def services():
        return json.loads(compose('config', '--format', 'json'))['services']
    def running():
        cid = compose('ps', '-q', 'watch').decode().strip()
        return docker('inspect', '-f', '{{.Config.Image}} {{.Image}}', cid).decode().split()
    old, old_id = running()
    match = re.fullmatch(r'([a-z0-9][a-z0-9._/-]*):release-([0-9a-f]{12})', old)
    require(match and services()['watch']['image'] == old, 'Expected current versioned watch image')
    prev = root / 'releases' / match[2]
    require(Path(services()['watch']['build']['context']) == prev, 'Unexpected live build root')
    require(re.fullmatch(r'https://[a-zA-Z0-9.-]+(?::[0-9]+)?', args.public_url), 'HTTPS origin required')
    if args.check_current:
        canary(old_id)
        gate(args.public_url, prev, old_id)
        print('PASS: current public release decoded; no switch or retirement')
        return
    rev = args.revision
    require(rev and re.fullmatch('[0-9a-f]{40}', rev), 'Use a full Git commit SHA')
    dest = root / 'releases' / rev[:12]
    require(dest != prev and dest.resolve(strict=True) == dest, 'Need a distinct staged release directory')
    tag = match[1] + ':release-' + rev[:12]
    require(not docker('image', 'ls', '-q', tag).strip(), 'Candidate tag already exists; inspect before retry')
    initial, nginx = config.read_bytes(), site.read_bytes()
    nextcfg = replace_once(initial, ('    image: '+old+'\n').encode(), ('    image: '+tag+'\n').encode())
    nextcfg = replace_once(nextcfg, ('    build: '+str(prev)+'\n').encode(), ('    build: '+str(dest)+'\n').encode())
    nextng = nginx
    for directive, suffix in [('root',''), ('alias','/assets/scenes/')]:
        nxt = lambda p: (directive+' '+str(static_root(p))+suffix+';').encode()
        nextng = replace_once(nextng, nxt(prev), nxt(dest))
    port = int(compose('port', 'watch', '8080').decode().strip().removeprefix('127.0.0.1:'))
    def idle():
        if args.allow_connected:
            return
        require(not run('ss','-ntH','state','established',f'( sport = :{port} )').strip(),
                'Live connections present; refusing switch')
    idle()
    # Unique private scratch. Config copies stay on this host; no paths supplied for deletion.
    scratch = Path(tempfile.mkdtemp(prefix='.watch-publish-', dir=root))
    print('Release scratch:', scratch, flush=True)
    for name, content in [('previous-compose',initial), ('previous-site',nginx)]:
        (scratch/name).write_bytes(content)
    builder = None
    buildargs = ['--label','org.opencontainers.image.revision='+rev,'-t',tag,str(dest)]
    if subprocess.run(['docker','buildx','version'],capture_output=True).returncode == 0:
        name = 'tc-release-' + secrets.token_hex(8)
        docker('buildx','create','--driver','docker-container','--name',name)
        builder = name
        (scratch/'builder').write_text(name)
        docker('buildx','build','--builder',name,'--load',*buildargs,timeout=1800)
    else:
        # The production daemon has the classic builder: no shared BuildKit cache is created.
        docker('build','--rm','--force-rm',*buildargs,env={**os.environ,'DOCKER_BUILDKIT':'0'},timeout=1800)
    image = docker('image','inspect','-f','{{.Id}}',tag).decode().strip()
    def up():
        compose('up','-d','--no-deps','--no-build','--pull','never','watch')
    def reload():
        run('nginx','-t'); run('systemctl','reload','nginx')
    switched = False
    def activate():
        nonlocal switched
        require(config.read_bytes()==initial and site.read_bytes()==nginx and running()==[old,old_id],
                'Deployment changed during build')
        idle()
        atomic(config,nextcfg)
        switched = True
        up()
        atomic(site,nextng)
        reload()
    def verify():
        require(running()==[tag,image], 'Wrong live container image')
        retry(lambda: gate(args.public_url,dest,image))
    def rollback():
        if switched:
            atomic(config,initial); atomic(site,nginx); up(); reload()
            retry(lambda: gate(args.public_url,prev,old_id))
            print('Rolled back and verified prior release.')
    def cleanup():
        require(running()==[tag,image], 'Live image changed before cleanup')
        if builder:
            docker('buildx','rm',builder)
        retire(old,old_id,{v.get('image') for v in services().values()})
        # Deliberately do not walk releases/, data/, Docker volumes, or shared builders.
        for name in ('builder','previous-compose','previous-site'):
            (scratch/name).unlink(missing_ok=True)
        scratch.rmdir()
        print('PASS: public playback verified, scoped cleanup complete')
    transaction(lambda:canary(image),activate,verify,rollback,cleanup)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',required=True,type=Path)
    p.add_argument('--nginx-site',required=True,type=Path)
    p.add_argument('--public-url',required=True)
    p.add_argument('--allow-connected',action='store_true',help='Allow a brief reconnect when switching the live watch service')
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--revision');g.add_argument('--check-current',action='store_true')
    args=p.parse_args()
    with (args.root/'.watch-publish.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        release(args)


if __name__=='__main__':
    main()
