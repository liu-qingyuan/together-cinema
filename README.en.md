# Together Cinema

[简体中文](README.md) · [English](README.en.md)

[![MIT license](https://img.shields.io/github/license/liu-qingyuan/together-cinema)](LICENSE)
[![Latest release](https://img.shields.io/github/v/release/liu-qingyuan/together-cinema)](https://github.com/liu-qingyuan/together-cinema/releases/latest)
[![Main branch tests and container smoke](https://github.com/liu-qingyuan/together-cinema/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/liu-qingyuan/together-cinema/actions/workflows/ci.yml?query=branch%3Amain)
[![Deploy with Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED)](#start)
[![Feature requests and bug reports](https://img.shields.io/badge/feedback-GitHub_Issues-475569)](https://github.com/liu-qingyuan/together-cinema/issues/new/choose)
[![Release feed](https://img.shields.io/badge/RSS-releases-e78024)](https://github.com/liu-qingyuan/together-cinema/releases.atom)
[![Main branch commit feed](https://img.shields.io/badge/RSS-commits-e78024)](https://github.com/liu-qingyuan/together-cinema/commits/main.atom)

[Latest stable release](https://github.com/liu-qingyuan/together-cinema/releases/latest) · [Current architecture: control and media paths](docs/architecture/current.en.md)

**Different places. The same moment.** A self-hosted watch-party space: synchronized playback, a shared library, text chat, optional WebRTC voice, subtitles and personal scenery.

[20-second walkthrough](docs/showcase/tour.webp) · [Host your own cinema](#start) · [Join a friend's invitation (no Docker)](#join-an-invitation) · [English viewer guide (HTML source)](web/help/en.html)

[![Two independent sessions in one demo room: a light desktop and a dark mobile viewport, paused at the same moment](docs/showcase/hero.webp)](docs/showcase/README.md)

One friend paused the film at 00:13; both screens stopped on the same frame. [Desktop view](docs/showcase/desktop.webp) · [Mobile view](docs/showcase/mobile.webp). These are real browser captures with Chinese UI; the current app also offers English, selected locally in Viewing settings. A mobile viewport is not a physical-phone test.

| Enter a room | Choose a film beside the player |
| --- | --- |
| [![Room-code entry beneath a starry mountain sky](docs/showcase/entry.webp)](docs/showcase/entry.webp) | [![The shared library alongside the player](docs/showcase/library.webp)](docs/showcase/library.webp) |
| **Browse the screening journal** | **Choose your personal scenery** |
| [![Filmstrip of built-in sample titles and dates](docs/showcase/journal.webp)](docs/showcase/journal.webp) | [![Cherry-blossom scene in the personal gallery](docs/showcase/scenes.webp)](docs/showcase/scenes.webp) |

[Full screenshot tour and artwork credits (Chinese, with English scene headings) →](docs/showcase/README.md). Journal titles and dates in that empty-room capture are explicitly built-in examples, not real viewing history.

## Who is it for?

Friends who want to watch together without giving their films to a third-party platform. Media stays on your server, room playback is synchronized, and viewers can chat alongside it.

- **Playback controls:** synchronized play/pause, seek, speed, hold-to-speed-up and keyboard control, with timed comments and multiple rooms.
- **Your shared library:** upload MP4 / M4V / WebM; MKV / AVI appear after background processing. Compatible video is remuxed where possible, otherwise converted. Films can be deleted.
- **Subtitles:** text and supported PGS image subtitles; stage fullscreen includes subtitles and timed comments. This is not a universal MKV/subtitle decoder.
- **Chat and voice:** room text chat; HTTPS and an external TURN configuration are required to enable WebRTC voice with volume controls and a waveform.
- **Optional online sources:** direct playback or server relay; enable `network` for YouTube and generic dynamic-page discovery. No login, CAPTCHA or DRM bypass, and no all-sites compatibility promise.
- **Gallery and screening room:** the ordinary entrance opens the gallery; a valid invitation opens its room directly. Private library listings require a session. Gallery preset buttons only preview this page; the room has eight personal wallpapers with artist credits and source links, not a shared-cover management panel. Assets ship with the deployment, with responsive sizes and static fallbacks; room entry stops gallery decoration. No third-party image CDN or analytics is requested while browsing.

## Start

**Path one: host your own cinema.** Just here to watch? Skip installation and [join an invitation](#join-an-invitation).

Install **Docker Engine / Docker Desktop + Compose v2** with `up --wait` support. First builds download dependencies; their duration depends on your connection. Check `docker context show` to confirm the intended engine. The installer does not run sudo, install Docker or change your firewall.

This page's bilingual UI and guide steps describe **current `main` source**, not a promise that older release archives include them. Install Git and clone the main branch:

```sh
git clone https://github.com/liu-qingyuan/together-cinema.git
cd together-cinema
./install.sh
```

Without Git, download the [current main source archive](https://github.com/liu-qingyuan/together-cinema/archive/refs/heads/main.zip), extract it, enter its directory and run only `./install.sh`; no additional clone is needed. For a formal release, follow that version's README and release notes instead. Open **http://127.0.0.1:8080**. Browse the gallery and enter a **2–8 character alphanumeric room code**: a new code creates a room; the same code joins the same room. This default listener is local-only, not a public deployment. A remembered room does not automatically join from the ordinary entrance, and visitors without a session cannot see the private library.

### Let remote friends join

Point your domain's DNS at the server and open TCP 80/443, then run:

```sh
./install.sh --domain cinema.example.com
```

Open `https://cinema.example.com` (replace the example domain). The browser's site-login prompt requires username **`cinema`** and the generated **`SITE_PASSWORD`** from your private `.env`. `WATCH_PASSWORD` is an internal signing/extractor secret, not the site-login password. Compose being healthy does not guarantee DNS or certificate issuance has finished; check `docker compose logs --tail=100 https` if needed.

> **A room code is not a password.** This is a trusted-friends shared library: anyone admitted to any room can watch, upload and delete the entire site's library. It is not a multi-tenant public video service. Only expose protected HTTPS; never forward unprotected port 8080 to the public internet. Invite trusted people, do not share `.env`, and keep private invitations out of public posts. See the [security boundary](SECURITY.md).

### Optional dynamic-page and YouTube discovery

```sh
./install.sh --network
# Or enable it on the first public installation:
./install.sh --network --domain cinema.example.com
```

Only enabling this option downloads/builds the larger browser image. The extractor allows one job at a time, a 35-second timeout and a 512 MiB container limit; temporary browsers exit on completion or failure. Shared HLS fragment caching is bounded to 16 MiB, not a whole-film disk download. It reduces repeated origin requests, **not server egress per viewer**. Local files, public HTTPS media URLs and discoverable static-page media do not need this optional service for a first watch.

## Join an invitation

**Path two: invited viewers need neither Docker nor a browser extension.**

1. Ask the operator for the complete invitation, for example `https://cinema.example.com/?room=AB` (an example domain, not a public demo). Open your friend's actual link. If a site-login prompt appears, use username `cinema` and the site access password they provide, not a third-party website account.
2. A valid invitation opens that room directly. Without an invitation, open your friend's site and enter the same 2–8 letter/number room code. Check the room number and online count on both screens.
3. The UI initially follows your browser's Chinese/English preferences, falling back to Chinese if neither matches. Choose **English** in “Viewing settings → Interface language” (Chinese labels: “观影设置 → 界面语言”) if needed. This is local to your browser; it neither changes your friend's language nor translates film titles, chat or subtitles.

## Choose a film and check synchronization

After joining, hosts and invited viewers use the same workflow:

1. The first viewer is usually the host; check “You are the host”. If needed, use “Members → Take playback control”. The host selects, plays, pauses, seeks and changes synchronized speed; other viewers follow.
2. Click “Scroll to the screening”, then the sidebar's “Library” tab. The host pauses any current film and clicks an existing film. If empty, use “Add video” to upload a file you have permission to watch together: MP4 / M4V / WebM / MKV / AVI. MKV / AVI enter the library after background processing; check status and free space.
3. Confirm the title on both screens, then have the host press play. If sound is blocked, each viewer should click the player's play button to allow audio. Have the host pause and resume to check that both follow. If not, check the room code and connection status; use “Reconnect” after disconnection. Volume, subtitles and timed-comment visibility are local choices.
4. For online media, paste an authorized public video webpage or HTTPS media URL into “Library → Online video · Direct / Relay”. Choose a mode and click “Find videos”, then **explicitly click the intended candidate** to switch. For a two-video page, choose the second by its order and picture; the first is not selected automatically. To change modes, find videos again and reselect the same candidate.

**Direct** sends media from the origin to each viewer (the HLS entry playlist still passes through this cinema); everyone needs origin access and browser codec support. **Relay** lets the server lawfully fetch and send media separately to each viewer. Relay is the default dropdown choice; prefer direct first when everyone can reach the origin. The default relay allowance is shared site-wide: **5 GiB per 24 hours**, up to **6 concurrent media requests**, not a guarantee for 6 viewers. Shared caching does not remove per-viewer egress. Sources are temporary, not permanent library imports. No login, paywall, CAPTCHA or DRM bypass, and no guarantee for every website or codec.

The complete [English viewer guide](web/help/en.html) ships with the site. GitHub displays that link as **HTML source**; to read the rendered guide, open `/help/en.html` on your friend's actual domain, e.g. `https://cinema.example.com/help/en.html` after replacing the example domain. No room session is required, but the site's access password still applies. “Viewer guide” in the gallery's entry card or the room's Library opens it in a new tab without interrupting playback. It explains direct/relay examples, empty results, expired sources and quota errors; no webpage translation is needed.

## After installation

```sh
./install.sh --check                 # validate configuration only
./install.sh --port 8088             # change the local HTTP port
# Upgrade: inspect changes, then update source and rebuild
# git pull --ff-only && ./install.sh
./uninstall.sh                      # stop containers, keep media and .env
./uninstall.sh --purge-data --yes    # PERMANENTLY delete project volumes and certificates!
```

No automatic backups, image exports, global Docker prune or deletion of other projects. Reinstallation preserves `.env` secrets and media volumes. Git clones can upgrade with `git pull --ff-only` as above. Archive users should back up first, update the source in the original directory, keep the private `.env` and the same Compose project name/volumes, then rerun `./install.sh`; do not create a separate empty library. Rebuilds interrupt active connections; wait until everyone has finished watching. Room state is not guaranteed to survive restarts.

For voice, public microphone access requires HTTPS. Set `WATCH_TURN_URLS` and `WATCH_TURN_SECRET` in private `.env` to match your external TURN service, then rerun `./install.sh`. Without TURN the UI reports voice disabled; text chat works without it. The app does not install TURN or promise connectivity through every network. Advanced [deployment and TURN details (Chinese)](docs/deployment.md) are optional, not required for a first watch with text chat.

Production sites using versioned images and an Nginx static front page should follow the [production release procedure](docs/releasing.md#versioned-production-releases-linux-compose--nginx): validate an isolated library and actual public playback before reclaiming the current build's cache and the unreferenced previous image. The ordinary installer does not clean the host.

## Resources

| Mode | Suggested starting point, not a benchmark promise | Notes |
| --- | --- | --- |
| Local video / chat | 1 vCPU, 1 GiB RAM; 2 GiB recommended | FFmpeg and large uploads need extra resources |
| With dynamic discovery | 2 GiB RAM or more recommended | Memory checked before discovery; 512 MiB extractor limit |
| Disk | Allow room for films and conversion beyond OS/images | Default 2 GiB free-space reserve is a write guard, not preallocated storage |

Video bitrate and viewer count determine bandwidth. A 33 GB source does not become low-traffic automatically. Compatible H.264 may only need remuxing/audio conversion, which does not shrink compatible video losslessly; other supported sources needing re-encoding are converted at up to 720p. H.265/HEVC auto-processing can fail the current output check and never enter the library; for a first watch, convert it locally to SDR H.264/AAC MP4 rather than assuming every codec will upload successfully. Keep the upload page open; parallel upload is not resume-after-refresh. See the [advanced storage/conversion reference (Chinese)](docs/deployment.md).

## Project status

This is an early open-source project with published source releases, not a SaaS certified for every website, phone or public network. [GitHub Releases](https://github.com/liu-qingyuan/together-cinema/releases) is the source of truth for versions and changes; the text link and badge above point to the latest stable release even if badge images do not load. An Android Quark half-covered-video report is unresolved; [compatibility notes](docs/compatibility.md) distinguish device emulation from real-device certification.

No prebuilt application images on Docker Hub/GHCR or public demo are provided. The installer uses Compose to build application images locally from the downloaded source; a source release is not a prebuilt application image.

## Development and contributing

Start with the [current code map (Chinese)](docs/code-map.md) for playback, library, conversion, online sources and screening history, with their tests. Backend code is in `cinema/`, web assets in `web/`, and tests/fixtures together in `tests/`, without test-layer subdirectories. From the repository root, with Python 3.13 and system `ffmpeg` / `ffprobe`:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -v
```

Optional real-browser checks require Playwright and local Chrome. Use only a dedicated local Compose test deployment, never a personal library:

```sh
pip install playwright
python scripts/gallery_smoke.py http://127.0.0.1:8080
# For Playwright Chromium: playwright install chromium, then add --channel chromium
# Optional: --artifacts /tmp/gallery-evidence (screenshots, no cookies or sessions)
python scripts/gallery_visual_smoke.py http://127.0.0.1:8080 --artifacts /tmp/gallery-visual
```

These two scripts explicitly use Chinese UI. The first uses two independent browsers, uploads/deletes only its generated clip and checks gallery access and real synchronized play/pause/seek. The second checks gallery presets, responsive loading, focus and preference fallbacks. For bilingual UI and help/online-media checks, run `python -m scripts.locale_smoke` and `python -m scripts.guide_smoke`; each starts a temporary loopback app with generated media, never an existing deployment. Repeated entry may trigger the existing login rate limit; wait for its window or restart only the dedicated test instance. These are viewport simulations, not phone certification; see the [historical gallery acceptance gaps (Chinese)](docs/gallery-visual-acceptance.md).

[Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Historical deployment design](docs/architecture.md) · [Release checklist](docs/releasing.md) · [Third-party licenses](THIRD_PARTY_NOTICES.md)

### Keeping translations in sync

Only Simplified Chinese and English are maintained. README language, viewer-guide language and the room's local UI preference are independent. Changes to first-watch steps, commands, configuration defaults, permissions or traffic limits must update both READMEs, the corresponding `web/help/zh-CN.html` / `web/help/en.html` content and relevant UI messages in the same commit. Keep information equivalent, not necessarily word-for-word. Propose a new translation in [GitHub Issues](https://github.com/liu-qingyuan/together-cinema/issues/new/choose) with its language and an ongoing maintainer. Keep additional translations together in `docs/readme/`, not placeholder files scattered across the root; supply a complete first-watch path and native-language screenshot descriptions, then verify installation/invitation/selection/sync before adding the top language links. Do not advertise empty or unmaintained translations. Label untranslated advanced references with their target language; they must not block the first watch. See this path's [validation evidence and limits](docs/readme-acceptance.md).

Small, complete fixes, reproducible compatibility reports and documentation improvements are welcome. Only share media you are authorized to access and distribute; no films, memberships or third-party accounts are bundled.

## License

Original code and vector artwork are [MIT](LICENSE). The two gallery photographs/illustrations retain **CC BY 4.0** attribution, not MIT. Third-party images, libraries and runtimes keep their [own licenses](THIRD_PARTY_NOTICES.md).
