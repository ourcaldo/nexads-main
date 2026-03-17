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

```bash
pip install -r requirements.txt
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
