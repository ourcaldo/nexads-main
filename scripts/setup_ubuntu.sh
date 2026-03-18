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

echo "[4/7] Installing Python, virtual display, and browser runtime libraries..."
sudo apt-get install -y \
  python3 \
  python3-venv \
  python3-pip \
  xvfb \
  libgtk-3-0 \
  libx11-xcb1 \
  libdbus-glib-1-2 \
  "$ASOUND_PKG"

VENV_DIR="${VENV_DIR:-.venv}"
echo "[5/7] Creating/updating virtual environment at ${VENV_DIR}..."
python3 -m venv "$VENV_DIR"
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

echo "[6/7] Installing Python dependencies from requirements.txt..."
python -m pip install --break-system-packages --upgrade pip setuptools wheel
pip install --break-system-packages -r requirements.txt

echo "[7/7] Fetching Camoufox browser binaries..."
python -m camoufox fetch

if [ "${INSTALL_PLAYWRIGHT_FIREFOX:-0}" = "1" ]; then
  echo "Installing Playwright Firefox (optional)..."
  python -m playwright install firefox
fi

echo "Setup complete."
echo "Activate env with: source ${VENV_DIR}/bin/activate"
echo "Run automation with: python main.py"
echo "Open config UI with: python main.py --config"
