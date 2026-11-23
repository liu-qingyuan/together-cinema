#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
case "$*" in
 '') docker compose --profile '*' down; printf '%s\n' 'Stopped. Named volumes and .env retained; run ./install.sh to start again.';;
 '--purge-data --yes') docker compose --profile '*' down --volumes; printf '%s\n' 'Removed this Compose project volumes, including media and HTTPS certificates. .env retained.';;
 '--help'|'-h') printf '%s\n' './uninstall.sh stops containers and retains media.' './uninstall.sh --purge-data --yes permanently removes this project volumes.';;
 *) printf '%s\n' 'Refusing ambiguous removal. Use --help.' >&2; exit 64;;
esac
