"""
nexads/navigation/explorer.py
Explorer mode: autonomous same-domain browsing via internal link discovery.
"""

from __future__ import annotations

import random
from urllib.parse import urlparse


# Path segments that real users wouldn't randomly click
BLOCKED_PATH_SEGMENTS = {
    "login", "logout", "signin", "signup", "register", "auth",
    "admin", "wp-admin", "wp-login", "wp-json", "dashboard",
    "cart", "checkout", "account", "my-account", "billing",
    "search", "feed", "rss", "api", "xmlrpc", "cgi-bin",
    "print", "embed", "preview", "trackback", "wp-cron",
}

# File extensions to skip
BLOCKED_EXTENSIONS = {
    ".pdf", ".zip", ".rar", ".exe", ".dmg", ".apk", ".msi",
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico", ".bmp",
    ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv",
    ".css", ".js", ".xml", ".json", ".woff", ".woff2", ".ttf", ".eot",
}

# URL schemes to skip
BLOCKED_SCHEMES = {"mailto:", "tel:", "javascript:", "data:", "blob:", "ftp:"}


def normalize_path(url: str) -> str:
    """Extract and normalize path for visited-set tracking."""
    try:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/").lower()
        return path or "/"
    except Exception:
        return "/"


def _strip_www(domain: str) -> str:
    """Remove leading www. prefix from domain."""
    d = domain.lower()
    return d[4:] if d.startswith("www.") else d


def _is_same_domain(href_domain: str, gate_domain: str) -> bool:
    """Check if href domain matches gate domain (including subdomains)."""
    if not href_domain or not gate_domain:
        return False
    href_clean = _strip_www(href_domain)
    gate_clean = _strip_www(gate_domain)
    return href_clean == gate_clean or href_clean.endswith(f".{gate_clean}")


def _is_blocked_path(path: str) -> bool:
    """Check if URL path contains blocked segments."""
    path_lower = path.lower()
    segments = path_lower.strip("/").split("/")
    for segment in segments:
        if segment in BLOCKED_PATH_SEGMENTS:
            return True
    return False


def _is_blocked_extension(path: str) -> bool:
    """Check if URL path ends with a blocked file extension."""
    path_lower = path.lower()
    for ext in BLOCKED_EXTENSIONS:
        if path_lower.endswith(ext):
            return True
    return False


def _is_blocked_scheme(href: str) -> bool:
    """Check if href uses a blocked scheme."""
    href_lower = href.lower().strip()
    for scheme in BLOCKED_SCHEMES:
        if href_lower.startswith(scheme):
            return True
    return False


async def discover_internal_links(page, gate_domain: str,
                                  visited_paths: set[str]) -> list[dict]:
    """Scan page for clickable same-domain links not yet visited.

    Returns list of dicts: {"element", "href", "path", "text"}
    """
    try:
        link_data = await page.evaluate(
            """
            () => {
                const links = document.querySelectorAll('a[href]');
                const results = [];
                const seen = new Set();
                for (let i = 0; i < Math.min(links.length, 150); i++) {
                    const a = links[i];
                    const href = a.href;
                    const raw = a.getAttribute('href') || '';
                    if (!href || seen.has(href)) continue;
                    seen.add(href);

                    const rect = a.getBoundingClientRect();
                    const style = window.getComputedStyle(a);
                    const visible = (
                        rect.width > 1 && rect.height > 1
                        && style.visibility !== 'hidden'
                        && style.display !== 'none'
                        && style.opacity !== '0'
                    );
                    const inViewport = (
                        rect.top < window.innerHeight + 200
                        && rect.bottom > -200
                    );

                    results.push({
                        href: href,
                        raw: raw,
                        text: (a.innerText || '').trim().substring(0, 100),
                        visible: visible,
                        in_viewport: inViewport,
                        index: i
                    });
                }
                return results;
            }
            """
        )
    except Exception:
        return []

    candidates = []
    for info in link_data:
        href = info.get("href", "")
        raw = info.get("raw", "")

        # Skip anchors-only, empty, and blocked schemes
        if not href or raw.startswith("#") or _is_blocked_scheme(raw):
            continue

        try:
            parsed = urlparse(href)
        except Exception:
            continue

        # Same-domain check
        href_domain = parsed.hostname or ""
        if not _is_same_domain(href_domain, gate_domain):
            continue

        path = parsed.path.rstrip("/").lower() or "/"

        # Skip blocked paths and extensions
        if _is_blocked_path(path) or _is_blocked_extension(path):
            continue

        # Skip already visited
        if normalize_path(href) in visited_paths:
            continue

        candidates.append({
            "href": href,
            "path": path,
            "text": info.get("text", ""),
            "visible": info.get("visible", False),
            "in_viewport": info.get("in_viewport", False),
            "index": info.get("index", 0),
        })

    return candidates


def select_next_link(candidates: list[dict]) -> dict | None:
    """Pick a link from candidates with weighted randomization."""
    if not candidates:
        return None

    # Assign weights: visible + in_viewport > visible > hidden
    weighted = []
    for c in candidates:
        w = 1.0
        if c.get("visible"):
            w += 3.0
        if c.get("in_viewport"):
            w += 2.0
        if c.get("text"):
            w += 1.0
        weighted.append((c, w))

    choices = [item[0] for item in weighted]
    weights = [item[1] for item in weighted]
    return random.choices(choices, weights=weights, k=1)[0]
