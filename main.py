import sys
import json
import random
import asyncio
import multiprocessing
import time
import aiohttp
from datetime import datetime, timedelta
from argparse import ArgumentParser
from PyQt5.QtWidgets import QApplication
from camoufox.async_api import AsyncCamoufox
from camoufox import DefaultAddons
from browserforge.fingerprints import Screen
from ui import ConfigWindow

# Global variable for config path
CONFIG_PATH = 'config.json'

class SessionFailedException(Exception):
    """Custom exception to mark a session as failed"""
    pass

class RateLimiter:
    """Class to handle API rate limiting"""
    def __init__(self, max_calls_per_minute=300):
        self.max_calls = max_calls_per_minute
        self.calls = []
        self.lock = asyncio.Lock()
    
    async def wait_if_needed(self):
        async with self.lock:
            now = time.time()
            # Remove calls older than 1 minute
            self.calls = [t for t in self.calls if now - t < 60]
            
            if len(self.calls) >= self.max_calls:
                oldest_call = self.calls[0]
                wait_time = 60 - (now - oldest_call)
                if wait_time > 0:
                    print(f"Rate limit reached, waiting {wait_time:.2f} seconds")
                    await asyncio.sleep(wait_time)
            
            self.calls.append(time.time())

class nexAds:
    def __init__(self, config_path='config.json'):
        """Initialize the nexAds automation tool."""
        self.config_path = config_path
        self.load_config()
        self.workers = []
        self.running = False
        self.session_counts = {}
        self.successful_sessions = {}
        self.ads_session_counts = {}
        self.successful_ads_sessions = {}
        self.start_time = None
        self.total_sessions = 0
        self.ads_sessions = 0
        self.calculate_session_distribution()
        self.failed_ads_sessions = 0
        self.pending_ads_sessions = 0
        self._ad_click_success = {}
        self.lock = multiprocessing.Lock()
        # Create manager for shared state
        self.manager = multiprocessing.Manager()
        self.rate_limiter = RateLimiter()
        
    def calculate_session_distribution(self):
        """Calculate how many sessions should include ad interactions based on CTR."""
        if not self.config['session']['enabled'] or self.config['session']['count'] == 0:
            threads = self.config['threads']
            max_time_min = self.config['session']['max_time']
            if max_time_min > 0:
                sessions_per_hour_per_thread = 60 / max_time_min
                self.total_sessions = int(threads * sessions_per_hour_per_thread)
            else:
                self.total_sessions = 100
        else:
            self.total_sessions = self.config['threads'] * self.config['session']['count']
        self.ads_sessions = max(1, int(self.total_sessions * (self.config['ads']['ctr'] / 100)))
        self.pending_ads_sessions = self.ads_sessions
        self.ads_session_flags = [False] * self.total_sessions
        for i in random.sample(range(self.total_sessions), min(self.ads_sessions, self.total_sessions)):
            self.ads_session_flags[i] = True
            
    def load_config(self):
        """Load configuration from JSON file."""
        try:
            with open(self.config_path, 'r') as f:
                self.config = json.load(f)
            if "type" in self.config["referrer"]:
                old_type = self.config["referrer"]["type"]
                if old_type == "random":
                    self.config["referrer"]["types"] = ["random"]
                else:
                    self.config["referrer"]["types"] = [old_type]
                del self.config["referrer"]["type"]
            # Validate proxy settings
            if self.config['proxy']['credentials'] and self.config['proxy']['file']:
                print("Warning: Both proxy credentials and file are specified. Using credentials and ignoring file.")
                self.config['proxy']['file'] = ""
        except FileNotFoundError:
            print(f"Config file {self.config_path} not found. Please create one using the --config option.")
            sys.exit(1)
        except json.JSONDecodeError:
            print(f"Invalid config file {self.config_path}. Please check the file or create a new one with --config.")
            sys.exit(1)
            
    def get_random_delay(self, min_time=None, max_time=None):
        """Generate a random delay between min and max time."""
        min_val = min_time if min_time is not None else self.config['delay']['min_time']
        max_val = max_time if max_time is not None else self.config['delay']['max_time']
        return random.randint(min_val, max_val)
        
    async def configure_browser(self, worker_id):
        """Configure and return a new browser instance with current settings."""
        try:
            proxy = None
            if self.config['proxy']['credentials']:
                proxy = self.config['proxy']['credentials']
            elif self.config['proxy']['file']:
                with open(self.config['proxy']['file'], 'r') as f:
                    proxies = [line.strip() for line in f if line.strip()]
                if proxies:
                    proxy = random.choice(proxies)

            headless = True
            if self.config['browser']['headless_mode'] == 'False':
                headless = False
            elif self.config['browser']['headless_mode'] == 'virtual':
                headless = 'virtual'

            os_fingerprint = random.choice(self.config['os_fingerprint'])

            device_type = random.choices(
                ['mobile', 'desktop'],
                weights=[
                    self.config['device_type']['mobile'],
                    self.config['device_type']['desktop']
                ],
                k=1
            )[0]

            screen = Screen(max_width=2800, max_height=2080) if device_type == 'mobile' \
                    else Screen(max_width=7680, max_height=4320)

            options = {
                'headless': headless,
                'os': os_fingerprint,
                'screen': screen,
                'geoip': True,
                'humanize': True
            }

            if self.config['browser']['disable_ublock']:
                options['exclude_addons'] = [DefaultAddons.UBO]

            if proxy:
                proxy_type = self.config['proxy']['type'].lower()
                if '@' in proxy:
                    auth, server = proxy.split('@')
                    user, pwd = auth.split(':')
                    host, port = server.split(':')
                    options['proxy'] = {
                        'server': f"{proxy_type}://{host}:{port}",
                        'username': user,
                        'password': pwd
                    }
                else:
                    host, port = proxy.split(':')
                    options['proxy'] = {
                        'server': f"{proxy_type}://{host}:{port}",
                        'username': None,
                        'password': None
                    }

            # Create and start the browser instance
            browser = await AsyncCamoufox(**options).start()
            delay = self.get_random_delay()
            await asyncio.sleep(delay)
            return browser

        except Exception as e:
            print(f"Worker {worker_id}: Browser initialization error: {str(e)}")
            return None
                
    async def cleanup_browser(self, browser, worker_id):
        """Clean up browser resources."""
        try:
            if not browser:
                return

            # Close all contexts
            for context in browser.contexts:
                try:
                    await context.close()
                except:
                    pass

            # Close browser
            try:
                await browser.close()
            except:
                pass

        except Exception as e:
            print(f"Worker {worker_id}: Error during browser cleanup: {str(e)}")
                
    async def setup_request_interceptor(self, page):
        """Set up request interceptor to block Google login pages."""
        await page.route("**/*", lambda route: route.abort() if "accounts.google.com" in route.request.url else route.continue_())
            
    async def accept_google_cookies(self, page):
        """Auto accept Google cookies if the popup is present."""
        try:
            accept_selectors = [
                "button:has-text('Accept all'), button:has-text('I agree'), button:has-text('Accept')",
                "button#L2AGLb",
                "div[role='dialog'] button:has-text('Accept')"
            ]
            for selector in accept_selectors:
                try:
                    accept_button = await page.query_selector(selector)
                    if accept_button and await accept_button.is_visible():
                        await accept_button.click(timeout=7500)
                        print("Accepted Google cookies")
                        return True
                except:
                    continue
            return False
        except Exception as e:
            print(f"Error accepting cookies: {str(e)}")
            return False
        
    async def handle_gdpr_consent(self, page, worker_id):
        """
        Handle GDPR consent popup if present on the page.
        Looks for specific elements and clicks the Consent button.
        Returns True if GDPR popup was found and handled, False otherwise.
        """
        try:
            # Check for GDPR dialog container with multiple possible selectors
            gdpr_selectors = [
                'div.fc-dialog-container',
                'div[class*="cookie"]',
                'div[class*="consent"]',
                'div[class*="gdpr"]',
                'div[class*="privacy"]'
            ]
            
            for selector in gdpr_selectors:
                try:
                    gdpr_dialog = await page.query_selector(selector)
                    if gdpr_dialog and await gdpr_dialog.is_visible():
                        print(f"Worker {worker_id}: GDPR consent dialog detected")
                        break
                    gdpr_dialog = None
                except:
                    continue
            
            if not gdpr_dialog:
                return False
                
            # Look for the consent button with multiple possible selectors
            consent_selectors = [
                'p.fc-button-label:has-text("Consent")',
                'button:has-text("Consent")',
                'button:has-text("Accept")',
                'button:has-text("Agree")',
                'button:has-text("I agree")',
                'button#accept-cookies',
                'button#consent-button'
            ]
            
            consent_button = None
            for selector in consent_selectors:
                try:
                    consent_button = await page.query_selector(selector)
                    if consent_button and await consent_button.is_visible():
                        break
                    consent_button = None
                except:
                    continue
            
            if not consent_button:
                print(f"Worker {worker_id}: GDPR dialog found but no consent button detected")
                return False
                
            # Scroll to the button if needed
            await consent_button.scroll_into_view_if_needed()
            
            # Get button position
            box = await consent_button.bounding_box()
            if not box:
                return False
            
            # Human-like movement to the button
            await page.mouse.move(
                box['x'] + box['width'] / 2,
                box['y'] + box['height'] / 2,
                steps=random.randint(5, 10)
            )
            
            # Small delay before click
            await page.wait_for_timeout(random.randint(300, 800))
            
            # Click the button
            await consent_button.click(delay=random.randint(50, 200))
            print(f"Worker {worker_id}: Clicked GDPR consent button")
            
            # Wait for dialog to disappear
            try:
                await page.wait_for_selector(selector, state='hidden', timeout=5000)
            except:
                pass
                
            return True
                
        except Exception as e:
            print(f"Worker {worker_id}: Error handling GDPR consent: {str(e)}")
            return False
            
    def get_random_keyword(self):
        """Get a keyword from the organic keywords list - handles all formats."""
        if "organic" not in self.config['referrer']['types']:
            return None
            
        # Get the raw keyword data
        keywords = self.config['referrer']['organic_keywords']
        
        # Handle all cases:
        # 1. If it's already a list, use it directly
        if isinstance(keywords, list):
            valid_keywords = [k.strip() for k in keywords if k and str(k).strip()]
        
        # 2. If it's a string, split by either commas or newlines
        elif isinstance(keywords, str):
            # Replace newlines with commas, then split
            keyword_str = keywords.replace('\n', ',').strip()
            valid_keywords = [k.strip() for k in keyword_str.split(',') if k.strip()]
        
        # 3. If it's some other type (number, etc.), convert to string
        else:
            valid_keywords = [str(keywords).strip()] if str(keywords).strip() else []
        
        # If we have exactly one keyword, just return it
        if len(valid_keywords) == 1:
            return valid_keywords[0]
        
        # If multiple keywords, return a random one
        if valid_keywords:
            return random.choice(valid_keywords)
        
        # If no valid keywords found
        print(f"DEBUG - Raw keyword data: {repr(keywords)}")  # Debug output
        return None
        
    async def perform_organic_search(self, page, keyword, target_domain, worker_id):
        """Perform organic search flow focusing only on main domain matching."""
        max_retries = 3
        retry_count = 0
        # Extract just the main domain (without www)
        main_domain = target_domain.replace('www.', '').split('/')[0]
        # Set up request interceptor to block Google login pages
        await self.setup_request_interceptor(page)
        
        while retry_count < max_retries:
            try:
                print(f"Worker {worker_id}: Performing organic search - visiting Google")
                await page.goto("https://www.google.com/ ", timeout=90000, wait_until="networkidle")
                if self.config['browser']['auto_accept_cookies']:
                    await self.accept_google_cookies(page)
                    
                print(f"Worker {worker_id}: Searching for keyword: {keyword}")
                search_input = await page.wait_for_selector('textarea[name="q"], input[name="q"]', 
                                                    state="visible", timeout=45000)
                
                if not search_input:
                    print(f"Worker {worker_id}: Could not find search input")
                    return False
                    
                # Clear input and type keyword
                await search_input.click(click_count=3)
                await search_input.press("Backspace")
                
                for char in keyword:
                    await search_input.press(char)
                    await page.wait_for_timeout(random.randint(50, 150))
                    
                await search_input.press("Enter")
                await page.wait_for_load_state("networkidle", timeout=45000)
                print(f"Worker {worker_id}: Looking for {main_domain} in results")
                
                # Wait for search results to load
                await page.wait_for_selector('div#search', state="visible", timeout=45000)
                
                # Find all visible result links
                all_links = await page.query_selector_all('a[href]:visible')
                if not all_links:
                    print(f"Worker {worker_id}: No links found in search results")
                    return False
                    
                # Find the first link that matches our main domain
                target_link = None
                for link in all_links:
                    try:
                        href = await link.get_attribute('href')
                        if href and main_domain in self.extract_domain(href):
                            target_link = link
                            break
                    except:
                        continue
                        
                if not target_link:
                    print(f"Worker {worker_id}: No links found matching main domain")
                    return False
                    
                # Scroll to the link
                await target_link.scroll_into_view_if_needed()
                await page.wait_for_timeout(random.randint(500, 1500))
                
                # Click the link
                async with page.expect_navigation(timeout=45000) as nav:
                    await target_link.click(delay=random.randint(50, 200))
                    
                # Wait for page to load
                await page.wait_for_load_state("networkidle", timeout=45000)
                
                # Verify we're on the correct domain
                current_main_domain = self.extract_domain(page.url).replace('www.', '')
                if main_domain not in current_main_domain:
                    print(f"Worker {worker_id}: Navigation failed. Current domain: {current_main_domain}, Expected: {main_domain}")
                    await page.go_back(timeout=45000)
                    await page.wait_for_load_state("networkidle")
                    retry_count += 1
                    continue
                    
                print(f"Worker {worker_id}: Successfully navigated to domain: {page.url}")
                return True
                
            except Exception as e:
                print(f"Worker {worker_id}: Organic search error (attempt {retry_count + 1}): {str(e)}")
                retry_count += 1
                if retry_count < max_retries:
                    await page.wait_for_timeout(2000)
                continue
                
        print(f"Worker {worker_id}: Max retries reached for organic search")
        return False
        
    def extract_domain(self, url):
        """Extract domain from URL."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc
        
    async def navigate_to_url_by_click(self, page, target_url, worker_id):
        """Navigate to target URL by finding and clicking a link on the current page."""
        target_domain = self.extract_domain(target_url)
        max_retries = 2
        retry_count = 0

        while retry_count < max_retries:
            try:
                # Ensure correct tab
                page, success = await self.ensure_correct_tab(page.context.browser, page, target_url, worker_id)
                if not success:
                    print(f"Worker {worker_id}: Could not ensure correct tab for navigation")
                    retry_count += 1
                    continue

                print(f"Worker {worker_id}: Scanning page for links to {target_domain}")

                all_links = await page.query_selector_all('a[href]:visible')
                if not all_links:
                    print(f"Worker {worker_id}: No visible links found on page")
                    retry_count += 1
                    continue

                matching_links = []
                for link in all_links:
                    try:
                        href = await link.get_attribute('href')
                        if href and target_url in href:
                            matching_links.append((link, 'exact'))
                        elif href and target_domain in href:
                            matching_links.append((link, 'domain'))
                    except:
                        continue

                matching_links.sort(key=lambda x: 0 if x[1] == 'exact' else 1)

                for link, match_type in matching_links:
                    try:
                        # --- Safe Scroll With DOM Check ---
                        scroll_success = False
                        scroll_attempts = 0

                        while scroll_attempts < 3 and not scroll_success:
                            try:
                                attached = await page.evaluate(
                                    "(el) => el && el.isConnected", link
                                )
                                if not attached:
                                    raise Exception("Element is not attached to the DOM")

                                await link.scroll_into_view_if_needed(timeout=22500)
                                scroll_success = True
                            except Exception as e:
                                scroll_attempts += 1
                                if scroll_attempts == 3:
                                    print(f"Worker {worker_id}: Scroll failed after 3 attempts")
                                    raise
                                await asyncio.sleep(1)

                        await page.wait_for_timeout(random.randint(500, 1500))

                        # Use smart_click to handle the click
                        current_domain = self.extract_domain(page.url)
                        if await self.smart_click(page, worker_id, current_domain, link):
                            await page.wait_for_load_state("networkidle", timeout=45000)
                            print(f"Worker {worker_id}: Successfully clicked {match_type} match")

                            if self.config['browser']['auto_accept_cookies']:
                                await self.accept_google_cookies(page)

                            await self.check_and_handle_vignette(page, worker_id)

                            return True

                    except Exception as e:
                        print(f"Worker {worker_id}: Link click failed: {str(e)}")
                        continue

                print(f"Worker {worker_id}: No matching links found, trying random navigation")
                random_nav_success = await self.random_navigation(page, worker_id, target_domain)
                if random_nav_success:
                    return True

            except Exception as e:
                print(f"Worker {worker_id}: Error during URL click navigation: {str(e)}")
                retry_count += 1
                if retry_count < max_retries:
                    await asyncio.sleep(2)
                continue

        print(f"Worker {worker_id}: Failed to navigate to {target_url} after {max_retries} attempts")
        raise SessionFailedException(f"Failed to navigate to {target_url}")

    async def random_navigation(self, page, worker_id, target_domain=None):
        """Perform random navigation by clicking a link on the page."""
        max_retries = 2  # Maximum retries for the entire operation
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Ensure correct tab
                current_url = page.url
                page, success = await self.ensure_correct_tab(page.context.browser, page, current_url, worker_id)
                if not success:
                    print(f"Worker {worker_id}: Could not ensure correct tab for random navigation")
                    retry_count += 1
                    continue
                    
                print(f"Worker {worker_id}: Attempting random navigation")
                
                # Get current URL before clicking
                original_url = page.url
                
                # Get all visible links on the page
                all_links = await page.query_selector_all('a[href]:visible')
                if not all_links:
                    print(f"Worker {worker_id}: No visible links found for random navigation")
                    retry_count += 1
                    continue
                    
                # Filter links by domain if specified
                if target_domain:
                    domain_links = []
                    for link in all_links:
                        try:
                            href = await link.get_attribute('href')
                            if href and target_domain in href:
                                domain_links.append(link)
                        except:
                            continue
                            
                    if domain_links:
                        print(f"Worker {worker_id}: Found {len(domain_links)} links matching target domain")
                        all_links = domain_links
                    else:
                        print(f"Worker {worker_id}: No links matching target domain found")
                        
                # Select random link
                link = random.choice(all_links)
                
                # Scroll to the link with max 3 attempts
                scroll_success = False
                for attempt in range(3):
                    try:
                        await link.scroll_into_view_if_needed(timeout=22500)
                        scroll_success = True
                        break
                    except Exception as e:
                        print(f"Worker {worker_id}: Scroll attempt {attempt + 1} failed: {str(e)}")
                        if attempt == 2:
                            raise
                        await asyncio.sleep(1)
                
                if not scroll_success:
                    retry_count += 1
                    continue
                    
                await page.wait_for_timeout(random.randint(500, 1500))
                
                # Use smart_click to handle the click
                current_domain = self.extract_domain(page.url)
                if await self.smart_click(page, worker_id, current_domain, link):
                    # Wait for navigation
                    await page.wait_for_load_state("networkidle", timeout=45000)
                    
                    # Check cookies after navigation
                    if self.config['browser']['auto_accept_cookies']:
                        await self.accept_google_cookies(page)
                    
                    # Check vignette after navigation
                    await self.check_and_handle_vignette(page, worker_id)
                    
                    # Verify we actually navigated somewhere
                    if page.url != original_url:
                        print(f"Worker {worker_id}: Random navigation successful to {page.url}")
                        return True
                    else:
                        print(f"Worker {worker_id}: Random navigation did not change URL")
                        retry_count += 1
                        continue
                    
            except Exception as e:
                print(f"Worker {worker_id}: Error during random navigation: {str(e)}")
                retry_count += 1
                if retry_count < max_retries:
                    await asyncio.sleep(2)
                continue
                
        print(f"Worker {worker_id}: Max retries reached for random navigation")
        return False
            
    async def ensure_correct_tab(self, browser, page, target_url, worker_id, timeout=60):
        """
        Ensure the correct tab is focused before performing activities.
        If the correct tab isn't found, opens the target URL in current or new tab based on tab count.
        Returns the page object and success status.
        """
        # Check if redirect prevention is disabled in config
        if not self.config['browser'].get('prevent_redirects', True):
            return page, True
            
        start_time = time.time()
        attempts = 0
        target_domain = self.extract_domain(target_url)

        while time.time() - start_time < timeout:
            attempts += 1
            try:
                contexts = browser.contexts if hasattr(browser, 'contexts') else [browser]
                pages = []
                for context in contexts:
                    try:
                        pages.extend(context.pages)
                    except:
                        continue

                current_tab = page if page and not page.is_closed() else (pages[0] if pages else None)
                target_page = None

                for p in pages:
                    try:
                        if not p.is_closed() and target_domain in p.url:
                            target_page = p
                            break
                    except:
                        continue
                
                if not target_page:
                    return page, True  # Return current page if redirect prevention is off
                
                if target_page:
                    if current_tab and target_page != current_tab:
                        await target_page.bring_to_front()
                        try:
                            await target_page.wait_for_load_state("networkidle", timeout=5000)
                        except:
                            pass
                        print(f"Worker {worker_id}: Focused on existing tab with {target_url}")
                    return target_page, True

                # If target not found
                if len(pages) <= 1:
                    # Reuse current tab
                    if current_tab:
                        try:
                            await current_tab.goto(target_url, timeout=90000, wait_until="networkidle")
                            await current_tab.bring_to_front()
                            print(f"Worker {worker_id}: Opened target URL in current tab")
                            return current_tab, True
                        except Exception as e:
                            print(f"Worker {worker_id}: Error loading target URL in current tab: {e}")
                            return None, False
                else:
                    # Open new tab
                    context = contexts[0] if contexts else await browser.new_context()
                    try:
                        new_page = await context.new_page()
                        await new_page.goto(target_url, timeout=90000, wait_until="networkidle")
                        await new_page.bring_to_front()
                        print(f"Worker {worker_id}: Opened target URL in new tab")
                        return new_page, True
                    except Exception as e:
                        print(f"Worker {worker_id}: Failed to open new tab: {e}")
                        try:
                            if 'new_page' in locals() and not new_page.is_closed():
                                await new_page.close()
                        except:
                            pass

                await asyncio.sleep(1)
            except Exception as e:
                print(f"Worker {worker_id}: Unexpected error in ensure_correct_tab: {e}")
                await asyncio.sleep(1)

        print(f"Worker {worker_id}: Timeout ensuring correct tab for {target_url}")
        return None, False
        
    async def detect_adsense_ads(self, page):
        """Detect visible AdSense ads on the current page."""
        try:
            ad_selectors = [
                'ins.adsbygoogle',
                'ins[class*="adsbygoogle"]',
                'div[id*="google_ads"]',
                'div[data-ad-client]',
                'div[data-ad-slot]',
                'iframe[src*="googleads"]',
                'iframe[src*="doubleclick.net"]',
                'iframe[src*="adservice.google.com"]',
                'div[class*="adsense"]'
            ]
            visible_ads = []
            
            for selector in ad_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    for element in elements:
                        try:
                            if await element.is_visible():
                                box = await element.bounding_box()
                                if box and box['width'] > 0 and box['height'] > 0:
                                    visible_ads.append(element)
                        except:
                            continue
                except:
                    continue
                    
            print(f"Found {len(visible_ads)} visible AdSense ads from {len(ad_selectors)} selectors")
            return visible_ads
            
        except Exception as e:
            print(f"Ad detection error: {str(e)}")
            return []
            
    async def detect_vignette_ad(self, page):
        """Detect if a vignette ad is currently showing by checking URL only."""
        try:
            # Check URL for #vignette
            return "#google_vignette" in page.url
                
        except Exception as e:
            print(f"Vignette detection error: {str(e)}")
            return False
            
    async def interact_with_vignette_ad(self, page, worker_id):
        """Interact with a detected vignette ad."""
        try:
            print(f"Worker {worker_id}: Attempting to interact with vignette ad")
            
            # First try to find and click radio buttons if they exist
            radio_buttons = await page.query_selector_all('input[type="radio"]:visible')
            if radio_buttons:
                print(f"Worker {worker_id}: Found {len(radio_buttons)} radio buttons in vignette")
                # Select a random radio button
                radio = random.choice(radio_buttons)
                current_domain = self.extract_domain(page.url)
                if await self.smart_click(page, worker_id, current_domain, radio):
                    print(f"Worker {worker_id}: Clicked radio button")
                
                # Look for submit/done buttons
                submit_buttons = await page.query_selector_all(
                    'button:has-text("Submit"), button:has-text("Done"), button:has-text("Continue"), button:has-text("Close")'
                )
                
                if submit_buttons:
                    for button in submit_buttons:
                        try:
                            if await button.is_visible():
                                if await self.smart_click(page, worker_id, current_domain, button):
                                    print(f"Worker {worker_id}: Clicked vignette submit button")
                                    return True
                        except:
                            continue
                            
            # If no radio buttons or they failed, try to find and click any button in the vignette
            buttons = await page.query_selector_all(
                'button:visible, div[role="button"]:visible, a[role="button"]:visible'
            )
            
            if buttons:
                print(f"Worker {worker_id}: Found {len(buttons)} buttons in vignette")
                for button in buttons:
                    try:
                        if await button.is_visible():
                            if await self.smart_click(page, worker_id, current_domain, button):
                                print(f"Worker {worker_id}: Clicked vignette button")
                                return True
                    except:
                        continue
                        
            # If no buttons found, try clicking on images or other elements
            images = await page.query_selector_all('img:visible, svg:visible')
            if images:
                print(f"Worker {worker_id}: Found {len(images)} images in vignette")
                for img in images:
                    try:
                        if await img.is_visible():
                            if await self.smart_click(page, worker_id, current_domain, img):
                                print(f"Worker {worker_id}: Clicked vignette image")
                                return True
                    except:
                        continue
                        
            # Last resort - try clicking on the vignette container itself
            vignette_container = await page.query_selector('div[class*="vignette"], div[id*="vignette"]')
            if vignette_container:
                try:
                    if await self.smart_click(page, worker_id, current_domain, vignette_container):
                        print(f"Worker {worker_id}: Clicked vignette container")
                        return True
                except:
                    pass
                    
            print(f"Worker {worker_id}: Could not find any interactive elements in vignette")
            return False
            
        except Exception as e:
            print(f"Worker {worker_id}: Error interacting with vignette: {str(e)}")
            return False
            
    async def check_and_handle_vignette(self, page, worker_id):
        """Check for and handle vignette ads if present."""
        try:
            # Check if vignette ad is present
            vignette_present = await self.detect_vignette_ad(page)
            if not vignette_present:
                return False
                
            print(f"Worker {worker_id}: Vignette ad detected")
            
            # Try to interact with the vignette
            success = await self.interact_with_vignette_ad(page, worker_id)
            if success:
                print(f"Worker {worker_id}: Successfully interacted with vignette ad")
                await page.wait_for_timeout(2000)  # Wait for vignette to close
                return True
                
            return False
            
        except Exception as e:
            print(f"Worker {worker_id}: Error checking/handling vignette: {str(e)}")
            return False
            
    async def interact_with_ads(self, page, browser, worker_id):
        """Interact with visible ads on the page by clicking them to open in new tabs."""
        visible_ads = await self.detect_adsense_ads(page)
        if not visible_ads:
            print(f"Worker {worker_id}: No visible AdSense ads found on page")
            return False
            
        print(f"Worker {worker_id}: Found {len(visible_ads)} visible AdSense ads on page")
        
        # Count current tabs before clicking
        context = browser.contexts[0]
        tabs_before = len(context.pages)
        
        clicked = False
        
        # Shuffle ads to click random ones first
        random.shuffle(visible_ads)
        
        for ad in visible_ads:
            try:
                current_domain = self.extract_domain(page.url)
                
                # Get ad position for logging
                box = await ad.bounding_box()
                ad_position = f"({box['x']:.0f},{box['y']:.0f})" if box else "(unknown position)"
                
                print(f"Worker {worker_id}: Attempting to click ad at {ad_position}")
                
                # Perform the click with is_ad_activity=True to open in new tab
                if await self.smart_click(page, worker_id, current_domain, ad, is_ad_activity=True):
                    # Wait longer after ad click to ensure tab opens (2-3 seconds)
                    await asyncio.sleep(random.uniform(2, 3))
                    
                    # Check if new tab was opened
                    tabs_after = len(context.pages)
                    if tabs_after > tabs_before:
                        print(f"Worker {worker_id}: Ad click successful - new tab opened (total tabs: {tabs_after})")
                        clicked = True
                        break
                    else:
                        print(f"Worker {worker_id}: Ad click did not open new tab (total tabs remains: {tabs_after})")
                        
                    # Small delay before trying next ad if this one failed
                    await asyncio.sleep(1)
                    
            except Exception as e:
                print(f"Worker {worker_id}: Error clicking visible ad: {str(e)}")
                # Small delay after error before continuing
                await asyncio.sleep(1)
                continue
                
        return clicked
    
    async def smart_click(self, page, worker_id, current_domain, element=None, is_ad_activity=False):
        """
        Perform a smart click with multiple fallback methods.
        For ads activities, opens links in new tabs using middle click or Ctrl+click.
        """
        try:
            # Ensure we're on the correct tab before clicking
            if not page or page.is_closed():
                print(f"Worker {worker_id}: Page is closed or invalid during smart click")
                return False

            # If no element provided, find one automatically
            if not element:
                # Get all clickable elements that are visible and not overlapped
                elements = await page.query_selector_all("a, button, input[type='button'], input[type='submit']")
                if not elements:
                    print(f"Worker {worker_id}: No clickable elements found")
                    return False
                
                # Filter elements that are visible and not overlapped
                valid_elements = []
                for el in elements:
                    try:
                        # Check if element is visible and not overlapped
                        is_visible = await el.is_visible()
                        is_covered = await page.evaluate("""(element) => {
                            const rect = element.getBoundingClientRect();
                            const x = rect.left + rect.width / 2;
                            const y = rect.top + rect.height / 2;
                            const topElement = document.elementFromPoint(x, y);
                            return topElement !== element && !element.contains(topElement);
                        }""", el)
                        
                        if is_visible and not is_covered:
                            valid_elements.append(el)
                    except:
                        continue
                
                if not valid_elements:
                    print(f"Worker {worker_id}: No valid clickable elements found")
                    return False
                
                element = random.choice(valid_elements)

            # Always get element info BEFORE any clicks or scrolls
            try:
                href = await element.get_attribute("href") or ""
            except:
                href = "N/A"

            try:
                tag = await element.evaluate('el => el.tagName')
            except:
                tag = "N/A"

            try:
                text_content = await element.text_content()
                text_preview = (text_content or "").strip()[:50]
            except:
                text_preview = "N/A"

            element_info = f"Tag: {tag}, Text: {text_preview}"
            
            # Scroll element into view
            await element.scroll_into_view_if_needed(timeout=10000)
            box = await element.bounding_box()
            if not box:
                print(f"Worker {worker_id}: Could not get element position")
                return False
                
            # Add cursor trail effect
            await self.add_cursor_trail(page)
            
            # Try mouse movement click first
            try:
                # Move mouse to element with human-like movement
                await page.mouse.move(
                    box['x'] + box['width'] / 2,
                    box['y'] + box['height'] / 2,
                    steps=random.randint(5, 15)
                )
                await page.wait_for_timeout(random.randint(300, 800))
                
                if is_ad_activity:
                    # For ads, first try middle click to open in new tab
                    try:
                        await page.mouse.click(
                            box['x'] + box['width'] / 2,
                            box['y'] + box['height'] / 2,
                            button="middle",
                            click_count=1,
                            delay=random.randint(50, 200))
                        print(f"Worker {worker_id}: Middle clicked ad element via mouse: {href if href else 'no href'}\nElement: {element_info}")
                        return True
                    except Exception as e:
                        print(f"Worker {worker_id}: Middle click failed, trying Ctrl+click: {str(e)}\nElement: {element_info}")
                        # If middle click failed, try Ctrl+click
                        await page.keyboard.down('Control')
                        await page.mouse.click(
                            box['x'] + box['width'] / 2,
                            box['y'] + box['height'] / 2,
                            button="left",
                            click_count=1,
                            delay=random.randint(50, 200))
                        await page.keyboard.up('Control')
                        print(f"Worker {worker_id}: Ctrl+clicked ad element via mouse: {href if href else 'no href'}\nElement: {element_info}")
                        return True
                else:
                    # Normal left click for non-ad elements
                    await page.mouse.click(
                        box['x'] + box['width'] / 2,
                        box['y'] + box['height'] / 2,
                        button="left",
                        click_count=1,
                        delay=random.randint(50, 200))
                    print(f"Worker {worker_id}: Clicked element via mouse: {href if href else 'no href'}\nElement: {element_info}")
                    return True
                    
            except Exception as e:
                print(f"Worker {worker_id}: Mouse click failed, trying native click: {str(e)}\nElement: {element_info}")
                try:
                    # If mouse click failed, try native click
                    if is_ad_activity:
                        # For ads, try to open in new tab via JavaScript
                        try:
                            await page.evaluate("""(element) => {
                                const event = new MouseEvent('click', {
                                    view: window,
                                    bubbles: true,
                                    cancelable: true,
                                    button: 1  // Middle click
                                });
                                element.dispatchEvent(event);
                            }""", element)
                            print(f"Worker {worker_id}: Middle clicked ad element via JS: {href if href else 'no href'}\nElement: {element_info}")
                            return True
                        except:
                            # If middle click failed, try Ctrl+click via JS
                            await page.evaluate("""(element) => {
                                const event = new MouseEvent('click', {
                                    view: window,
                                    bubbles: true,
                                    cancelable: true,
                                    ctrlKey: true
                                });
                                element.dispatchEvent(event);
                            }""", element)
                            print(f"Worker {worker_id}: Ctrl+clicked ad element via JS: {href if href else 'no href'}\nElement: {element_info}")
                            return True
                    else:
                        # Normal click for non-ad elements
                        await element.click(timeout=10000)
                        print(f"Worker {worker_id}: Clicked element via native click: {href if href else 'no href'}\nElement: {element_info}")
                        return True
                        
                except Exception as e:
                    print(f"Worker {worker_id}: Native click failed, trying JS click: {str(e)}\nElement: {element_info}")
                    try:
                        # If native click failed, try JS click
                        await page.evaluate("""(element) => {
                            element.click();
                        }""", element)
                        print(f"Worker {worker_id}: Clicked element via JS: {href if href else 'no href'}\nElement: {element_info}")
                        return True
                    except Exception as e:
                        print(f"Worker {worker_id}: All click methods failed: {str(e)}\nElement: {element_info}")
                        return False
        
        except Exception as e:
            print(f"Worker {worker_id}: Error performing smart click: {str(e)}")
            return False
        
    async def add_cursor_trail(self, page):
        """Add cursor trail effect to the page."""
        await page.evaluate(
            """
            // Only add the cursor trail if it doesn't already exist
            if (!window._cursorTrailAdded) {
                // First we create the styles
                const style = document.createElement('style');
                style.innerHTML = `
                    .cursor-trail {
                        position: fixed;
                        width: 10px;  /* Size */
                        height: 10px;
                        background-color: red;  /* Color */
                        border-radius: 50%;
                        pointer-events: none;
                        z-index: 10000;
                        opacity: 0.5;
                        transition: opacity 0.3s, transform 0.3s;
                    }
                `;
                document.head.appendChild(style);

                // Then we append an event listener for the trail
                document.addEventListener('mousemove', (event) => {
                    const trailDot = document.createElement('div');
                    trailDot.classList.add('cursor-trail');
                    document.body.appendChild(trailDot);

                    trailDot.style.left = `${event.clientX}px`;
                    trailDot.style.top = `${event.clientY}px`;

                    // after 300ms we fade out and remove the trail dot
                    setTimeout(() => {
                        trailDot.style.opacity = '0';
                        setTimeout(() => trailDot.remove(), 300);
                    }, 50);
                });
                
                window._cursorTrailAdded = true;
            }
            """
        )

    async def perform_random_activity(self, page, browser, worker_id, stay_time, is_ads_session=False):
        """
        Perform random activities on the page with full tab checking before each activity.
        """
        if not self.config['browser']['random_activity'] and not is_ads_session:
            return False
                
        try:
            # Get current URL for logging and domain checking
            current_url = page.url
            current_domain = self.extract_domain(current_url)
            
            activity_start = time.time()
            remaining_time = stay_time
            
            while remaining_time > 0 and self.running:
                # ENSURE CORRECT TAB BEFORE ANY ACTIVITY
                page, success = await self.ensure_correct_tab(browser, page, current_url, worker_id)
                if not success:
                    print(f"Worker {worker_id}: Lost correct tab during activities")
                    return False
                    
                # Check for vignette ads before starting
                await self.check_and_handle_vignette(page, worker_id)
                    
                # Determine which activities to perform based on config
                activities = []
                if 'scroll' in self.config['browser']['activities']:
                    activities.append(lambda: self.random_scroll(page, browser, worker_id))
                if 'click' in self.config['browser']['activities']:
                    activities.append(lambda: self.random_click(page, browser, worker_id, current_domain, is_ads_session))
                if 'hover' in self.config['browser']['activities']:
                    activities.append(lambda: self.random_hover(page, browser, worker_id))
                    
                # If we have activities to perform
                if activities:
                    # Perform one random activity
                    activity = random.choice(activities)
                    await activity()
                        
                    # Calculate remaining time after activity
                    elapsed = time.time() - activity_start
                    remaining_time = stay_time - elapsed
                    
                    # Small delay between activities if time remains
                    if remaining_time > 0:
                        delay = min(random.uniform(1, 3), remaining_time)
                        if delay > 0:
                            await asyncio.sleep(delay)
                            elapsed = time.time() - activity_start
                            remaining_time = stay_time - elapsed
                    
                    # CHECK VIGNETTE AFTER ACTIVITY
                    await self.check_and_handle_vignette(page, worker_id)
                    
            return True
                
        except Exception as e:
            print(f"Worker {worker_id}: Error during random activities: {str(e)}")
            return False

    async def random_click(self, page, browser, worker_id, current_domain, is_ads_session=False):
        """
        Finds random clickable elements on current domain and clicks them.
        """
        try:
            # ENSURE CORRECT TAB BEFORE CLICKING
            current_url = page.url
            page, success = await self.ensure_correct_tab(browser, page, current_url, worker_id)
            if not success:
                print(f"Worker {worker_id}: Could not ensure correct tab for clicking")
                return False

            # Store original URL to detect navigation
            original_url = page.url
            
            # Get all potential click targets
            elements = await page.query_selector_all('a, button, [onclick], [role=button]')
            if not elements:
                print(f"Worker {worker_id}: No clickable elements found")
                return False
                
            # Filter to same-domain elements only
            same_domain_elements = []
            for element in elements:
                try:
                    href = await element.get_attribute('href') or ''
                    if href and not href.startswith('#') and current_domain in self.extract_domain(href):
                        same_domain_elements.append(element)
                except:
                    continue
                    
            if not same_domain_elements:
                print(f"Worker {worker_id}: No same-domain elements found")
                return False
                
            # Select one random element to click
            element = random.choice(same_domain_elements)
            print(f"Worker {worker_id}: Attempting click on random element")
            
            # Perform the click using smart_click
            if await self.smart_click(page, worker_id, current_domain, element, is_ads_session):
                # Small delay after click
                await asyncio.sleep(random.uniform(0.5, 1.5))
                
                # Return True if navigation occurred
                return page.url != original_url
                
            return False
            
        except Exception as e:
            print(f"Worker {worker_id}: Random click error: {str(e)}")
            return False

    async def random_scroll(self, page, browser, worker_id):
        """
        Perform human-like scrolling with tab checking.
        """
        try:
            # ENSURE CORRECT TAB BEFORE SCROLLING
            current_url = page.url
            page, success = await self.ensure_correct_tab(browser, page, current_url, worker_id)
            if not success:
                print(f"Worker {worker_id}: Could not ensure correct tab for scrolling")
                return
                
            print(f"Worker {worker_id}: Performing human-like scroll")
            
            # Get page dimensions
            height = await page.evaluate("document.body.scrollHeight")
            viewport_height = await page.evaluate("window.innerHeight")
            
            if height <= viewport_height:
                print(f"Worker {worker_id}: Page is not scrollable")
                return
                
            # Random scroll parameters
            scroll_amount = random.randint(int(height * 0.2), int(height * 0.8))
            steps = random.randint(3, 10)
            step_size = scroll_amount // steps
            
            # Perform scroll in steps with random variations
            for i in range(steps):
                if not self.running:
                    break
                    
                # Random variation in step size
                current_step = step_size + random.randint(-50, 50)
                await page.evaluate(f"window.scrollBy(0, {current_step})")
                
                # Random pause between scroll steps
                await page.wait_for_timeout(random.randint(100, 500))
                
            print(f"Worker {worker_id}: Scrolled {scroll_amount}px in {steps} steps")
            
        except Exception as e:
            print(f"Worker {worker_id}: Error during scrolling: {str(e)}")

    async def random_hover(self, page, browser, worker_id):
        """
        Perform realistic mouse hover with tab checking.
        """
        try:
            # ENSURE CORRECT TAB BEFORE HOVER
            current_url = page.url
            page, success = await self.ensure_correct_tab(browser, page, current_url, worker_id)
            if not success:
                print(f"Worker {worker_id}: Could not ensure correct tab for hovering")
                return
                
            print(f"Worker {worker_id}: Performing random hover")
            
            # Get all hoverable elements
            elements = await page.query_selector_all('a, button, img, div, span:visible')
            if not elements:
                print(f"Worker {worker_id}: No hoverable elements found")
                return
                
            # Filter visible elements
            visible_elements = []
            for element in elements:
                try:
                    if await element.is_visible():
                        visible_elements.append(element)
                except:
                    continue
                    
            if not visible_elements:
                print(f"Worker {worker_id}: No visible hoverable elements")
                return
                
            # Select random element
            element = random.choice(visible_elements)
            await element.scroll_into_view_if_needed(timeout=10000)
            box = await element.bounding_box()
            if not box:
                print(f"Worker {worker_id}: Could not get element position")
                return
                
            # Add cursor trail effect
            await self.add_cursor_trail(page)
                
            # Human-like movement parameters
            steps = random.randint(5, 15)
            target_x = box['x'] + random.randint(0, int(box['width']))
            target_y = box['y'] + random.randint(0, int(box['height']))
            
            # Move mouse in steps
            for i in range(steps):
                if not self.running:
                    break
                    
                # Calculate intermediate position
                frac = (i + 1) / steps
                current_x = int(target_x * frac)
                current_y = int(target_y * frac)
                await page.mouse.move(current_x, current_y)
                
                # Random small delay between steps
                await page.wait_for_timeout(random.randint(50, 200))
                
            # Final hover position
            await page.mouse.move(target_x, target_y)
            
            # Random hover duration
            hover_time = random.uniform(0.5, 2.0)
            await page.wait_for_timeout(int(hover_time * 1000))
            
            print(f"Worker {worker_id}: Hovered at {target_x},{target_y} for {hover_time:.1f}s")
            
        except Exception as e:
            print(f"Worker {worker_id}: Error during hover: {str(e)}")
            
    async def process_ads_tabs(self, browser_context, worker_id):
        """Process any ad tabs that were opened during the session."""
        try:
            # Get all pages safely
            try:
                pages = browser_context.pages
            except AttributeError:
                print(f"Worker {worker_id}: No pages found in browser context - natural exit")
                return 0
                
            if len(pages) <= 1:
                return 0
                
            print(f"Worker {worker_id}: Processing {len(pages)-1} ad tabs")
            config_urls = []
            
            for url_data in self.config['urls']:
                if url_data['random_page']:
                    urls = [u.strip() for u in url_data['url'].split(',')]
                    config_urls.extend(urls)
                else:
                    config_urls.append(url_data['url'].strip())
                    
            ad_tabs_processed = 0
            
            for page in pages:
                try:
                    if page.is_closed():
                        continue
                        
                    current_url = page.url
                    if any(self.extract_domain(url) in current_url for url in config_urls):
                        continue
                        
                    ad_tabs_processed += 1
                    print(f"Worker {worker_id}: Processing ad tab: {current_url}")
                    
                    stay_time = random.randint(
                        self.config['ads']['min_time'],
                        self.config['ads']['max_time']
                    )
                    
                    start_time = time.time()
                    while time.time() - start_time < stay_time:
                        await self.perform_random_activity(page, browser_context, worker_id, stay_time)
                        await asyncio.sleep(self.get_random_delay(1, 3))
                        
                    await page.close()
                    
                except Exception as e:
                    print(f"Worker {worker_id}: Error processing ad tab: {str(e)}")
                    continue
                    
            return ad_tabs_processed
            
        except Exception as e:
            print(f"Worker {worker_id}: Error processing ad tabs: {str(e)}")
            return 0
            
    async def natural_exit(self, browser_context, worker_id):
        """Perform natural exit sequence by visiting Google and closing tabs."""
        try:
            # Get all pages safely
            try:
                pages = browser_context.pages
            except AttributeError:
                print(f"Worker {worker_id}: No pages found for natural exit")
                return False
                
            if not pages:
                return True
                
            print(f"Worker {worker_id}: Starting natural exit sequence")
            
            # Close all tabs except one
            while len(pages) > 1:
                try:
                    page = pages[-1]
                    if not page.is_closed():
                        await page.close()
                    pages = browser_context.pages
                    await asyncio.sleep(self.get_random_delay(1, 2))
                except Exception as e:
                    print(f"Worker {worker_id}: Error closing tab during natural exit: {str(e)}")
                    break
                    
            # Visit Google on the remaining tab if it exists
            if pages:
                try:
                    page = pages[0]
                    if not page.is_closed():
                        await page.goto("https://www.google.com ", timeout=45000, wait_until="networkidle")
                        await asyncio.sleep(self.get_random_delay(2, 5))
                        await page.close()
                except Exception as e:
                    print(f"Worker {worker_id}: Error during Google visit in natural exit: {str(e)}")
                    
            return True
            
        except Exception as e:
            print(f"Worker {worker_id}: Error during natural exit: {str(e)}")
            return False
            
    async def worker_session(self, worker_id):
        """Main worker session that performs the browsing activities."""
        session_count = 0
        successful_sessions = 0
        ads_session_count = 0
        successful_ads_sessions = 0
        
        try:
            if not self.config['urls']:
                print(f"Worker {worker_id}: No URLs configured")
                return
                
            while self.running:
                # Reset per-session timer
                session_start_time = time.time()
                
                # Check session count limit
                if (self.config['session']['enabled'] and 
                    self.config['session']['count'] > 0 and 
                    session_count >= self.config['session']['count']):
                    print(f"Worker {worker_id}: Session count limit reached")
                    break
                    
                # Determine session type
                with self.lock:
                    session_index = sum([w.session_count for w in self.workers]) if self.workers else 0
                    is_ads_session = False
                    
                    if self.pending_ads_sessions > 0:
                        is_ads_session = True
                        self.pending_ads_sessions -= 1
                    elif session_index < len(self.ads_session_flags):
                        is_ads_session = self.ads_session_flags[session_index]
                        
                # Session header
                if is_ads_session:
                    print(f"Worker {worker_id}: Starting AD INTERACTION session")
                    ads_session_count += 1
                else:
                    print(f"Worker {worker_id}: Starting normal session")
                    
                session_count += 1
                session_successful = False
                browser = None
                
                try:
                    # --- BROWSER INITIALIZATION ---
                    browser = await self.configure_browser(worker_id)
                    if not browser:
                        print(f"Worker {worker_id}: Failed to initialize browser")
                        await asyncio.sleep(10)
                        continue

                    # Use the default context already created by Camoufox
                    context = await browser.new_context()
                    page = await context.new_page()
                    
                    # Track if ad click was successful in this session
                    ad_click_success = False
                    
                    # --- URL PROCESSING ---
                    for url_index, url_data in enumerate(self.config['urls']):
                        if not self.running:
                            break
                            
                        # Check max session time (per-session basis)
                        if (self.config['session']['max_time'] > 0 and 
                            (time.time() - session_start_time) >= self.config['session']['max_time'] * 60):
                            print(f"Worker {worker_id}: Max session time reached")
                            break
                            
                        # Get target URL
                        if url_data['random_page']:
                            urls = [u.strip() for u in url_data['url'].split(',') if u.strip()]
                            url = random.choice(urls) if urls else url_data['url'].strip()
                        else:
                            url = url_data['url'].strip()
                        
                        # Print URL sequence information
                        print(f"Worker {worker_id}: [URL {url_index + 1}/{len(self.config['urls'])}] Visiting: {url}")
                            
                        # --- FIRST URL HANDLING ---
                        if url_index == 0:
                            referrer_types = self.config['referrer']['types']
                            referrer_type = random.choice(referrer_types)
                            
                            # Social referrer
                            if referrer_type == "social":
                                with open('referrers.json', 'r') as f:
                                    referrers = json.load(f)
                                social = random.choice(list(referrers['social'].values()))
                                referrer = f"https://{random.choice(social)}"
                                await page.set_extra_http_headers({'referer': referrer})
                                print(f"Worker {worker_id}: Using social referrer: {referrer}")
                                
                                # Direct visit
                                print(f"Worker {worker_id}: Loading initial URL directly")
                                try:
                                    await page.goto(url, timeout=90000, wait_until="networkidle")
                                except Exception as e:
                                    print(f"Worker {worker_id}: Error visiting URL: {str(e)}")
                                    raise SessionFailedException("Failed to visit initial URL")
                                    
                            # Organic search
                            elif referrer_type == "organic":
                                keyword = self.get_random_keyword()
                                if not keyword:
                                    print(f"Worker {worker_id}: No valid keyword available")
                                    raise SessionFailedException("No valid keyword available")
                                    
                                print(f"Worker {worker_id}: Using keyword: {keyword}")
                                target_domain = self.extract_domain(url)
                                if not await self.perform_organic_search(page, keyword, target_domain, worker_id):
                                    print(f"Worker {worker_id}: Organic search failed")
                                    raise SessionFailedException("Organic search failed")
                                    
                            # Direct visit
                            else:
                                print(f"Worker {worker_id}: Loading initial URL directly")
                                try:
                                    await page.goto(url, timeout=90000, wait_until="networkidle")
                                except Exception as e:
                                    print(f"Worker {worker_id}: Error visiting URL: {str(e)}")
                                    raise SessionFailedException("Failed to visit initial URL")
                                    
                        # --- SUBSEQUENT URLS ---
                        else:
                            print(f"Worker {worker_id}: Navigating to next URL in sequence")
                            if not await self.navigate_to_url_by_click(page, url, worker_id):
                                print(f"Worker {worker_id}: Falling back to direct navigation")
                                try:
                                    await page.goto(url, timeout=90000, wait_until="networkidle")
                                except Exception as e:
                                    print(f"Worker {worker_id}: Error visiting URL: {str(e)}")
                                    raise SessionFailedException("Failed to navigate to URL")
                                    
                        # Check cookies after navigation
                        if self.config['browser']['auto_accept_cookies']:
                            await self.accept_google_cookies(page)

                        await self.handle_gdpr_consent(page, worker_id)
                            
                        # Check for vignette ads after page load
                        await self.check_and_handle_vignette(page, worker_id)
                            
                        # Get stay time for this URL from config
                        stay_time = random.randint(url_data['min_time'], url_data['max_time'])
                        print(f"Worker {worker_id}: Staying on page for {stay_time} seconds")
                        
                        # Perform random activities within the stay time
                        activity_start = time.time()
                        remaining_time = stay_time
                        while remaining_time > 0 and self.running:
                            # Calculate remaining time
                            elapsed = time.time() - activity_start
                            remaining_time = stay_time - elapsed
                            
                            # Perform random activity with proper tab checking
                            activity_success = await self.perform_random_activity(
                                page, browser, worker_id, remaining_time, is_ads_session)
                                                        
                            if is_ads_session and activity_success:
                                successful_ads_sessions += 1
                                                        
                            # Small delay between activities if time remains
                            if remaining_time > 0:
                                delay = min(random.uniform(0.5, 1.5), remaining_time)
                                if delay > 0:
                                    await asyncio.sleep(delay)
                        
                        # Handle ads session if needed (only if we haven't had a successful click yet)
                        if is_ads_session and not ad_click_success:
                            print(f"Worker {worker_id}: Checking for ads elements on URL {url_index + 1}")
                            # Count tabs before ad click
                            tabs_before = len(context.pages)
                            
                            # Try to interact with ads
                            ad_click_success = await self.interact_with_ads(page, browser, worker_id)
                            
                            if ad_click_success:
                                # Count tabs after ad click
                                tabs_after = len(context.pages)
                                if tabs_after > tabs_before:
                                    print(f"Worker {worker_id}: Ad click successful (new tab opened)")
                                    successful_ads_sessions += 1
                                else:
                                    print(f"Worker {worker_id}: Ad click did not open new tab")
                                    ad_click_success = False
                    
                    # If we get here, all URLs processed successfully
                    session_successful = True
                    
                except SessionFailedException as e:
                    print(f"Worker {worker_id}: Session marked as failed: {str(e)}")
                    if is_ads_session:
                        with self.lock:
                            self.failed_ads_sessions += 1
                    session_successful = False
                except Exception as e:
                    print(f"Worker {worker_id}: Critical error: {str(e)}")
                    session_successful = False
                    
                finally:
                    # --- RESOURCE CLEANUP ---
                    try:
                        if browser:
                            # Process any ad tabs that were opened
                            await self.process_ads_tabs(context, worker_id)
                            
                            # Perform natural exit
                            await self.natural_exit(context, worker_id)
                            
                            # Clean up browser and profile
                            await self.cleanup_browser(browser, worker_id)
                    except Exception as e:
                        print(f"Worker {worker_id}: Error during cleanup: {str(e)}")
                    
                    # Small delay to ensure clean closure
                    await asyncio.sleep(1)
                    
                # --- POST-SESSION HANDLING ---
                if session_successful:
                    successful_sessions += 1
                    delay = self.get_random_delay(10, 30)
                    print(f"Worker {worker_id}: Session successful, waiting {delay}s")
                else:
                    delay = self.get_random_delay(30, 60)
                    print(f"Worker {worker_id}: Session failed, waiting {delay}s")
                    
                await asyncio.sleep(delay)
                
        except Exception as e:
            print(f"Worker {worker_id}: FATAL ERROR: {str(e)}")
        finally:
            # --- FINAL STATS ---
            with self.lock:
                self.session_counts[worker_id] = session_count
                self.successful_sessions[worker_id] = successful_sessions
                self.ads_session_counts[worker_id] = ads_session_count
                self.successful_ads_sessions[worker_id] = successful_ads_sessions
                
            print(f"Worker {worker_id}: Session completed - "
                f"Total: {session_count}, "
                f"Success: {successful_sessions}, "
                f"Ads: {ads_session_count} ({successful_ads_sessions} successful)")
    
    def start(self):
        """Start the nexAds automation with configured threads."""
        if self.running:
            print("Already running")
            return
            
        self.running = True
        self.start_time = datetime.now()
        self.session_counts = {}
        self.successful_sessions = {}
        self.ads_session_counts = {}
        self.successful_ads_sessions = {}
        self.failed_ads_sessions = 0
        
        print(f"Starting nexAds with {self.config['threads']} threads")
        print(f"Total sessions planned: {self.total_sessions} (Ads: {self.ads_sessions})")
        
        self.workers = []
        
        # Start all workers
        for i in range(self.config['threads']):
            p = multiprocessing.Process(
                target=run_worker,
                args=(CONFIG_PATH, i + 1)
            )
            p.start()
            self.workers.append(p)
            
        try:
            # Monitor workers until all complete
            while any(p.is_alive() for p in self.workers):
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
            
        print("\nAll workers completed")
        
        total_sessions = sum(self.session_counts.values())
        successful_sessions = sum(self.successful_sessions.values())
        total_ads_sessions = sum(self.ads_session_counts.values())
        successful_ads_sessions = sum(self.successful_ads_sessions.values())
        
        print(f"Total sessions attempted: {total_sessions}")
        print(f"Successful sessions: {successful_sessions} ({successful_sessions/max(1, total_sessions)*100:.1f}%)")
        print(f"Total ads sessions attempted: {total_ads_sessions}")
        print(f"Successful ads sessions: {successful_ads_sessions} ({successful_ads_sessions/max(1, total_ads_sessions)*100:.1f}%)")
        print(f"Failed ads sessions: {self.failed_ads_sessions}")
        print(f"Actual CTR: {successful_ads_sessions/max(1, successful_sessions)*100:.2f}% (Target: {self.config['ads']['ctr']}%)")
        
    def stop(self):
        """Stop the nexAds automation."""
        if not self.running:
            return
            
        self.running = False
        print("Stopping all workers...")
        
        # Terminate all worker processes
        for worker in self.workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=10)
                
        runtime = datetime.now() - self.start_time
        print(f"nexAds stopped. Total runtime: {runtime}")

async def run_worker_async(config_path, worker_id):
    """Top-level async function for multiprocessing.
    
    This function creates a new nexAds instance and runs a single worker session.
    """
    try:
        # Create a new automation instance for this process
        automation = nexAds(config_path=config_path)
        automation.running = True
        await automation.worker_session(worker_id)
    except Exception as e:
        print(f"Worker {worker_id} failed: {str(e)}")
    finally:
        # Clean up
        try:
            automation = None
        except:
            pass

def run_worker(config_path, worker_id):
    """Wrapper to run async worker in new event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_worker_async(config_path, worker_id))
    loop.close()

def main():
    """Main entry point for nexAds application."""
    parser = ArgumentParser(description='nexAds Automation Tool')
    parser.add_argument('--config', action='store_true', help='Open configuration GUI')
    args = parser.parse_args()
    
    if args.config:
        app = QApplication(sys.argv)
        window = ConfigWindow()
        window.show()
        sys.exit(app.exec_())
    else:
        automation = nexAds()
        try:
            automation.start()
        except KeyboardInterrupt:
            automation.stop()

if __name__ == '__main__':
    multiprocessing.freeze_support()
    multiprocessing.set_start_method('spawn')
    main()