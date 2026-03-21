"""
app/browser/proxy.py
Proxy string parsing and config resolution.
"""

import random
from typing import Optional, Dict

# Per-process cache: proxy file path -> list of proxy strings.
# Avoids re-reading the file on every session start.
_proxy_file_cache: Dict[str, list] = {}


def _looks_like_host(value: str) -> bool:
    """Return True when value resembles a host or IP."""
    if not value:
        return False

    candidate = value.strip().lower()
    if candidate == "localhost":
        return True

    if "." in candidate and " " not in candidate:
        return True

    parts = candidate.split(".")
    if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        return True

    return False


def _is_port(value: str) -> bool:
    """Return True when value is a valid TCP port string."""
    if not value or not value.isdigit():
        return False
    port_num = int(value)
    return 1 <= port_num <= 65535


def parse_proxy_entry(proxy: str):
    """Parse proxy string to (host, port, username, password) or None."""
    value = (proxy or "").strip()
    if not value:
        return None

    username = None
    password = None
    host = None
    port = None

    if "@" in value:
        left, right = value.rsplit("@", 1)

        # Format: user:pass@host:port
        if ":" in right:
            candidate_host, candidate_port = right.rsplit(":", 1)
            if _is_port(candidate_port):
                host = candidate_host
                port = candidate_port
                if ":" in left:
                    username, password = left.split(":", 1)
                else:
                    username, password = left, ""
                return host, port, username, password

        # Format: host:port@user:pass
        if ":" in left and ":" in right:
            candidate_host, candidate_port = left.rsplit(":", 1)
            if _is_port(candidate_port):
                host = candidate_host
                port = candidate_port
                username, password = right.split(":", 1)
                return host, port, username, password

        return None

    # Formats without @.
    parts = value.split(":")

    # Format: host:port
    if len(parts) == 2 and _is_port(parts[1]):
        host, port = parts[0], parts[1]
        return host, port, None, None

    # Format: host:port:user:pass OR user:pass:host:port
    if len(parts) >= 4:
        if _is_port(parts[1]) and _looks_like_host(parts[0]):
            host = parts[0]
            port = parts[1]
            username = parts[2]
            password = ":".join(parts[3:])
            return host, port, username, password

        if _is_port(parts[-1]):
            candidate_host = parts[-2]
            if _looks_like_host(candidate_host):
                host = candidate_host
                port = parts[-1]
                username = parts[0]
                password = ":".join(parts[1:-2])
                return host, port, username, password

    return None


def resolve_proxy_config(config: dict) -> Optional[Dict[str, str]]:
    """Resolve and normalize one proxy config for browser launch."""
    proxy_value = None
    if config["proxy"]["credentials"]:
        proxy_value = config["proxy"]["credentials"]
    elif config["proxy"]["file"]:
        proxy_file = config["proxy"]["file"]
        if proxy_file not in _proxy_file_cache:
            with open(proxy_file, "r") as f:
                _proxy_file_cache[proxy_file] = [line.strip() for line in f if line.strip()]
        proxies = _proxy_file_cache[proxy_file]
        if proxies:
            proxy_value = random.choice(proxies)

    if not proxy_value:
        return None

    proxy_type = config["proxy"]["type"].lower()
    parsed_proxy = parse_proxy_entry(proxy_value)
    if not parsed_proxy:
        raise ValueError(
            "Unsupported proxy format. Use one of: "
            "ip:port, host:port:user:pass, host:port@user:pass, "
            "user:pass:host:port, user:pass@host:port"
        )

    host, port, user, pwd = parsed_proxy
    return {
        "server": f"{proxy_type}://{host}:{port}",
        "username": user,
        "password": pwd,
    }


def build_full_proxy_url(proxy_cfg: Dict[str, str]) -> str:
    """Build full proxy URL with embedded credentials for aiohttp."""
    server = proxy_cfg.get("server", "")
    if proxy_cfg.get("username") and proxy_cfg.get("password"):
        parsed = server.split("://")
        if len(parsed) == 2:
            return f"{parsed[0]}://{proxy_cfg['username']}:{proxy_cfg['password']}@{parsed[1]}"
    return server
