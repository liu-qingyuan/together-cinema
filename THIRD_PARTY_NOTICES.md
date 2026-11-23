# Third-party notices

The project source and original vector artwork are MIT licensed. That does **not** relicense dependencies, vendored files, Docker base images, or FFmpeg.

| Distribution | Version | License / retained notice | Upstream |
|---|---|---|---|
| Artplayer | 5.4.0 | MIT, `assets/ARTPLAYER-LICENSE.txt` | https://github.com/zhw2590582/ArtPlayer |
| HLS.js | 1.7.4 | Apache-2.0, `assets/LICENSE-hls.txt` and `LICENSES/Apache-2.0.txt` | https://github.com/video-dev/hls.js |
| libpgs | 0.9.0 | MIT, `assets/LICENSE-libpgs.txt` | https://github.com/Arcus92/libpgs-js |
| danmaku | 2.0.10 | MIT, `assets/LICENSE-danmaku.txt` and embedded header | https://github.com/weizhenye/Danmaku |
| Browser seccomp profile | modified source snapshot | Apache-2.0, `LICENSES/Apache-2.0.txt` | https://github.com/microsoft/playwright/blob/main/utils/docker/seccomp_profile.json |

Seccomp changes from the imported Playwright profile allow `pidfd_open`, `pidfd_send_signal`, and `chroot` for the non-root Chromium namespace sandbox. The browser sandbox is not disabled.

Runtime packages (aiohttp, Playwright, yt-dlp, Node.js, Caddy, Python and FFmpeg) retain their own upstream licenses. The pinned Node distribution is fetched from nodejs.org with an architecture-specific SHA256 check. FFmpeg is installed from Debian; its build can include GPL components. Docker runtime licensing is not covered by the application MIT license. Retain `/usr/share/doc` notices and review the binary/source redistribution requirements before publishing container binaries. This first source distribution builds from upstream packages; it does not include prebuilt runtime binaries or movies.

All six backgrounds and the README banner in this distribution are original vector artwork. The private deployment's external photographs, anime images, movie stills and screenshots are intentionally not redistributed.
