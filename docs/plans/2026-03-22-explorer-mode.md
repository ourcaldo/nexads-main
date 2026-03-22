# Explorer Mode — Implementation Plan

**Date:** 2026-03-22
**Goal:** Add an "Explorer Mode" that replaces the fixed URL sequence with autonomous same-domain browsing. The automation visits a single gate URL, then discovers and navigates internal pages by clicking links — making each session's path unique and unpatterned.

---

## Background & Motivation

Currently, every session visits the same URLs in the same order. Even with randomized timings and human-like activity, the **navigation pattern itself** is a fingerprint — Google can see the same user visiting the same 5 pages in the same sequence session after session.

Explorer mode solves this: the user provides one gate URL, and the automation autonomously discovers and browses internal pages on that domain, creating a unique path every session.

---

## Design Decisions (from discussion)

1. **Two modes coexist** — Sequential mode (existing) stays as-is. Explorer mode is a new toggle. When explorer is enabled, user puts only 1 gate URL and the "Add URL" button is disabled.
2. **Sequential mode cleanup** — Remove comma-separated URL format and the `random_page` checkbox column. Each row = one URL in sequential mode.
3. **Visited tracking** — Per-session `set()` of visited paths prevents revisiting the same page.
4. **Navigation via SmartClick only** — All page transitions use real clicks on visible links (not `page.goto()`). This produces natural referrer headers and navigation events.
5. **Dead-end fallback** — When no unvisited internal links exist, use `page.go_back()` (like a real user hitting back) and pick a different link. If back at the gate URL with no unvisited links, session ends naturally.
6. **Session time is the only cap** — No max page count. Each discovered page gets a random stay time (default min 30s, max 60s, configurable). Automation keeps exploring until session timer expires.
7. **Same-domain only** — Explorer never clicks external links. Only links matching the gate URL's domain (including subdomains) are eligible.
8. **Link quality filter** — Skip URLs a real user wouldn't randomly click: login, admin, cart, checkout, mailto, tel, javascript, file downloads, etc.

---

## Config Schema Changes

### Current `config.json` URL section
```json
"urls": [
    {
        "url": "https://example.com",
        "random_page": true,
        "min_time": 30,
        "max_time": 60
    }
]
```

### New `config.json` with explorer mode
```json
"explorer": {
    "enabled": false,
    "gate_url": "",
    "min_time": 30,
    "max_time": 60
},
"urls": [
    {
        "url": "https://example.com",
        "min_time": 30,
        "max_time": 60
    }
]
```

### Changes
- **New `explorer` section** with `enabled`, `gate_url`, `min_time` (default 30), `max_time` (default 60)
- **Remove `random_page`** field from URL entries (sequential mode cleanup)
- When `explorer.enabled` is `true`, the `urls` list is ignored — only `explorer.gate_url` is used
- When `explorer.enabled` is `false`, the `urls` list is used as before (minus `random_page`)

---

## Task Breakdown

### Task 1: Config schema update
**Files:** `app/ui/config_io.py`

- Add `explorer` section to `DEFAULT_CONFIG`:
  ```python
  "explorer": {
      "enabled": False,
      "gate_url": "",
      "min_time": 30,
      "max_time": 60
  }
  ```
- Remove `random_page` from default URL entry
- Add backward-compat handling in `load_config()`: if `explorer` key missing, inject default; if old URLs have `random_page`, strip it silently

### Task 2: GUI — Explorer mode toggle and URL section rework
**Files:** `app/ui/config_window.py`

**Explorer mode controls (new):**
- Add a checkbox: `"Enable Explorer Mode"` above the URL section
- When checked, show:
  - Gate URL input field (single URL)
  - Min Time / Max Time spinboxes (per-page stay time for discovered pages)
- When checked, hide/disable:
  - The URL table, Add URL button, Delete URL button
- When unchecked, show the URL table as before (sequential mode)

**Sequential mode cleanup:**
- Remove the "Random Page" column (column index 2) from the URL table
- Table columns become: `["#", "URL", "Min Time", "Max Time"]` (4 columns)
- Remove comma-separated URL splitting in `add_url_to_table()` — one URL per entry
- Update placeholder text: `"Enter URL"` (remove comma instruction)

