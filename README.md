# nexAds

An automation tool to boost traffic with browser fingerprint spoofing and human-like browsing behavior.

## Features

- **Anti-detect Browser**: Uses Camoufox (Firefox-based) with randomized fingerprints
- **Multi-threaded**: Run multiple parallel browser sessions
- **Proxy Support**: HTTP, HTTPS, SOCKS4, SOCKS5 (from file or credentials)
- **Smart Referrers**: Direct, social media, or organic Google search referrers
- **Human-like Behavior**: Random scrolling, clicking, hovering with cursor trails
- **Ad Interaction**: Configurable CTR-based AdSense ad clicking
- **GDPR/Cookie Handling**: Auto-accepts cookie consent popups
- **Vignette Ad Support**: Detects and interacts with vignette ads
- **GUI Configuration**: PyQt5 dark-mode configuration editor

## Installation

### Quick Ubuntu Server Setup (one script)

Run the automated installer to set up Python, pip, xvfb, Linux runtime libraries, Python dependencies, and Camoufox binaries:

```bash
chmod +x scripts/setup_ubuntu.sh
./scripts/setup_ubuntu.sh
```

By default, the installer now also auto-starts nexAds in background (`nohup + setsid`) after setup.

You can also run it from anywhere with an explicit shell command:

```bash
bash scripts/setup_ubuntu.sh
```

Optional: also install Playwright Firefox during setup:

```bash
INSTALL_PLAYWRIGHT_FIREFOX=1 ./scripts/setup_ubuntu.sh
```

Optional: disable auto-start after setup:

```bash
RUN_IN_BACKGROUND=0 ./scripts/setup_ubuntu.sh
```

When auto-start is used, the installer writes:
- `nexads.pid` (parent PID)
- `nexads.pgid` (process group ID)

Stop the full background tree (workers + browser children):

```bash
bash scripts/stop_nexads.sh
```

Run nexAds in background and write logs to a file:

```bash
nohup setsid python3 main.py > nexads.log 2>&1 < /dev/null &
tail -f nexads.log
```

If you stop with `kill <pid>` only, child browser processes may remain.
Prefer killing the whole process group:

```bash
kill -TERM -- -$(cat nexads.pgid)
```

If `git pull` is blocked by local changes and you want to force-sync your local copy to GitHub `main` (discard local uncommitted changes):

```bash
git fetch origin
git reset --hard origin/main
git clean -fd
```

Official Camoufox docs used in this guide:
- Installation: https://camoufox.com/python/installation/
- GeoIP: https://camoufox.com/python/geoip/
- Virtual display: https://camoufox.com/python/virtual-display/

### 1) Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2) Install/upgrade Camoufox with GeoIP support (recommended)

Camoufox official docs recommend installing with the `geoip` extra, especially when using proxies:

```bash
pip install -U "camoufox[geoip]"
```

Note: `camoufox[geoip]` is already included in this project's `requirements.txt`.  
Run the command above if you want to force-update Camoufox to the latest release.

### 3) Download Camoufox browser binaries (required)

After installation, fetch the browser:

```bash
python -m camoufox fetch
```

Alternative:

```bash
camoufox fetch
```

### 4) Linux dependencies (fresh Linux installs)

If Camoufox/Firefox fails to start on a clean Linux machine, install:

```bash
sudo apt install -y libgtk-3-0 libx11-xcb1 libasound2
```

### 5) Virtual display mode (recommended for Linux headless runs)

Camoufox docs recommend using a virtual display buffer instead of plain headless mode.

Install `xvfb`:

```bash
sudo apt-get install xvfb
```

If you get `E: Unable to locate package xvfb` on Ubuntu, enable/update apt sources first:

```bash
sudo apt-get update
sudo apt-get install -y software-properties-common
sudo add-apt-repository -y universe
sudo apt-get update
sudo apt-get install -y xvfb
```

If it still fails, verify distro/repositories:

```bash
cat /etc/os-release
apt-cache policy xvfb
grep -R "^deb " /etc/apt/sources.list /etc/apt/sources.list.d/ 2>/dev/null
```

Arch Linux:

