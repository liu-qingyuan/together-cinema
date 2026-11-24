# Security boundary

## Do not expose the bare app as a public media service

Room codes select a room; they do not grant different library permissions or provide strong authentication. Any authenticated room entrant can access, upload and delete the **whole** library. The shared-password HTTPS gateway protects the deployment; this is a trusted-friends product, not a multi-tenant service or private ACL for each room.

Default bind is127.0.0.1. The optional public Caddy entry uses HTTPS and Basic Auth. Keep `.env` private, never paste it into issues, and do not forward8080 without a separate access gate. Changing the signing secret invalidates browser sessions and worker authentication. There is no account recovery or user-role system.

Network extraction processes untrusted public webpages. Public-IP validation, pinned DNS connections, request/body/time limits, non-root Chromium sandbox, dead-proxy fallback, read-only containers and process cleanup reduce risk; they are not a proof of complete SSRF isolation or immunity to browser vulnerabilities. Preserve these controls. Never enableprivileged or disablethe sandbox just to make an unknown host work. Keep pinned dependencies reviewed and updated.

No credentials, cookies, login sessions or DRM bypass are imported from viewers. Do not submit signed video URLs containing tokens in public issues. Logs/HARs may contain private URLs; redact confirmed secrets in display copies, not runtime configuration.

## Report a vulnerability

Do not post vulnerabilities in public issues. Use GitHub private vulnerability reporting if enabled for this repository; otherwise ask the maintainer for a private contact channel without disclosing exploit details. No unconfirmed contact address is provided.
