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
