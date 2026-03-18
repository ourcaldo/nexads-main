#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/app"

cd "$APP_DIR"

if [[ ! -f config.json ]]; then
  echo "config.json not found in $APP_DIR"
  exit 1
fi

if ! python3 -m camoufox path >/dev/null 2>&1; then
  echo "Camoufox binaries not found, fetching..."
  python3 -m camoufox fetch
fi

exec python3 main.py
