# Known Issues

## 🔴 Bug #1 — `ensure_correct_tab` inverted logic
**File:** `main.py`
**Line:** ~684

The two conditions cancel each other out. When `target_page` is not found, the function returns early with the current page as if it succeeded — meaning the tab-checking logic never actually corrects anything.

```python
if not target_page:
    return page, True  # ← returns early, doing nothing

if target_page:  # ← unreachable when target_page is None
    ...
```

---

## 🔴 Bug #2 — `random_hover` mouse always starts from `(0,0)`
**File:** `main.py`
**Line:** ~1362

The intermediate mouse positions are calculated as a fraction of the **target coordinate only**, meaning the movement always originates from the top-left corner of the screen instead of the mouse's current position. This is obviously non-human behavior.

```python
current_x = int(target_x * frac)  # frac near 0 → always near (0,0)
current_y = int(target_y * frac)
```

**Fix:** Interpolate from the current mouse position to the target, not from `(0,0)`.

---

## 🔴 Bug #3 — `add_cursor_trail` injects a visible red dot on every page
**File:** `main.py`
**Line:** ~1113

A debug artifact that injects a bright red 10px dot cursor trail into every visited page via JavaScript. This is visible to the site and could expose the automation to bot detection.

```python
background-color: red;  /* Color */
```

**Fix:** Remove the cursor trail injection entirely, or at minimum remove the visible styling.

---

## 🔴 Bug #4 — `self.workers` has no `.session_count` attribute
**File:** `main.py`
**Line:** ~1510

`self.workers` holds `multiprocessing.Process` objects, which have no `.session_count` attribute. This will raise an `AttributeError` at runtime when determining the session index.

```python
session_index = sum([w.session_count for w in self.workers])  # AttributeError!
```

**Fix:** Track session counts separately (e.g. via a shared `multiprocessing.Value` or `Manager` dict) instead of reading from the Process objects directly.
