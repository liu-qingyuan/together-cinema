#!/bin/sh
set -eu
: "${SITE_PASSWORD:?Set a unique site password}"
BASIC_AUTH_HASH=$(caddy hash-password --plaintext "$SITE_PASSWORD")
export BASIC_AUTH_HASH
unset SITE_PASSWORD
exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
