#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/app"
RUNTIME_CONFIG="/tmp/nexads.config.json"

cd "$APP_DIR"

if [[ ! -f config.json ]]; then
  echo "config.json not found in $APP_DIR"
  exit 1
fi

# Build a runtime config copy so mounted host config.json is not mutated.
cp config.json "$RUNTIME_CONFIG"

python3 - <<'PY'
import json
import os
from pathlib import Path

runtime_path = Path("/tmp/nexads.config.json")
cfg = json.loads(runtime_path.read_text(encoding="utf-8"))
changed = False

browser = cfg.setdefault("browser", {})
proxy = cfg.setdefault("proxy", {})

headless_mode = os.getenv("NEXADS_HEADLESS_MODE", "").strip()
if headless_mode and browser.get("headless_mode") != headless_mode:
    browser["headless_mode"] = headless_mode
    changed = True

profile_dir = os.getenv("NEXADS_PROFILE_DIR", "").strip()
if profile_dir and browser.get("profile_dir") != profile_dir:
    browser["profile_dir"] = profile_dir
    changed = True

proxy_file_env = os.getenv("NEXADS_PROXY_FILE", "").strip()
if proxy_file_env:
    if proxy.get("file") != proxy_file_env:
        proxy["file"] = proxy_file_env
        changed = True
else:
    configured_proxy_file = str(proxy.get("file", "") or "").strip()
    proxy_credentials = str(proxy.get("credentials", "") or "").strip()
    default_proxy_file = Path("/app/proxy.txt")
    if (
        not proxy_credentials
        and default_proxy_file.exists()
        and (
            not configured_proxy_file
            or (":" in configured_proxy_file and "\\" in configured_proxy_file)
            or not Path(configured_proxy_file).exists()
        )
    ):
        proxy["file"] = "proxy.txt"
        changed = True

if changed:
    runtime_path.write_text(json.dumps(cfg, indent=4) + "\n", encoding="utf-8")
    print("Runtime config overrides applied.")
PY

if ! python3 -m camoufox path >/dev/null 2>&1; then
  echo "Camoufox binaries not found, fetching..."
  python3 -m camoufox fetch
fi

export NEXADS_CONFIG_PATH="$RUNTIME_CONFIG"
exec python3 main.py
