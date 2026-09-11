"""
scraper/browser.py
───────────────────
Playwright browser pool with stealth anti-detection patches.

Provides:
  - BrowserPool  — async context manager managing N browser instances
  - new_page()   — creates a new stealth-patched page with proxy support
"""

from __future__ import annotations

import asyncio
import json
import random
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Optional

from loguru import logger
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from config.settings import settings

# ── Realistic user agents (rotate to avoid fingerprinting) ───────────────────
USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0",
]

# ── Viewport sizes to rotate through ─────────────────────────────────────────
VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
]


async def _apply_stealth_scripts(page: Page) -> None:
    """
    Inject JavaScript patches to mask common headless browser fingerprints.
    These run before any page navigation.
    """
    stealth_js = """
    // 1. Hide navigator.webdriver — most critical check
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true
    });

    // 2. Fake plugins (real browsers have plugins)
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
    });

    // 3. Fake language list
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-IN', 'en-US', 'en', 'hi'],
    });

    // 4. Remove Playwright-specific variables
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
    delete window.__playwright;
    delete window.__pw_manual;

    // 5. Override permissions API
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
    );

    // 6. Fix iframe contentWindow
    const originalGetter = HTMLIFrameElement.prototype.__lookupGetter__('contentWindow');
    Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
        get: function() {
            const w = originalGetter.call(this);
            if (w && w.navigator && w.navigator.webdriver) {
                Object.defineProperty(w.navigator, 'webdriver', {
                    get: () => undefined
                });
            }
            return w;
        }
    });

    // 7. Realistic chrome object
    window.chrome = {
        runtime: {
            onMessage: { addListener: () => {} },
            connect: () => {},
        },
        loadTimes: function() {},
        csi: function() {},
        app: {}
    };

    // 8. Fake hardware concurrency and memory (headless often shows 2/0.25)
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });

    // 9. Spoof screen properties
    Object.defineProperty(screen, 'availWidth', { get: () => window.innerWidth });
    Object.defineProperty(screen, 'availHeight', { get: () => window.innerHeight });
    """
    await page.add_init_script(stealth_js)


async def new_context(
    playwright: Playwright,
    browser: Browser,
    proxy_server: Optional[str] = None,
    source_portal: str = "default",
) -> BrowserContext:
    """
    Creates a new BrowserContext with stealth settings and optional proxy.
    Each context has isolated cookies/storage — treat it like a fresh browser session.
    """
    ua = random.choice(USER_AGENTS)
    viewport = random.choice(VIEWPORTS)

    context_kwargs: dict = {
        "user_agent": ua,
        "viewport": viewport,
        "locale": "en-IN",
        "timezone_id": "Asia/Kolkata",
        "geolocation": {"latitude": 28.6139, "longitude": 77.2090},  # New Delhi
        "permissions": ["geolocation"],
        "java_script_enabled": True,
        "bypass_csp": False,
        "extra_http_headers": {
            "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
        },
    }

    if proxy_server:
        context_kwargs["proxy"] = {"server": proxy_server}

    state_file = _storage_state_path(source_portal)
    if state_file.exists() and state_file.stat().st_size > 0:
        try:
            # Validate first. Playwright otherwise raises a confusing
            # ``Extra data`` JSON error when a previous process was interrupted.
            json.loads(state_file.read_text(encoding="utf-8"))
            context_kwargs["storage_state"] = str(state_file)
            logger.debug("Loading browser state for {}.", source_portal)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Ignoring invalid browser state for {}: {}", source_portal, exc)

    context = await browser.new_context(**context_kwargs)

    async def _handle_route(route):
        if _should_block_resource(route.request.url):
            await route.abort()
        else:
            await route.continue_()

    # Block ONLY tracking/analytics — do NOT block CSS/fonts as React apps need them to render
    await context.route("**/*", _handle_route)

    return context


def _storage_state_path(source_portal: str) -> Path:
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", source_portal).strip("._") or "default"
    return settings.data_dir / "browser_states" / f"{safe_name}.json"


