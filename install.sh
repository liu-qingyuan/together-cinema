#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"
usage() {
 cat <<'HELP'
Together Cinema installer (Docker Engine + Compose v2 required)
Usage: ./install.sh [--network] [--domain HOST] [--port PORT] [--check]
  --network       Enable bounded YouTube/dynamic-page extractor (larger image)
  --domain HOST   Enable HTTPS + shared access password; DNS and ports80/443 required
  --port PORT     Local HTTP port, default8080 (binds127.0.0.1)
  --check         Validate Compose config only; never start containers
  --help          Show this help without Docker or filesystem changes
Secrets are generated once in .env (mode600); media lives in a named Docker volume.
No sudo, automatic backups, remote shell download, or global prune is performed.
HELP
}
fail() { printf '%s\n' "Error: $*" >&2; exit 1; }
random_hex() {
 token=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
 [ "${#token}" -eq 64 ] || fail 'Cannot obtain secure randomness'
 printf '%s' "$token"
}
set_value() {
 key=$1 value=$2
 awk -v key="$key" -v value="$value" 'BEGIN{found=0} index($0,key "=")==1 {print key "=" value;found=1;next} {print} END{if(!found)print key "=" value}' .env > ".env.tmp.$$"
 chmod 600 ".env.tmp.$$"; mv ".env.tmp.$$" .env
}
get_value() { awk -v key="$1" 'index($0,key "=")==1 {print substr($0,length(key)+2);exit}' .env; }
add_profile() {
 profiles=$(get_value COMPOSE_PROFILES)
 case ",$profiles," in *",$1,"*) ;; *) if [ -n "$profiles" ]; then profiles="$profiles,$1"; else profiles=$1; fi; set_value COMPOSE_PROFILES "$profiles";; esac
}
main() {
 network=false domain='' port='' check=false
 while [ "$#" -gt 0 ]; do
  case "$1" in
   --help|-h) usage; return 0;;
   --network) network=true; shift;;
   --check) check=true; shift;;
   --domain|--port)
    [ "$#" -ge 2 ] || fail "Missing value for $1"
    case "$1" in --domain) domain=$2;; --port) port=$2;; esac; shift 2;;
   *) fail "Unknown argument: $1";;
  esac
 done
 if [ -n "$domain" ]; then
  case "$domain" in *[!a-zA-Z0-9.-]*|.*|*.|*..*|-*|*-) fail 'Domain must be a plain DNS hostname, no URL/path/port';; esac
  case "$domain" in *.*) ;; *) fail 'A public hostname is required for automatic HTTPS';; esac
 fi
 if [ -n "$port" ]; then
  case "$port" in *[!0-9]*) fail 'Port must be numeric';; esac
  [ "$port" -gt 0 ] && [ "$port" -le 65535 ] || fail 'Port must be1..65535'
 fi
 command -v docker >/dev/null 2>&1 || fail 'Install Docker Engine/Desktop and Compose v2 first; see docs/deployment.md'
 docker compose version >/dev/null 2>&1 || fail 'Docker Compose v2 is required'
 if [ "$check" = false ]; then docker info >/dev/null 2>&1 || fail 'Docker daemon is unavailable; start Docker and retry'; fi
 mkdir .install.lock 2>/dev/null || fail 'Another install is active, or stale .install.lock remains; inspect before removing it'
 trap 'rm -f ".env.tmp.$$"; rmdir .install.lock 2>/dev/null || true' EXIT HUP INT TERM
 umask 077
 [ ! -L .env ] || fail 'Refusing symlink .env'
 if [ ! -f .env ]; then
  signing=$(random_hex); site=$(random_hex)
  cat > ".env.tmp.$$" <<ENV
WATCH_PASSWORD=$signing
SITE_PASSWORD=$site
HOST_PORT=8080
COOKIE_SECURE=false
CADDY_SITE=
COMPOSE_PROFILES=
RESERVE_BYTES=2147483648
WATCH_TURN_URLS=
WATCH_TURN_SECRET=
ENV
  mv ".env.tmp.$$" .env
 fi
 chmod 600 .env
 signing=$(get_value WATCH_PASSWORD); site=$(get_value SITE_PASSWORD)
 case "$signing:$site" in *CHANGE_ME*) fail 'Replace example secrets, or remove an unused example .env and rerun';; esac
 [ "${#signing}" -ge 32 ] && [ "$signing" != CHANGE_ME ] || fail 'WATCH_PASSWORD must be a unique secret, at least32 characters'
 [ "${#site}" -ge 32 ] && [ "$site" != CHANGE_ME ] || fail 'SITE_PASSWORD must be a unique secret, at least32 characters'
 if [ "$network" = true ]; then add_profile network; fi
 if [ -n "$domain" ]; then set_value CADDY_SITE "$domain"; set_value COOKIE_SECURE true; add_profile https; fi
 if [ -n "$port" ]; then set_value HOST_PORT "$port"; fi
 docker compose config --quiet
 if [ "$check" = true ]; then printf '%s\n' 'Configuration valid; no containers started.'; return 0; fi
 printf '%s\n' "Docker context: $(docker context show)"
 docker compose up --build --detach --wait --wait-timeout 180
 domain=$(get_value CADDY_SITE)
 if [ -n "$domain" ]; then
  printf '%s\n' "Ready: https://$domain" 'Site login username: cinema' 'Site password: read SITE_PASSWORD from your private .env (never commit/share that file).'
  printf '%s\n' 'DNS must point to this host; allow TCP80/443. Initial certificate issuance may take time.'
 else printf '%s\n' "Ready: http://127.0.0.1:$(get_value HOST_PORT)" 'Local-only listener. Use --domain HOST for protected public HTTPS.'; fi
}
main "$@"