**Save logic:**
- When explorer enabled: save `explorer.enabled = True`, `explorer.gate_url`, `explorer.min_time`, `explorer.max_time`
- When explorer disabled: save `explorer.enabled = False`, save `urls` list without `random_page`

### Task 3: Link discovery module
**Files:** `app/navigation/explorer.py` (new file)

Create a new module for explorer-mode link discovery and navigation:

```python
"""
nexads/navigation/explorer.py
Explorer mode: autonomous same-domain browsing via internal link discovery.
"""

# --- Constants ---

# URL path segments to skip (login, admin, cart, etc.)
BLOCKED_PATH_SEGMENTS = {
    "login", "logout", "signin", "signup", "register",
    "admin", "wp-admin", "wp-login", "dashboard",
    "cart", "checkout", "account", "my-account",
    "search", "feed", "rss", "api", "xmlrpc",
}

# File extensions to skip
BLOCKED_EXTENSIONS = {
    ".pdf", ".zip", ".rar", ".exe", ".dmg", ".apk",
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
    ".mp3", ".mp4", ".avi", ".mov", ".wmv",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".css", ".js", ".xml", ".json",
}

# URL schemes to skip
BLOCKED_SCHEMES = {"mailto:", "tel:", "javascript:", "data:", "blob:"}
```

**Functions:**

#### `discover_internal_links(page, gate_domain, visited_paths) -> list[dict]`
- Query all `<a href>` elements on the page
- Filter to same-domain only (match gate_domain, including subdomains like `blog.example.com` for `example.com`)
- Filter out: blocked path segments, blocked extensions, blocked schemes, anchors (`#`), already-visited paths
- For each eligible link, collect: `{"element": el, "href": href, "path": path, "text": text}`
- Return list of eligible link dicts
- Cap element scanning to first 100 `<a>` tags for performance

#### `select_next_link(candidates, current_path) -> dict | None`
- From the eligible candidates, pick one with slight weighting:
  - Prefer links visible in viewport (higher weight)
  - Prefer links with text content (not empty `<a>` tags)
  - Light randomization so it's not always the "best" link
- Return the selected link dict, or `None` if no candidates

#### `normalize_path(url) -> str`
- Extract path from URL, strip trailing slash, lowercase
- Used for visited-set tracking (avoid treating `/about/` and `/about` as different)
- Strip query params for dedup (except preserve meaningful ones? keep simple — strip all)

### Task 4: Explorer session loop
**Files:** `app/core/session.py`

Add an explorer-mode branch in the `run()` method, parallel to the existing URL-processing `for` loop:

```python
# --- URL PROCESSING ---
if explorer_enabled:
    await self._run_explorer_session(
        page, browser, wid, ctx, interaction_state,
        is_ads_session, session_start_time, session_deadline,
        _session_expired, _session_remaining, _emit_step,
    )
else:
    # existing for url_index, url_data in enumerate(ctx.config["urls"]): ...
```

#### `_run_explorer_session()` method on SessionRunner

```
1. Visit gate URL (via referrer — social/organic/direct, same as current first URL logic)
2. Initialize: visited_paths = {normalize_path(gate_url)}, page_count = 0
3. Loop while not _session_expired() and ctx.running:
    a. Compute stay_time from explorer min/max using lognormal randomization
    b. Clamp stay_time to remaining session budget
    c. Run perform_random_activity() on current page (with ads, consent, vignette — same as sequential)
    d. Discover internal links via discover_internal_links()
    e. Select next link via select_next_link()
    f. If no link found:
        - page.go_back() — navigate to previous page
        - Wait for page settle
        - Re-discover links (excluding visited)
        - If still no links, end session naturally
    g. Click selected link via smart_click()
    h. Wait for navigation + page settle
    i. Add new path to visited_paths
    j. page_count += 1
    k. Handle consent dialog if appears
    l. Continue loop
```

**Key details:**
- The gate URL is visited using the same referrer logic as the current first URL (social/organic/direct)
- Each subsequent page is reached by clicking a link — no `page.goto()`
- The `ensure_correct_tab` guard still runs to handle unexpected redirects
- Ad interaction still triggers during `perform_random_activity()` (same as sequential)
- Consent handling happens after each navigation (same as sequential)
- Vignette check happens during activity (same as sequential)
- Telemetry events still emitted for each page

