# Browser Detection Issues

This document tracks all browser detection issues encountered and solutions attempted.

## Overview

The browser automation system uses:
- **Playwright** with **playwright-stealth** for mobile sessions
- **Camoufox** for desktop sessions
- Proxy rotation for traffic generation
- BrowserForge for fingerprint generation

---

## Issue 1: Different Time Zones

**Detection Score:** -10%

**Description:** The website detects that the browser's timezone doesn't match the proxy's timezone (or local machine timezone).

### Root Cause
- Playwright contexts don't automatically set timezone from geoip data
- The timezone needs to be explicitly set in context options

### Attempts to Fix

1. **Added GeoIP Lookup Module** (`app/browser/geoip.py`)
   - Fetches timezone from proxy IP
   - Returns timezone string like "Europe/Vienna"

2. **Updated Context Options** in `configure_browser()`:
   ```python
   if geoip_data.get("timezone"):
       context_opts["timezone_id"] = geoip_data["timezone"]
   ```

3. **Added JavaScript Injection** in stealth script:
   ```javascript
   if (geoip && geoip.timezone) {
       // Override Date.prototype methods
   }
   ```

**Status:** ❌ Not Fully Resolved
- The timezone may not be properly applied to Playwright context
- Need to verify `timezone_id` context option works in mobile mode

---

## Issue 2: Language Mismatch

**Detection Score:** -10%

**Description:** The browser's language/locale doesn't match the proxy's country.

### Root Cause
- Default navigator.language is "en" or machine locale
- Need to override Accept-Language headers and navigator.languages

### Attempts to Fix

1. **Updated Context Options:**
   ```python
   if geoip_data.get("locale"):
       context_opts["locale"] = geoip_data["locale"]
   context_opts["extra_http_headers"]["Accept-Language"] = accept_lang
   ```

2. **Added JavaScript Override:**
   ```javascript
   if (geoip && geoip.locale) {
       defineGetter(navigator, 'language', geoip.locale.split('-')[0]);
       defineGetter(navigator, 'languages', [geoip.locale, geoip.locale.split('-')[0], 'en']);
   }
   ```

3. **playwright-stealth Configuration:**
   ```python
   stealth_kwargs = {
       "navigator_languages_override": locale_override,
   }
   ```

**Status:** ❌ Not Fully Resolved
- Need to verify locale is properly set in Playwright context

---

## Issue 3: Bot Control

**Detection Score:** -5%

**Description:** Browser environment appears to be controlled by a robot.

### Root Cause
- Multiple automation signals that need to be hidden:
  - `navigator.webdriver = true`
  - Chrome runtime variables
  - CDP automation flags

### Attempts to Fix

1. **playwright-stealth Integration:**
   ```python
   stealth = Stealth()
   stealth_manager = stealth.use_async(async_playwright())
   pw = await stealth_manager.__aenter__()
   ```

2. **Added Stealth Evasion Scripts:**
   ```javascript
   // Hide webdriver
   Object.defineProperty(navigator, 'webdriver', {
       get: () => undefined,
       configurable: true
   });
   
   // Remove CDP automation flags
   delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
   delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
   delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
   
   // Override chrome.runtime
   Object.defineProperty(chrome, 'runtime', {
       get: () => undefined,
       configurable: true
   });
   ```

**Status:** ⚠️ Partially Resolved
- Most automation signals hidden
- Some detection methods may still be catching browser

---

## Issue 4: WebGL Exception

**Detection Score:** -5%

**Description:** WebGL fingerprint doesn't match expected values.

### Root Cause
- Headless browsers use SwiftShader GPU
- WebGL vendor/renderer shows "Google" or "SwiftShader"

### Attempts to Fix

1. **Added WebGL Spoofing in Injection Script:**
   ```javascript
   if (videoCard.vendor || videoCard.renderer) {
       const getParameter = WebGLRenderingContext.prototype.getParameter;
       WebGLRenderingContext.prototype.getParameter = function(parameter) {
           if (parameter === 37445 && videoCard.vendor) return videoCard.vendor;
           if (parameter === 37446 && videoCard.renderer) return videoCard.renderer;
           return getParameter.call(this, parameter);
       };
   }
   ```