```bash
sudo pacman -S xorg-server-xvfb
```

Verify:

```bash
which Xvfb
```

Then set `headless_mode` to `"virtual"` in `config.json` (or in the GUI).  
This project already passes that value to Camoufox (`headless="virtual"`).

### 6) Optional Playwright Firefox install

Not required for Camoufox itself, but useful for mixed Playwright workflows:

```bash
python -m playwright install firefox
```

## Camoufox GeoIP Notes

- This project already enables GeoIP in code (`app/browser/setup.py` sets `geoip=True`).
- With a proxy configured, Camoufox can align locale/timezone/location and WebRTC IP behavior to the target IP.
- Helpful Camoufox CLI commands:

```bash
python -m camoufox version
python -m camoufox path
python -m camoufox remove
```

## Usage

### Build AdSense signal list from EasyList

Generate candidate selectors/domains from EasyList into JSON:

```bash
python3 scripts/extract_adsense_signals.py
```

Custom source/output:

```bash
python3 scripts/extract_adsense_signals.py --source https://easylist.to/easylist/easylist.txt --output data/adsense_signals.json
```

The generated file can be used by ad detection/classification logic.

At runtime, nexAds will auto-check this file on startup and refresh it when missing/stale before workers are launched.

### Run automation
```bash
python main.py
```

### Open configuration GUI
```bash
python main.py --config
```

## Docker (Auto-run on deploy)

This repository now includes a production-ready `Dockerfile`, `docker-compose.yml`, and startup entrypoint.

### Quick start

```bash
docker compose up -d --build
```

This will automatically:
- install system dependencies (`xvfb`, Firefox/Camoufox runtime libs),
- install Python dependencies,
- fetch Camoufox browser binaries,
- start `python main.py` on container startup.

### Auto-start behavior

- Compose uses `restart: unless-stopped`, so it restarts automatically after reboot/deploy.
- Container startup uses your `config.json` directly (no runtime env override required).
- Set all behavior (`threads`, `urls`, `ads`, `referrer`, `browser`, etc.) in `config.json`.
- For containerized runs, set `proxy.file` in `config.json` to `proxy.txt`.
- Persistent browser storage is disabled; workers start fresh each session.

### Files used by Compose

- `./config.json` → `/app/config.json` (read-only)
- `./proxy.txt` → `/app/proxy.txt` (read-only)
- `./referrers.json` → `/app/referrers.json` (read-only)

### Common commands

```bash
docker compose logs -f nexads
docker compose restart nexads
docker compose down
```

## Configuration

All settings are stored in `config.json`. Edit via the GUI (`--config`) or manually:

| Section | Key Fields |
|---------|-----------|
| **proxy** | `type` (http/https/socks4/socks5), `credentials`, `file` |
| **browser** | `headless_mode` (True/False/virtual), `disable_ublock`, `random_activity`, `auto_accept_cookies`, `gdpr_max_wait_seconds`, `gdpr_on_fail` (`continue`/`skip_url`/`abort_session`), `prevent_redirects`, `activities` (scroll/hover/click) |
| **delay** | `min_time`, `max_time` (seconds between actions) |
| **session** | `enabled`, `count` (0=unlimited), `max_time` (minutes) |
| **threads** | Number of parallel browser workers |
| **os_fingerprint** | List of OS to emulate: `windows`, `macos`, `linux` |
| **device_type** | `mobile` / `desktop` percentage split |
| **referrer** | `types` (direct/social/organic/random), `organic_keywords` |
| **urls** | List of `{url, random_page, min_time, max_time}` |
| **ads** | `ctr` (percentage), `min_time`, `max_time` (seconds on ad page) |

## Mobile Fingerprint Operations

Operator rollout, validation gates, telemetry interpretation, and rollback procedure are documented in:

- `docs/runbook-mobile-fingerprint.md`

## Files

| File | Purpose |
|------|---------|
| `main.py` | Core automation engine |
| `ui.py` | PyQt5 configuration GUI |
| `config.json` | Runtime configuration |
| `proxy.txt` | Proxy list (one per line) |
| `referrers.json` | Social media referrer domains |
| `requirements.txt` | Python dependencies |
