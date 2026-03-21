#!/usr/bin/env bash
set -euo pipefail

# One-shot Ubuntu setup for nexAds.
# Installs system dependencies, Python tooling, project packages, and Camoufox binaries.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_ROOT"

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This script requires apt-get (Ubuntu/Debian-based systems)."
  exit 1
fi

if [ ! -f "requirements.txt" ]; then
  echo "requirements.txt not found. Run this script from the nexads repository."
  exit 1
fi

RUN_IN_BACKGROUND="${RUN_IN_BACKGROUND:-1}"

echo "[1/7] Updating apt package index..."
sudo apt-get update

echo "[2/7] Installing repository and base utilities..."
sudo apt-get install -y software-properties-common ca-certificates curl git

# Ubuntu commonly needs 'universe' enabled for xvfb availability.
if grep -qi "ubuntu" /etc/os-release; then
  echo "[3/7] Enabling Ubuntu universe repository (safe if already enabled)..."
  sudo add-apt-repository -y universe || true
  sudo apt-get update
fi

ASOUND_PKG="libasound2"
if apt-cache show libasound2t64 >/dev/null 2>&1; then
  ASOUND_PKG="libasound2t64"
fi

echo "[4/6] Installing Python, virtual display, and browser runtime libraries..."
sudo apt-get install -y \
  python3 \
  python3-pip \
  xvfb \
  libgtk-3-0 \
  libx11-xcb1 \
  libdbus-glib-1-2 \
  "$ASOUND_PKG"

echo "[5/6] Installing Python dependencies from requirements.txt..."
python3 -m pip install --break-system-packages --upgrade pip setuptools wheel
python3 -m pip install --break-system-packages -r requirements.txt

echo "[6/8] Fetching Camoufox browser binaries..."
python3 -m camoufox fetch

echo "[7/8] Installing CloakBrowser + stealth Chromium binary (mobile sessions)..."
python3 -m pip install --break-system-packages -q "cloakbrowser[geoip]"
python3 -m cloakbrowser install || echo "CloakBrowser install verification failed (binary may still be usable)"

echo "[8/8] Installing Playwright Firefox (for Camoufox)..."
python3 -m playwright install firefox

if [ "${RUN_IN_BACKGROUND}" = "1" ]; then
  echo "Starting nexAds in background..."

  if [ -f "nexads.pid" ]; then
    existing_pid="$(tr -d '[:space:]' < nexads.pid)"
    if [ -n "${existing_pid}" ] && kill -0 "${existing_pid}" >/dev/null 2>&1; then
      echo "nexAds already appears to be running (PID: ${existing_pid})."
      echo "Use: bash scripts/stop_nexads.sh"
      echo "Skipping auto-start."
      echo "Setup complete."
      exit 0
    fi
  fi

  nohup setsid python3 main.py > nexads.log 2>&1 < /dev/null &
  bg_pid=$!
  bg_pgid="$(ps -o pgid= -p "${bg_pid}" 2>/dev/null | tr -d '[:space:]')"
  echo "${bg_pid}" > nexads.pid
  if [ -n "${bg_pgid}" ]; then
    echo "${bg_pgid}" > nexads.pgid
  fi
  echo "Started nexAds (PID: ${bg_pid}, PGID: ${bg_pgid:-unknown})"
  echo "Use scripts/stop_nexads.sh to stop all worker/browser children cleanly."
else
  echo "RUN_IN_BACKGROUND=${RUN_IN_BACKGROUND} -> skipping auto-start."
fi

echo "Setup complete."
echo "Run automation with: python3 main.py"
echo "Open config UI with: python3 main.py --config"
echo "Run in background with logs: nohup python3 main.py > nexads.log 2>&1 &"
echo "Watch logs live: tail -f nexads.log"
echo "Stop background run cleanly: bash scripts/stop_nexads.sh"
