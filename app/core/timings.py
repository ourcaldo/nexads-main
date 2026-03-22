"""
app/core/timings.py
Centralized timing configuration — every delay/pause value in one place.

All values are in milliseconds. Use timing_ms() for wait_for_timeout and
timing_seconds() for asyncio.sleep.
"""

import math
import random

# fmt: off
TIMINGS = {
    # --- Page Navigation ---
    "page_settle":        {"min": 3000,  "max": 10000},  # After page load, before interaction
    "nav_post_click":     {"min": 2000,  "max": 4000},   # After clicking a navigation link
    "nav_scroll_step":    {"min": 300,   "max": 800},    # Between scroll-up steps during nav
    "nav_scroll_micro":   {"min": 50,    "max": 120},    # Scroll-to-top micro steps
    "nav_scroll_gap":     {"min": 300,   "max": 700},    # Gap after scroll-to-top sequence
    "nav_click_settle":   {"min": 500,   "max": 1500},   # After clicking link, wait for response
    "nav_retry":          {"min": 2000,  "max": 2000},   # Wait before retrying failed nav
    "nav_load_check":     {"min": 500,   "max": 500},    # Load state check wait

    # --- Activity Loop ---
    "activity_gap":       {"min": 700,   "max": 4800},   # Between activities (scroll/hover/click)
    "activity_backoff":   {"min": 500,   "max": 2400},   # Backoff when no activities available
    "read_pause":         {"min": 3000,  "max": 10000},  # Simulated reading pause
    "jitter_pause":       {"min": 800,   "max": 4200},   # Idle mouse jitter interval

    # --- Scroll ---
    "scroll_step":        {"min": 80,    "max": 450},    # Between scroll wheel steps (ms)
    "scroll_correction":  {"min": 55,    "max": 240},    # Scroll micro-correction delay (ms)

    # --- Hover ---
    "hover_dwell":        {"min": 350,   "max": 3400},   # How long to hover on elements

    # --- Click ---
    "click_settle":       {"min": 350,   "max": 2800},   # Post-click settle time
    "click_dwell":        {"min": 160,   "max": 820},    # Pause before clicking
    "click_delay":        {"min": 45,    "max": 240},    # Mousedown-to-mouseup gap

    # --- Ad Interaction ---
    "ad_notice":          {"min": 200,   "max": 800},    # "Noticing" ad hover before reading
    "ad_read_hover":      {"min": 300,   "max": 1400},   # "Reading" ad content hover
    "ad_scan_hover":      {"min": 150,   "max": 600},    # Scanning ad second point
    "ad_retry":           {"min": 350,   "max": 2000},   # Between ad detection retries
    "ad_poll":            {"min": 350,   "max": 350},    # Ad outcome polling interval
    "ad_tail":            {"min": 1000,  "max": 3000},   # Post-navigation redirect settle
    "ad_vignette":        {"min": 1200,  "max": 3200},   # Vignette dismiss delay

    # --- Tab Management ---
    "tab_wait":           {"min": 1000,  "max": 1200},   # Tab operations wait
    "tab_dwell":          {"min": 5000,  "max": 15000},  # Non-ad tab browse time
    "tab_idle":           {"min": 700,   "max": 3800},   # Between tab activities
    "tab_close_gap":      {"min": 1000,  "max": 2000},   # Between closing tabs

    # --- Natural Exit ---
    "exit_read":          {"min": 1200,  "max": 6000},   # Read-and-leave pause
    "exit_scroll_pre":    {"min": 1000,  "max": 5500},   # Before exit scroll
    "exit_scroll_post":   {"min": 500,   "max": 3000},   # After exit scroll
    "exit_cursor":        {"min": 1200,  "max": 7000},   # Moving cursor to close area
    "exit_hesitation":    {"min": 500,   "max": 3000},   # Final hesitation before exit

    # --- Social Platform Visit ---
    "social_settle":      {"min": 600,   "max": 2200},   # After social page load
    "social_scroll_gap":  {"min": 200,   "max": 900},    # Between social scrolls

    # --- Referrer Navigation ---
    "referrer_settle":    {"min": 1500,  "max": 3000},   # After referrer navigation

    # --- Consent Handling ---
    "consent_pre":        {"min": 45,    "max": 220},    # Before finding consent buttons
    "consent_hover":      {"min": 90,    "max": 360},    # Mouse move to consent button
    "consent_post":       {"min": 150,   "max": 700},    # After consent button click
    "consent_settle":     {"min": 180,   "max": 900},    # Post-dismiss settle
    "consent_action":     {"min": 350,   "max": 400},    # Accept/reject wait
    "consent_retry":      {"min": 100,   "max": 800},    # Between retry checks

    # --- Google Warm-up ---
    "warmup_typing":      {"min": 35,    "max": 220},    # Per-character typing delay (fallback)
    "warmup_result_wait": {"min": 350,   "max": 2200},   # Wait before clicking search result
    "warmup_click":       {"min": 35,    "max": 220},    # Click delay on results
    "warmup_page_dwell":  {"min": 1300,  "max": 3200},   # Time on visited warm-up page
    "warmup_scroll_gap":  {"min": 200,   "max": 800},    # Between warm-up scrolls
    "warmup_settle":      {"min": 250,   "max": 900},    # General warm-up settle
    "warmup_retry":       {"min": 1000,  "max": 1000},   # Wait for search to settle

    # --- Worker / Session ---
    "worker_stagger":     {"min": 2000,  "max": 5000},   # Stagger between worker starts
    "browser_retry":      {"min": 10000, "max": 10000},  # Browser init failure retry wait
    "session_retry":      {"min": 1000,  "max": 1000},   # Between session loop retries
    "session_activity":   {"min": 400,   "max": 2800},   # Session-level activity gap
    "session_success":    {"min": 10000, "max": 30000},   # Wait after successful session
    "session_failure":    {"min": 30000, "max": 60000},   # Wait after failed session
    "failure_cooldown":   {"min": 120000,"max": 120000},  # Cooldown after consecutive failures
}
# fmt: on


def _lognormal_clamped(median: float, sigma: float,
                       min_val: float, max_val: float) -> float:
    """Generate a lognormal random value clamped to [min_val, max_val]."""
    if min_val >= max_val:
        return min_val
    mu = math.log(max(median, 0.01))
    value = random.lognormvariate(mu, sigma)
    return max(min_val, min(max_val, value))


def timing_ms(key: str) -> int:
    """Return a randomized timing value in milliseconds from TIMINGS."""
    t = TIMINGS[key]
    mn, mx = t["min"], t["max"]
    if mn >= mx:
        return mn
    median = math.sqrt(mn * mx)  # geometric mean — natural for lognormal
    return int(round(_lognormal_clamped(median, 0.4, mn, mx)))


def timing_seconds(key: str) -> float:
    """Return a randomized timing value in seconds from TIMINGS."""
    return timing_ms(key) / 1000.0
