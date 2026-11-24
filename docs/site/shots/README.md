# Viewer interface screenshots

The twelve WebPs are photographs of the running UI (six per language).
The existing entry card is unchanged. Library, Direct and Relay show the
grouped tool cards; Upload shows a real, throttled local demo transfer and its
ETA. Voice shows the night-mode controls, without joining a call.

To refresh the changed panels, run `python -m scripts.capture_site_shots` from
the repository root with the app dependencies, Chrome, Playwright, ffmpeg and
cwebp installed. It uses a fresh local server and temporary media directory per
language, not a production library. The files, room code and unsubmitted
media.example.org URL are demo content. Upload speed/ETA are examples, not a
speed guarantee. Each homepage links its own language’s full-size images.
