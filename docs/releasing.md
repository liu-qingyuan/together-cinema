# Publishing checklist

This is a local candidate, not an already-published repository. The working name Together Cinema and MIT were confirmed; remote owner/name still need confirmation.

Before first public push:

- Inspect every tracked file and `git diff`; never include `.env`, ACCESS.txt, films, deployment dumps, local paths, keys, image archives or personal logs.
- Run original tests, installer contracts, actual Docker health/login/media smoke and public-profile auth smoke.
- Record tested architecture; do not claimARM64/AMD64/TLS issuance/real mobile results that were not executed.
- Review `THIRD_PARTY_NOTICES.md` and runtime binary license obligations before publishing container binaries.
- Enable private vulnerability reporting and choose maintainers/support policy.
- Replace generic clone placeholders only after the real remote exists. Add real CI/release badges only after those workflows run.
- Write a short release note showing what is stable, optional and known broken (including Quark).

Growth comes after this: a 30-second original demo, good screenshots, bilingual docs, fast first issue responses and consistent releases. There is no promise of a star count and no plan for purchased/artificial stars.
