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

### Run automation
```bash
python main.py
```

### Open configuration GUI
```bash
python main.py --config
```

## Configuration

All settings are stored in `config.json`. Edit via the GUI (`--config`) or manually:

| Section | Key Fields |
|---------|-----------|
| **proxy** | `type` (http/https/socks4/socks5), `credentials`, `file` |
| **browser** | `headless_mode` (True/False/virtual), `disable_ublock`, `random_activity`, `auto_accept_cookies`, `prevent_redirects`, `activities` (scroll/hover/click) |
| **delay** | `min_time`, `max_time` (seconds between actions) |
| **session** | `enabled`, `count` (0=unlimited), `max_time` (minutes) |
| **threads** | Number of parallel browser workers |
| **os_fingerprint** | List of OS to emulate: `windows`, `macos`, `linux` |
| **device_type** | `mobile` / `desktop` percentage split |
| **referrer** | `types` (direct/social/organic/random), `organic_keywords` |
| **urls** | List of `{url, random_page, min_time, max_time}` |
| **ads** | `ctr` (percentage), `min_time`, `max_time` (seconds on ad page) |

## Files

| File | Purpose |
|------|---------|
| `main.py` | Core automation engine |
| `ui.py` | PyQt5 configuration GUI |
| `config.json` | Runtime configuration |
| `proxy.txt` | Proxy list (one per line) |
| `referrers.json` | Social media referrer domains |
| `requirements.txt` | Python dependencies |
