# Publishing checklist

Source releases are published at https://github.com/liu-qingyuan/together-cinema. The application source is MIT; third-party assets keep their own licenses.

Before publishing a release:

- Inspect every tracked file and `git diff`; never include `.env`, ACCESS.txt, private films, deployment dumps, local paths, keys, image archives or personal logs.
- Run original tests, installer contracts, actual Docker health/login/media smoke and public-profile auth smoke.
- Record tested architecture; do not claimARM64/AMD64/TLS issuance/real mobile results that were not executed.
- Review `THIRD_PARTY_NOTICES.md` and runtime binary license obligations before publishing container binaries.
- Enable private vulnerability reporting and choose maintainers/support policy.
- Verify clone URLs, release links and CI status against the release commit.
- Write a short release note showing what is stable, optional and known broken (including Quark).

Growth comes after this: a 30-second original demo, good screenshots, bilingual docs, fast first issue responses and consistent releases. There is no promise of a star count and no plan for purchased/artificial stars.

## Versioned production releases (Linux, Compose + Nginx)

For installations with a versioned `watch` image, a loopback port, and Nginx serving
the release's static homepage and scenes, use **deploy/release_live.py** as the update
entry point. It replaces the manual “switch, then clean the server” procedure.
The ordinary installer remains data-preserving; it is not the updater for this layout.
Current staged releases keep the Python package in `cinema/` and the static root in
`web/`. The release tool selects each release's static root independently, so it can
still check or roll back to older releases whose homepage was at the release root.

1. On a trusted workstation, select a reviewed commit with green CI. Stage its
   Docker build inputs in a **new** `releases/<first 12 hex of commit>` under the
   deployment root. Export from Git, not the working tree; never include private
   .env, data, subtitles, dumps or Docker volumes. For example:
   ```sh
   rev=$(git rev-parse HEAD)
   short=$(git rev-parse --short=12 "$rev")
   git archive "$rev" -- Dockerfile .dockerignore requirements.txt cinema web |
     ssh "$DEPLOY_HOST" "cd '$DEPLOY_ROOT' && mkdir 'releases/$short' && tar xf - -C 'releases/$short'"
   ```
2. Install the trusted release tool and its matching `scripts/smoke.py` together
   (preserve the deploy/ and scripts/ layout). On the service host invoke:
   ```sh
   python3 deploy/release_live.py --root "$DEPLOY_ROOT" --nginx-site "$NGINX_SITE" \
     --public-url "$PUBLIC_ORIGIN" --revision "$rev"
   ```
   Use `--check-current` instead of `--revision` to test the running version
   without switching versions or deleting images. Run during an idle window:
   the release refuses to switch while there are established playback-service connections by default. Operators who accept a brief interruption may pass `--allow-connected` to switch without waiting for disconnection. Canary, public playback verification and rollback are unchanged.
3. The canary uses an isolated network and tmpfs, uploads only a generated movie,
   checks its media range, decodes frames, and joins its own WebSocket room.
   After the switch the public gate checks health, exact homepage/CSS bytes,
   a 206 range, and decodes the entire served opening clip input to two frames.
   It does not select a film or upload anything to production.
4. Only after success: remove this run's private builder/cache if created, the
   exact superseded app tag if no other container (including stopped containers)
   or configured service uses it, and this run's scratch configuration copies.
   On hosts without Buildx, the classic builder creates no separate BuildKit
   cache; Docker retains current/shared ancestors. Never run daemon-wide prune,
   enumerate files to purge by age, or delete volumes or version directories.
5. Canary failure leaves the old service untouched. Failed activation or live
   verification restores and verifies the previous config and image. Failed
   cleanup does **not** roll back a good release. On failure inspect the printed
   private scratch directory (including builder name where applicable) and candidate
   tag before retrying. No SSH credentials or production targets belong in CI.