2. **BrowserForge Fingerprint Injection:**
   - Mobile fingerprint includes videoCard data with vendor/renderer
   - Values injected via `defineGetter`

**Status:** ⚠️ Partially Resolved
- WebGL spoofing depends on BrowserForge fingerprint data
- May need additional hardening

---

## Issue 5: IP Addresses Different

**Detection Score:** -10%

**Description:** Browser IP doesn't match real machine IP (using proxy).

### Root Cause
- Using proxy server - IP is intentionally different

**Status:** ✅ Expected Behavior
- Cannot fix - using proxy is intentional
- Detection is correct (proxy IP != real IP)

---

## Issue 6: DNS Leak

**Detection Score:** -3%

**Description:** DNS server may leak websites visited.

### Root Cause
- DNS requests may go through machine's default DNS, not proxy

### Attempts to Fix

1. **Proxy Configuration** - DNS should route through proxy
2. **Browser Arguments:**
   ```python
   "--disable-web-security",
   ```

**Status:** ⚠️ Depends on Proxy Provider
- Quality of proxy determines DNS handling
- Some proxies route all traffic, others don't

---

## Issue 7: Different Browser Version

**Detection Score:** -5%

**Description:** UserAgent shows different browser version than actual.

### Root Cause
- Mobile fingerprint has specific UserAgent
- UserAgent spoofing is intentional for fingerprint

### Attempts to Fix

1. **BrowserForge Fingerprint Generation:**
   - Generates realistic mobile UserAgent
   - Includes Chrome version matching fingerprint

2. **Context Options:**
   ```python
   context_opts["user_agent"] = fingerprint["headers"]["User-Agent"]
   ```

**Status:** ✅ Expected Behavior
- UserAgent spoofing is intentional for fingerprint consistency
- Detection is expected with mobile fingerprints

---

## Issue 8: UserAgent Different

**Detection Score:** -10%

**Description:** UserAgent doesn't match expected value.

### Root Cause
- Same as Issue 7 - intentional spoofing

### Attempts to Fix

Same as Issue 7.

**Status:** ✅ Expected Behavior
- Mobile fingerprints have specific UserAgents

---

## Issue 9: Incognito Mode

**Detection Score:** -10%

**Description:** Browser appears to be in incognito/private mode.

### Root Cause
- Playwright contexts are always created fresh
- Storage APIs behave like incognito
- localStorage may be empty or throw errors

### Attempts to Fix

1. **Added Extensive Incognito Detection Evasion:**
   ```javascript
   // Make storage APIs appear to work normally
   try {
       if (typeof localStorage === 'undefined') {
           const mockStorage = {};
           Object.defineProperty(window, 'localStorage', {
               get: () => mockStorage,
               configurable: true
           });
       }
       
       const origSetItem = Storage.prototype.setItem;
       Storage.prototype.setItem = function(key, value) {
           try { origSetItem.call(this, key, value); } catch(e) {}
       };
   } catch(e) {}
   
   // Fake navigator.storage
   if (navigator.storage && navigator.storage.estimate) {
       const origEstimate = navigator.storage.estimate.bind(navigator.storage);
       navigator.storage.estimate = async () => {
           const result = await origEstimate();
           return {
               ...result,
               usage: result.usage || 1024 * 1024 * 5,
               quota: result.quota || 1024 * 1024 * 100
           };
       };
   }
   
   // Fake navigator.cookieEnabled
   defineGetter(navigator, 'cookieEnabled', true);
   
   // Fake WebSQL
   if (typeof window.openDatabase !== 'undefined') {
       window.openDatabase = (name, version, displayName, estimatedSize, callback) => {
           return { transaction: () => {} };
       };
   }
   
   // Override indexedDB
   if (typeof indexedDB === 'undefined') {
       window.indexedDB = {
           open: () => ({ result: null, onsuccess: null, onerror: null }),
           deleteDatabase: () => ({}),
           cmp: () => 0
       };
   }
   
   // Fake permissions for storage-access
   if (navigator.permissions && navigator.permissions.query) {
       const origQuery = navigator.permissions.query.bind(navigator.permissions);
       navigator.permissions.query = (params) => {
           if (params.name === 'storage-access') {
               return Promise.resolve({ state: 'granted' });
           }
           return origQuery(params);
       };
   }
   ```