### Task 5: SmartClick integration for explorer navigation
**Files:** `app/browser/click.py` (possibly), `app/core/session.py`

The explorer needs to click a specific `<a>` element to navigate. The existing `smart_click()` accepts an `element` parameter and handles:
- Scroll into view
- Humanized mouse movement
- Click with fallback chain

This already works. The explorer calls it like:
```python
await self._smart_click(page, wid, gate_domain, link_element, False, interaction_state)
```

With `is_ad_activity=False` since these are content links, not ads.

After clicking, wait for navigation to complete:
```python
await page.wait_for_load_state("domcontentloaded", timeout=30000)
await asyncio.sleep(timing_seconds("page_settle"))
```

### Task 6: process_ads_tabs compatibility
**Files:** `app/navigation/tabs.py`

`process_ads_tabs` uses config URLs to identify which tabs are "config" vs "ad" tabs. In explorer mode, it should treat the gate domain as the config domain:

```python
# Current: checks against all config URLs
if any(_domain_matches(current_url, extract_domain(url)) for url in config_urls):
    continue

# Explorer mode: check against gate domain
if explorer_enabled:
    if _domain_matches(current_url, extract_domain(gate_url)):
        continue
```

### Task 7: Sequential mode cleanup
**Files:** `app/core/session.py`, `app/ui/config_window.py`, `app/ui/config_io.py`

- Remove all `random_page` references in session.py URL processing
- In `session.py` line 468-472: remove the `if url_data["random_page"]:` branch that splits comma-separated URLs — just use `url_data["url"].strip()` always
- In `config_window.py`: remove Random Page column from table
- In `config_io.py`: remove `random_page` from default URL entry

---

## File Change Summary

| File | Change |
|------|--------|
| `app/ui/config_io.py` | Add `explorer` to DEFAULT_CONFIG, remove `random_page`, backward compat |
| `app/ui/config_window.py` | Explorer toggle + gate URL UI, remove Random Page column, save logic |
| `app/navigation/explorer.py` | **New file** — link discovery, selection, path normalization, blocked filters |
| `app/core/session.py` | Explorer session loop (`_run_explorer_session`), remove `random_page` handling |
| `app/navigation/tabs.py` | Explorer-aware config URL matching in `process_ads_tabs` |
| `app/browser/activities.py` | No changes — `perform_random_activity` works as-is |
| `app/browser/click.py` | No changes — `smart_click` already supports element-based clicks |
| `config.json` | Add `explorer` section, remove `random_page` from URLs |

---

## Implementation Order

| Step | Task | Description |
|------|------|-------------|
| 1 | Task 1 | Config schema: add `explorer`, remove `random_page`, backward compat |
| 2 | Task 7 | Sequential mode cleanup: remove `random_page` from session loop + GUI |
| 3 | Task 3 | Create `app/navigation/explorer.py` — link discovery module |
| 4 | Task 4 | Explorer session loop in `session.py` |
| 5 | Task 5 | SmartClick integration for explorer navigation |
| 6 | Task 6 | `process_ads_tabs` compatibility for explorer mode |
| 7 | Task 2 | GUI: explorer toggle, gate URL input, conditional visibility |

---

## Acceptance Criteria

1. **Explorer mode works end-to-end**: gate URL → discover links → click link → browse page → discover more → repeat until session ends
2. **No page visited twice**: visited path tracking prevents loops
3. **Same-domain only**: external links are never clicked
4. **Link quality**: login/admin/cart/download links are skipped
5. **Dead-end recovery**: `page.go_back()` works when no unvisited links found
6. **Session time respected**: explorer stops when session timer expires
7. **Ad interaction works**: ads are detected and clicked during page activity (same as sequential)
8. **process_ads_tabs works**: ad tabs are processed after explorer session ends
9. **Sequential mode unaffected**: when explorer is disabled, existing sequential behavior works identically (minus `random_page` removal)
10. **GUI toggles correctly**: explorer checkbox shows/hides appropriate controls
11. **Backward compat**: old config.json without `explorer` key loads correctly with defaults
12. **All navigation uses SmartClick**: no `page.goto()` for page-to-page transitions (except gate URL initial load via referrer)
