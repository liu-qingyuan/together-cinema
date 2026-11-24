# Contributing

Small, testable changes are welcome. Start with an issue describing actual behavior, expected behavior and a minimal input. Do not upload films, personal server credentials, room messages or signed URLs.

- Start with the [current code map](docs/code-map.md) to find each responsibility and its tests. Backend code lives in the `cinema/` Python package, web assets in `web/`, and tests stay in `tests/`; installation and Compose entry points stay at the repository root.
- Python 3.13, system `ffmpeg`/`ffprobe`, `pip install -r requirements.txt`.
- From the repository root, run `python -m unittest discover -v`. Tests and their fixtures live in `tests/`; do not split test layers or add import-path workarounds. Docker with the Compose v2 CLI is needed to run the two Compose-shape checks without skips (no daemon needed); installer contract tests use a fake Docker CLI, while separate smoke tests use a real engine.
- Preserve synchronization, bounded resources and cleanup behavior. Test observable HTTP/WebSocket/process interfaces.
- Do not add a frontend build chain, provider-specific parser or new abstraction without a demonstrated need.
- Keep application and default installer safe for a trusted private deployment; room code is not an authorization boundary.
- New vendored assets must retain their licenses and provenance. No scraped commercial artwork or movie stills for README/demo.
- No fake reviews, stars, installs, benchmark claims or CI badges. A passing emulator test is not a real-device compatibility guarantee.

Use [GitHub Issues](https://github.com/liu-qingyuan/together-cinema/issues) for requests, triage and the backlog; pull requests are for review. To enable the feature-record hooks in a fresh clone, run `./.feature-docs/run install`.
