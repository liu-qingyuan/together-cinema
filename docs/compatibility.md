# Compatibility and known limits

- Mac/desktop Chrome, iPhone/iPad Safari and other devices differ in H.265, native fullscreen, subtitle and autoplay behavior. Prefer stage fullscreen to preserve PGS overlays; OS picture-in-picture cannot be assumed to carry custom overlays.
- Android Quark: a user reported a black rectangle obscuring the upper half of video and the play icon. Standard mobile-viewport Chromium tests pass; a CSS-inset-unavailable experiment produces a different failure. Root cause is not confirmed and no blind compatibility patch is shipped. Compare with another browser and supply the original media page URL/Quark version privately when reproducing. Do not advertise this as fixed.
- Browser background tabs, network jitter and autoplay restrictions can delay sync until a user gesture.
- Generic extraction cannot support every site. DRM, login, CAPTCHA and some browser redirects are unsupported. Direct mode requires every viewer to reach the original source; relay consumes per-viewer egress.
- Unsupported subtitle/codecs may not be selectable or playable. MKV container support is not universal browser decode support.

Release validation must distinguish host unit tests, real Docker builds, desktop browser emulation and real physical devices. See the [historical Alpha validation](validation.md) for its dated results, and the [current code map](code-map.md) for regression entry points.
