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

echo "[6/6] Fetching Camoufox browser binaries..."
python3 -m camoufox fetch

if [ "${INSTALL_PLAYWRIGHT_FIREFOX:-0}" = "1" ]; then
  echo "Installing Playwright Firefox (optional)..."
  python3 -m playwright install firefox
fi

echo "Setup complete."
echo "Run automation with: python3 main.py"
echo "Open config UI with: python3 main.py --config"
echo "Run in background with logs: nohup python3 main.py > nexads.log 2>&1 &"
echo "Watch logs live: tail -f nexads.log"
