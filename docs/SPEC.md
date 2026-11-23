# First distributable release

- Export original application into a separate Git project; never alter personal production.
- No private credentials/domains/IPs/reports/videos in tracked files. Allowlisted source and vendor licenses only.
- `./install.sh` on a Docker+Compose host initializes unique secrets, starts core+converter, waits for health. No sudo/curl shell, no automatic backups, no system prune.
- Default listener loopback. `--domain HOST` enables optional HTTPS with shared Basic Auth access gate; room codes are not authorization.
- `--network` enables existing bounded dynamic extractor. Optional external TURN documented, not silently provisioned or claimed universally working.
- Repeat install preserves secrets and data. Uninstall preserves named volume unless explicit `--purge-data --yes`.
- Ship README in Chinese+English, original redistributable scene artwork, licenses, deployment/security/contributing docs and CI.
- Actual local Docker build/health/browser smoke plus original tests; do not label unexecuted platforms as verified.
- No remote creation/push/publication until owner/repository confirmation. No guarantee of GitHub stars.