def _should_block_resource(url: str) -> bool:
    """Block only tracking/analytics/ads. Keep CSS, fonts, JS — needed for React rendering."""
    block_patterns = [
        "google-analytics", "googletagmanager", "facebook.net", "twitter.com",
        "doubleclick", "adservice", "hotjar", "mixpanel", "segment.io",
        "newrelic", "datadog", "gtag/js", "fbevents",
    ]
    return any(pat in url.lower() for pat in block_patterns)


@asynccontextmanager
async def new_page(
    playwright: Playwright,
    browser: Browser,
    proxy_server: Optional[str] = None,
    source_portal: str = "default",
) -> AsyncGenerator[Page, None]:
    """
    Async context manager that yields a stealth-patched Playwright page.

    Usage:
        async with new_page(playwright, browser, proxy) as page:
            await page.goto("https://...")
    """
    context = await new_context(playwright, browser, proxy_server, source_portal)
    page = await context.new_page()
    await _apply_stealth_scripts(page)
    try:
        yield page
    finally:
        # Save state on close so cookies persist
        try:
            state_file = _storage_state_path(source_portal)
            state_file.parent.mkdir(parents=True, exist_ok=True)
            temp_file = state_file.with_suffix(".tmp")
            await context.storage_state(path=str(temp_file))
            # Validate and atomically replace, so a killed write is never loaded.
            json.loads(temp_file.read_text(encoding="utf-8"))
            temp_file.replace(state_file)
            logger.debug("Saved browser session state for {}.", source_portal)
        except Exception as e:
            logger.warning(f"Failed to save state: {e}")
            
        try:
            await context.close()
        except Exception as exc:
            # A browser/page crash should not overwrite a completed scrape's
            # outcome. The pool will restart the browser before the next job.
            logger.warning("Browser context was already closed: {}", exc)


class BrowserPool:
    """
    Manages a pool of Playwright browser instances for concurrent scraping.
    Uses a semaphore to cap concurrency per settings.max_concurrent_scrapers.

    Usage:
        async with BrowserPool() as pool:
            async with pool.acquire_page() as page:
                await page.goto(...)
    """

    def __init__(self) -> None:
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._semaphore: Optional[asyncio.Semaphore] = None

    async def start(self) -> None:
        logger.info("Starting Playwright browser pool (headless={})", settings.headless)
        self._playwright = await async_playwright().start()
        self._browser = await self._launch_browser()
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_scrapers)
        logger.success("Browser pool started.")

    async def _launch_browser(self) -> Browser:
        assert self._playwright is not None
        return await self._playwright.chromium.launch(
            headless=settings.headless,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--disable-gpu",
                "--window-size=1920,1080",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-notifications",
                "--disable-popup-blocking",
                "--ignore-certificate-errors",
                "--lang=en-IN",
                # Prevents 'Chrome is being controlled by automated software' banner
                "--excludeSwitches=enable-automation",
                "--useAutomationExtension=false",
            ],
        )

    async def stop(self) -> None:
        if self._browser:
            try:
                await self._browser.close()
            except Exception as exc:
                logger.warning("Browser was already closed during pool shutdown: {}", exc)
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser pool stopped.")

    async def __aenter__(self) -> "BrowserPool":
        await self.start()
        return self

    async def __aexit__(self, *_) -> None:
        await self.stop()

    @asynccontextmanager
    async def acquire_page(
        self,
        proxy_server: Optional[str] = None,
        source_portal: str = "default",
    ) -> AsyncGenerator[Page, None]:
        """
        Acquires a semaphore slot and yields a fresh stealth page.
        Automatically releases the slot and closes the page on exit.
        """
        assert self._browser is not None, "BrowserPool not started. Use 'async with BrowserPool()'"
        assert self._semaphore is not None

        async with self._semaphore:
            if not self._browser.is_connected():
                logger.warning("Browser process disconnected; restarting before next collection job")
                self._browser = await self._launch_browser()
            async with new_page(
                self._playwright, self._browser, proxy_server, source_portal
            ) as page:
                yield page