2. **playwright-stealth Integration:**
   - playwright-stealth has built-in incognito evasion

**Status:** ❌ Not Fully Resolved
- Detection systems may use additional methods
- Playwright's context creation inherently looks like incognito

---

## Summary of Detection Scores

| Issue | Score | Status | Fixable? |
|-------|-------|--------|----------|
| Time Zones | -10% | ❌ | Partially |
| Language Mismatch | -10% | ❌ | Partially |
| Bot Control | -5% | ⚠️ | Partially |
| WebGL Exception | -5% | ⚠️ | Partially |
| IP Different | -10% | ✅ | No (expected) |
| DNS Leak | -3% | ⚠️ | Depends on proxy |
| Browser Version | -5% | ✅ | No (expected) |
| UserAgent Different | -10% | ✅ | No (expected) |
| Incognito Mode | -10% | ❌ | Difficult |

**Total Potential Score:** -68% (excluding expected items: -43%)

---

## Technical Solutions in Use

### 1. playwright-stealth
Python package that applies 20+ stealth evasions:
- navigator.webdriver → false
- chrome.runtime → undefined
- navigator.plugins → populated with fake plugins
- navigator.languages → spoofed
- window.outer* / inner* → spoofed
- WebGL vendor/renderer → spoofed
- Permissions API → spoofed
- Media devices → spoofed
- Speech synthesis → spoofed

### 2. BrowserForge Fingerprints
Mobile fingerprint generation with:
- Realistic UserAgent for Chrome/Android
- Screen dimensions matching mobile
- Navigator properties
- WebGL GPU info
- Battery API data
- Media devices

### 3. GeoIP Integration
- Fetches proxy IP location
- Returns timezone, locale, language
- Applied to context options and JS injection

### 4. Custom Stealth Scripts
Additional JavaScript injected via `page.addInitScript()`:
- CDP variable cleanup
- Storage API normalization
- Incognito evasion
- Permissions spoofing

---

## Known Limitations

1. **Playwright Context Architecture**
   - Playwright creates fresh contexts by design
   - Cannot fully mimic persistent browser profile

2. **BrowserLeaks Detection**
   - sites like browserLeaks.com use advanced fingerprinting
   - Some signals cannot be spoofed at JS level

3. **Proxy-Dependent Issues**
   - DNS leak depends on proxy provider
   - IP location must match geoip data

4. **Headless Mode**
   - Running headless may introduce additional signals
   - Real browser (headful) would be less detectable

---

## Recommendations

### High Priority
1. Verify timezone_id is properly applied to Playwright context
2. Verify locale/language is properly set
3. Test with headful mode (headless=False)

### Medium Priority
1. Add more WebGL spoofing
2. Test with different proxy providers
3. Consider using persistent contexts

### Low Priority
1. Custom WebGL renderer implementation
2. Hardware fingerprint randomization
3. Canvas fingerprint evasion

---

## Testing Sites

- https://www.browserscan.net/
- https://browserleaks.com/
- https://pixelscan.net/
- https://iphey.com/

---

## Files Modified

- `app/browser/setup.py` - Browser configuration, stealth integration
- `app/browser/geoip.py` - GeoIP lookup module
- `app/browser/activities.py` - Activity spoofing
- `app/core/worker.py` - Stealth application to contexts
- `requirements.txt` - Added playwright-stealth, aiohttp
