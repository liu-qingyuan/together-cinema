# Historical release validation — Alpha candidate

Validated on **2026-11-23**, before the first Alpha source publication. At that time, the tested source was ready for a limited **Alpha** source release, not a claim of universal/stable compatibility, and no GitHub remote or public release had been created. Results and test counts below are preserved as observed then, not current totals or publication status. See the [current code map](code-map.md), [test-layout baseline](evidence/test-layout.json) and [published source releases](https://github.com/liu-qingyuan/together-cinema/releases).

## Actual environment

- macOS ARM64 host, Docker Desktop29.6.1 / Linux ARM64 containers.
- Host Python3.14; application container Python3.13 with system FFmpeg.
- Existing personal production deployment was not changed or restarted.

## Executed checks

| Check | Observed result |
|---|---|
| Host `python -m unittest discover -q` | **90 passed**, no skips |
| Full suite in real app container | **90 run:88 passed,2 skipped**; the2 Compose-CLI checks are executed on host, because the app container intentionally has no Docker CLI |
| Actual `./install.sh` core build/start | Exit0, app health200, converter running; listener127.0.0.1 |
| Actual `./install.sh --network` | Exit0, both core and ARM64 extractor built and started |
| HTTP smoke | Room login200, generated MP4 upload201, exact first32 media bytes via206 Range, scenes200 and real WebSocket room |
| Actual AVI background conversion | MPEG4/MP3 fixture accepted202, worker completed, output joined library |
| Two independent browser contexts | Both decoded640×360 frames and real audio; play/pause/seek, short keyboard seek/volume, hold2×/release1×, chat and danmaku synchronized; stage fullscreen toggled correctly;6 local SVG themes loaded; no JS errors |
| Public YouTube sample through installed stack | Blender Foundation Big Buck Bunny sample resolved and relayed; both contexts decoded640×360 + audio; seek/rate/danmaku synchronized; media requests stayed on the app origin |
| Shared HLS cache | Sample had shared hits/coalesced requests; payload + reservations remained below16MiB; after ending, streams/cache/reservations/inflight all0, no video disk cache. Unselected source metadata remains bounded and expires within120s |
| Generic dynamic browser fixture in real extractor container | Sandboxed Chromium executed iframe + WASM + requests, discovered HLS, denied private destination and private redirect with0 private TCP connections |
| Extractor health | Healthy/idle after private-input400, temporary directory empty |
| Actual gateway HTTPS/access protection | Real TLS validated using locally generated CA; unauthorized401, wrong password401, authorized health/login/library200; Secure cookie and authenticated WSS room worked |
| Default uninstall → reinstall | Exit0; both media SHA256 values, named volumes and private.env SHA256 unchanged; test marker survived and was then removed |
| Source hygiene and patch check | Limited-pattern tracked-file check and `git diff --check` passed; generated.env and browser traces excluded |

### Reproduction entry points

```sh
python -m unittest discover -v
./install.sh
python scripts/smoke.py http://127.0.0.1:8080
./install.sh --network
./uninstall.sh   # default keeps named data volumes
./install.sh
```

Container suite needs its temporary test data on a filesystem with room for the existing2GiB reserve; the production32MiB `/tmp` is deliberately not suitable for upload fixtures. This is a test-location constraint, not a reason to remove disk-reserve protection.

## Failures caught before release

- YAML flow-list commas had split tmpfs options into separate mounts; quotes and a Compose-shape regression fixed this.
- Converter/watch redundantly built one shared image; watch is now the sole build owner, converter never tries to pull a nonexistent registry image.
- Debian HTTP downloads failed in this network; Dockerfiles now use the official HTTPS source, and both actual rebuilds passed.
- A Linux orphan test relied on `ps`, absent from the slim runtime; it now observes `/proc` on Linux while preserving the same liveness assertion.
- Compose-only tests now share one Docker-CLI availability guard; Docker-free app containers skip those2 checks instead of failing.
- Initial browser harness played before sync suppression settled; waiting for the existing cooldown made the unchanged runtime test repeatable. This is not claimed as a production bug fix.

## Still not certified

- Fresh Linux AMD64/Windows installations; the provided AMD64 GitHub Actions workflow had not run on a remote repository at the time of this validation.
- Public DNS/ACME certificate issuance. The local TLS/auth/WSS path was actually tested; that does not establish a real domain's DNS/firewall/certificate readiness.
- Cross-network real-device voice with external TURN, every mobile browser, and every website/codec.
- The reported Android Quark half-covered video remains unresolved. Mobile-sized desktop contexts are not physical-device certification.
- Indefinite leak freedom or production load capacity. Bounded lifecycle tests and limits were checked, not an unlimited endurance proof.

Independent Standards and Spec broad reviews accepted the direction with no Critical/High. Final focused closure covers the slim-container test portability, trace exclusion, and this evidence update; do not substitute static review for the executed checks above.
