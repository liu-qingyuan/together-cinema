# Together Cinema

[English](README.md) · [简体中文](README.zh-CN.md)

**[Project website](https://liu-qingyuan.github.io/together-cinema/)** · **[Host your own](https://liu-qingyuan.github.io/together-cinema/deploy/en.html)** · [Viewer guide](https://liu-qingyuan.github.io/together-cinema/help/en.html)

[![MIT license](https://img.shields.io/github/license/liu-qingyuan/together-cinema)](LICENSE)
[![Latest release](https://img.shields.io/github/v/release/liu-qingyuan/together-cinema)](https://github.com/liu-qingyuan/together-cinema/releases/latest)
[![Main branch tests and container smoke](https://github.com/liu-qingyuan/together-cinema/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/liu-qingyuan/together-cinema/actions/workflows/ci.yml?query=branch%3Amain)
[![Deploy with Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED)](https://liu-qingyuan.github.io/together-cinema/deploy/en.html)
[![Feature requests and bug reports](https://img.shields.io/badge/feedback-GitHub_Issues-475569)](https://github.com/liu-qingyuan/together-cinema/issues/new/choose)
[![Release feed](https://img.shields.io/badge/RSS-releases-e78024)](https://github.com/liu-qingyuan/together-cinema/releases.atom)
[![Main branch commit feed](https://img.shields.io/badge/RSS-commits-e78024)](https://github.com/liu-qingyuan/together-cinema/commits/main.atom)

[Latest stable release](https://github.com/liu-qingyuan/together-cinema/releases/latest) · [Current architecture: control and media paths](docs/architecture/current.en.md)

**Different places. The same moment.** A self-hosted watch-party space: synchronized playback, a shared library, text chat, optional WebRTC voice, subtitles and personal scenery.

[20-second walkthrough](docs/showcase/tour.webp) · [Host your own cinema](https://liu-qingyuan.github.io/together-cinema/deploy/en.html) · [Join a friend's invitation (no Docker)](https://liu-qingyuan.github.io/together-cinema/help/en.html#start)

[![Two independent sessions in one demo room: a light desktop and a dark mobile viewport, paused at the same moment](docs/showcase/hero.webp)](docs/showcase/README.md)

One friend paused the film at 00:13; both screens stopped on the same frame. [Desktop view](docs/showcase/desktop.webp) · [Mobile view](docs/showcase/mobile.webp). These are real browser captures with Chinese UI; the current app also offers English, selected locally in Viewing settings. A mobile viewport is not a physical-phone test.

| Enter a room | Choose a film beside the player |
| --- | --- |
| [![Room-code entry beneath a starry mountain sky](docs/showcase/entry.webp)](docs/showcase/entry.webp) | [![Shared library and the new Library tools card](docs/site/shots/en-library.webp)](docs/site/shots/en-library.webp) |
| **Browse the screening journal** | **Choose your personal scenery** |
| [![Filmstrip of built-in sample titles and dates](docs/showcase/journal.webp)](docs/showcase/journal.webp) | [![Cherry-blossom scene in the personal gallery](docs/showcase/scenes.webp)](docs/showcase/scenes.webp) |

[Upload progress and voice settings: see the screenshots](https://liu-qingyuan.github.io/together-cinema/#room-tools).

[Full screenshot tour and artwork credits (Chinese, with English scene headings) →](docs/showcase/README.md). Journal titles and dates in that empty-room capture are explicitly built-in examples, not real viewing history.

<a id="start"></a><a id="join-an-invitation"></a><a id="video-discovery"></a>

## Getting started

- **Hosting?** Follow the [Docker deployment guide](https://liu-qingyuan.github.io/together-cinema/deploy/en.html): install locally, enable HTTPS, verify playback, and upgrade while keeping your media. Images are built on your host.
- **Invited?** Open your friend’s link; no Docker or extension is needed. The [viewer guide](https://liu-qingyuan.github.io/together-cinema/help/en.html) covers choosing a film, subtitles, sync, and [direct vs. relay](https://liu-qingyuan.github.io/together-cinema/help/en.html#modes).

Room codes do not isolate the library. Use protected HTTPS and invite only people you trust: admitted members can upload and delete films. Use only media you have permission to share.

[Contribute](CONTRIBUTING.md) · [Architecture](docs/architecture/current.en.md) · [Compatibility](docs/compatibility.md) · [Security](SECURITY.md) · [Releases](https://github.com/liu-qingyuan/together-cinema/releases)

Original code: [MIT](LICENSE). Third-party media and libraries retain [their own licenses](THIRD_PARTY_NOTICES.md).
