# Bilingual README first-watch validation

Ticket #17; implementation baseline `bf5b135`. The README paths describe current `main`, not a claim that older formal-release archives already include the bilingual UI and viewer guides. No application protocol, permission or deployment contract changes were made.

## Reader paths

Both homepages put “简体中文 · English” before badges and screenshots. Each has native-language screenshot descriptions, separate hosting and invited-viewer paths, room entry, host selection, play/pause confirmation, direct/relay advice and links to its existing architecture and guide. Advanced references without a translation identify their language. The guide links to repository HTML source are explicitly distinguished from rendered `/help/zh-CN.html` and `/help/en.html` on the operator's actual site; the example domain is not a demo.

Installation commands, `.env` secret roles, HTTPS protection, site-wide shared-library permissions, optional discovery, TURN, storage and relay limits were compared against `install.sh`, `compose.yml`, `docs/deployment.md` and both shipped guides. Review caught an older deployment-reference claim that HEVC could be remuxed successfully: `cinema/conversion.py` attempts HEVC copying but then rejects non-H.264 output. Both READMEs instead warn that HEVC processing can fail and recommend SDR H.264/AAC MP4 for a first watch; the converter itself is unchanged and remains follow-up work. No Docker installation is required for an invited browser. Both READMEs describe same-commit translation updates and maintained additions under `docs/readme/`, without advertising unmaintained languages or introducing a translation platform.

## Executed checks

Machine-readable results: [`evidence/readme.json`](evidence/readme.json).

- `python -m unittest discover -v`: **121 passed, no skips**. `node --test tests/locale.test.cjs`: **2 passed**.
- Independent fresh source directory and new volume, Docker Desktop on macOS ARM64, application Python 3.13: `./install.sh --port 18917` passed. Only the loopback test port changed from the README default to avoid existing sites. `./install.sh --check` passed and preserved `.env` byte-for-byte. No production deployment was restarted.
- `python scripts/smoke.py http://127.0.0.1:18917`: health/login/upload/Range/WebSocket and actual FFmpeg decoding passed; only generated media used.
- `python scripts/gallery_smoke.py http://127.0.0.1:18917`: Chinese gallery, unauthorized library access, valid/invalid invitation, manual entry, two independent browser processes and real play/pause/seek passed. Playback drift was 0.057 s; exit and re-entry passed.
- A companion English walkthrough on that same clean Compose instance followed the README's visible UI: open the public English guide before joining, create a room, use “Copy invite”, open the actual clipboard invitation in an independent English browser context, “Add video” → “Choose a video” → “Upload to library”, choose the generated film and confirm both decoded it. Play and pause/resume drift were 0.018 s / 0.082 s; no browser errors. The invited side only opened a browser. This was a one-off reader walkthrough with existing Playwright tooling, not a new committed test platform.
- `python scripts/runtime_layout_smoke.py http://127.0.0.1:18917`: real MKV background conversion, browser playback and original active subtitle passed.
- `python scripts/gallery_visual_smoke.py http://127.0.0.1:18917 --artifacts <temporary-directory>`: desktop/mobile-sized presets, loading, focus, reduced preferences and base CSS entry passed, with no horizontal overflow at 320 px. The existing Chinese-locator gallery/layout scripts now explicitly request `zh-CN`; before this test-only fix, the host Chrome defaulted to English and the gallery script failed at the Chinese heading. Application language selection was correct and unchanged.
- `python -m scripts.guide_smoke`: two independent English/Chinese contexts, anonymous help, explicit second candidate, actual direct-origin and server-relay media paths, blocked guest-origin access with successful relay, pause/resume and actionable failure paths passed. Opening help caused no reload, reconnect or playback command.
- `python -m scripts.locale_smoke`: English local switching during shared playback, Chinese guest isolation, original subtitle/chat/title/timed comment preservation, preferences and storage-disabled behavior passed, with no media reload/reconnect/language-triggered control.

The README Markdown is checked with GitHub's Markdown API plus local path/fragment checks. Published GitHub homepage rendering and navigation are checked after push and recorded in the closing issue comment, rather than treating local source preview as publication evidence.

## Reused evidence and limits

The clean-install and same-directory upgrade tests for the shipped guides, retained media/subtitle and `.env` are already recorded in [`guide-acceptance.md`](guide-acceptance.md) and [`evidence/guide-distribution.json`](evidence/guide-distribution.json). This ticket reran a clean installation, not a new upgrade matrix. It does not claim that downloading an older release supplies newer `main` features.

Only the test's Compose project, its created volumes and image tag were removed afterward; no global prune or personal-library cleanup. Source/test logs and transient screenshots stayed outside the repository; the committed JSON contains no credentials, storage state or private invitations.

No public DNS/ACME certificate issuance, cross-network TURN, external provider, production deployment or physical mobile-device validation is claimed. The network test maps only transport for `media.example` to owned local clips while keeping real discovery, selection and relay behavior. Mid-stream quota exhaustion remains unverified, as in the existing guide evidence. Badge images are optional; the stable-release and architecture text links remain available.
