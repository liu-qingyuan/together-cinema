# Third-party notices

The project source and original vector artwork are MIT licensed. That does **not** relicense dependencies, vendored files, Docker base images, or FFmpeg.

| Distribution | Version | License / retained notice | Upstream |
|---|---|---|---|
| Artplayer | 5.4.0 | MIT, `web/assets/ARTPLAYER-LICENSE.txt` | https://github.com/zhw2590582/ArtPlayer |
| HLS.js | 1.7.4 | Apache-2.0, `web/assets/LICENSE-hls.txt` and `LICENSES/Apache-2.0.txt` | https://github.com/video-dev/hls.js |
| libpgs | 0.9.0 | MIT, `web/assets/LICENSE-libpgs.txt` | https://github.com/Arcus92/libpgs-js |
| danmaku | 2.0.10 | MIT, `web/assets/LICENSE-danmaku.txt` and embedded header | https://github.com/weizhenye/Danmaku |
| Browser seccomp profile | modified source snapshot | Apache-2.0, `LICENSES/Apache-2.0.txt` | https://github.com/microsoft/playwright/blob/main/utils/docker/seccomp_profile.json |

Seccomp changes from the imported Playwright profile allow `pidfd_open`, `pidfd_send_signal`, and `chroot` for the non-root Chromium namespace sandbox. The browser sandbox is not disabled.

Runtime packages (aiohttp, Playwright, yt-dlp, Node.js, Caddy, Python and FFmpeg) retain their own upstream licenses. The pinned Node distribution is fetched from nodejs.org with an architecture-specific SHA256 check. FFmpeg is installed from Debian; its build can include GPL components. Docker runtime licensing is not covered by the application MIT license. Retain `/usr/share/doc` notices and review the binary/source redistribution requirements before publishing container binaries. This first source distribution builds from upstream packages; it does not include prebuilt runtime binaries or movies.

The README banner is MIT-licensed; personal room wallpapers are third-party artwork, as credited below. The gallery additionally includes two third-party CC BY 4.0 works, not relicensed as MIT:

| Gallery work | Author / original source | License / changes |
|---|---|---|
| Sky Backgrounds | [Unicorn Creates](https://unicorncreates.itch.io/sky-backgrounds), [selected daytime JPEG](https://img.itch.zone/aW1hZ2UvNDMxOTM4MS8yNTgxNDE1NS5qcGc=/original/RcHjox.jpg) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); desktop full 1280×720, mobile center crop 480×720, WebP quality 84 |
| Milky way in Elbrus | [oliwok / Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Milky_way_in_Elbrus.jpg) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); full portrait resized from 3648×5472 to 960×1440 / 480×720, WebP quality 86, metadata removed; no crop or recoloring |

Full attribution, original file links and modifications ship in `web/assets/scenes/sources.json`; the retained license text is `web/assets/scenes/LICENSE-CC-BY-4.0.txt`. Both are available through `/scenes/` in the app image. Only the selected optimized derivatives ship, not the reference gallery packs or the 26 MB original photograph. Screenshots in `docs/evidence/gallery/` reproduce these works under the same CC BY 4.0 attribution; screenshot framing and browser UI are added by Together Cinema contributors.

The private deployment's other external photographs, anime images, movie stills and screenshots are intentionally not redistributed.

## Personal room wallpapers

WebP derivatives are resized from the listed artists’ published works, not generated or relicensed under MIT. Shown as integrated room backgrounds. No filters or AI repainting. Source dimensions and licenses are in the shipped scene credits.

- 盛夏晴空（亦用作无声开场：裁切、缓慢推镜，6 秒 H.264） — *Sky Backgrounds* (daylight), [Unicorn Creates](https://unicorncreates.itch.io/sky-backgrounds) · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- 雨中巴黎 — [Ana Vieira](https://www.pexels.com/photo/black-and-white-photo-of-a-cobblestone-street-between-buildings-in-paris-on-a-rainy-day-20889037/) · [Pexels License](https://www.pexels.com/license/)
- 午睡时间 — [Dimitar Dimitrov](https://www.pexels.com/photo/a-close-up-shot-of-a-sleeping-cat-7249473/) · [Pexels License](https://www.pexels.com/license/)
- 额间轻吻 — [Andriyko Podilnyk](https://unsplash.com/photos/man-kissing-womans-forehead-3p6RZXty-7c) · [Unsplash License](https://unsplash.com/license)
- 山野晨雾 — [Felix Mittermeier](https://www.pexels.com/photo/green-mountains-photo-1269808/) · [Pexels License](https://www.pexels.com/license/)
- 樱花小径 — [Pexels photo #31727069](https://www.pexels.com/photo/serene-cherry-blossom-pathway-in-springtime-31727069/) · [Pexels License](https://www.pexels.com/license/)
- 白色轨道 — [David Vives](https://www.pexels.com/photo/oculus-interior-architecture-in-new-york-city-36050278/) · [Pexels License](https://www.pexels.com/license/)
- 涩谷十字路口 — [Sarmat Batagov](https://unsplash.com/photos/busy-city-intersection-at-night-with-bright-lights-2HbkIQeZRBc) · [Unsplash License](https://unsplash.com/license)

## Motion (room settings only)

The optional locally served bundle uses [Motion](https://motion.dev/) 12.23.24 (MIT). Build inputs: `web/comfort-motion/package-lock.json`; run `npm ci && npm run build` there to reproduce it. License texts: `LICENSES/comfort-motion.txt`. Docker installation and playback do not require Node or a CDN.

## Documentation screenshots

The [screenshot gallery and optional animated walkthrough](docs/showcase/README.md) use local demonstration rooms and the credited scene derivatives above. The demo film loops the credited Sky Backgrounds opening. The two-screen composite adds device framing and captions. The third-party artwork retains its original terms.
