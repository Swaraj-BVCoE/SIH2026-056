"""
scraper/base_scraper.py
────────────────────────
Abstract base class for all airline and OTA scrapers.

Subclass this and implement:
  - SOURCE_PORTAL : str  — unique identifier (e.g. "indigo_direct")
  - _fetch()             — async method that does the actual scraping

The base class handles:
  - Retry logic with exponential backoff (tenacity)
  - Human-like random delays between actions
  - XHR/Fetch response interception hook
  - ScrapeRun audit logging
  - Structured error classification
"""

from __future__ import annotations

import asyncio
import json
import random
from abc import ABC, abstractmethod
from datetime import date, datetime, timezone
from typing import Any, Optional

from loguru import logger
from playwright.async_api import Page, Response
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config.routes import Route
from config.settings import settings
from db.database import get_db
from db.models import FlightPrice, ScrapeRun
from scraper.proxy import proxy_pool


# ── Custom Exceptions ─────────────────────────────────────────────────────────
class ScraperBlocked(Exception):
    """Raised when the scraper detects it has been blocked (429, 403, CAPTCHA)."""


class ScraperParseError(Exception):
    """Raised when the page/response structure has changed unexpectedly."""


class ScraperNetworkError(Exception):
    """Raised for transient network-level failures."""


# ── Parsed fare data schema ───────────────────────────────────────────────────
class FareRecord:
    """
    Intermediate, loosely-typed representation of a scraped fare.
    Validated + converted to FlightPrice by the pipeline.
    """

    def __init__(
        self,
        origin: str,
        destination: str,
        travel_date: date,
        airline: str,
        total_fare: float,
        *,
        airline_code: str = "",
        flight_number: str = "",
        departure_time: str = "",   # HH:MM string
        arrival_time: str = "",     # HH:MM string
        duration_minutes: int = 0,
        stops: int = 0,
        fare_class: str = "Economy",
        base_fare: float = 0.0,
        taxes_fees: float = 0.0,
        currency: str = "INR",
        seats_left: int = 0,
        is_refundable: Optional[bool] = None,
        raw: dict | None = None,
    ) -> None:
        self.origin = origin.upper()
        self.destination = destination.upper()
        self.travel_date = travel_date
        self.airline = airline
        self.airline_code = airline_code
        self.flight_number = flight_number
        self.departure_time = departure_time
        self.arrival_time = arrival_time
        self.duration_minutes = duration_minutes
        self.stops = stops
        self.fare_class = fare_class
        self.base_fare = base_fare
        self.taxes_fees = taxes_fees
        self.total_fare = total_fare
        self.currency = currency
        self.seats_left = seats_left
        self.is_refundable = is_refundable
        self.raw = raw or {}

    def __repr__(self) -> str:
        return (
            f"FareRecord({self.origin}→{self.destination} "
            f"{self.travel_date} {self.airline} {self.flight_number} "
            f"₹{self.total_fare:.0f})"
        )


# ── Base Scraper ──────────────────────────────────────────────────────────────
class BaseScraper(ABC):
    """
    Abstract base class. All airline and OTA scrapers extend this.

    Subclasses MUST define:
        SOURCE_PORTAL: str
        async def _fetch(self, page, route, travel_date) -> list[FareRecord]
    """

    SOURCE_PORTAL: str = "base"  # Override in subclass

    def __init__(self) -> None:
        self._intercepted_responses: list[dict] = []
        self.last_status: str = "PENDING"
        self.last_error: str = ""

    # ── Public API ────────────────────────────────────────────────────────────
    async def scrape(
        self,
        page: Page,
        route: Route,
        travel_date: date,
        scrape_run_id: Optional[int] = None,
    ) -> list[FareRecord]:
        """
        Main entry point. Wraps _fetch() with retry, logging, and error handling.
        Returns a list of FareRecord objects (may be empty on failure).
        """
        logger.info(
            "[{}] Scraping {} → {} for {}",
            self.SOURCE_PORTAL,
            route.origin,
            route.destination,
            travel_date,
        )
        self.last_status = "RUNNING"
        self.last_error = ""

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(settings.scrape_retry_attempts),
                wait=wait_exponential(
                    multiplier=1,
                    min=settings.scrape_retry_delay,
                    max=settings.scrape_retry_delay * 4,
                ),
                retry=retry_if_exception_type((ScraperNetworkError, ScraperParseError)),
                reraise=True,
            ):
                with attempt:
                    self._intercepted_responses.clear()
                    records = await self._fetch(page, route, travel_date)
                    logger.success(
                        "[{}] {} records found for {}-{} on {}",
                        self.SOURCE_PORTAL,
                        len(records),
                        route.origin,
                        route.destination,
                        travel_date,
                    )
                    self.last_status = "SUCCESS" if records else "NO_DATA"
                    return records

        except ScraperBlocked as exc:
            self.last_status = "BLOCKED"
            self.last_error = str(exc)
            logger.warning("[{}] BLOCKED: {}", self.SOURCE_PORTAL, exc)
            return []
        except ScraperParseError as exc:
            self.last_status = "FAILED"
            self.last_error = str(exc)
            logger.error("[{}] PARSE ERROR: {}", self.SOURCE_PORTAL, exc)
            return []
        except ScraperNetworkError as exc:
            self.last_status = "OFFLINE"
            self.last_error = str(exc)
            logger.error("[{}] NETWORK ERROR (exhausted retries): {}", self.SOURCE_PORTAL, exc)
            return []
        except RetryError as exc:
            self.last_status = "FAILED"
            self.last_error = str(exc)
            logger.error("[{}] All retries exhausted.", self.SOURCE_PORTAL)
            return []
        except Exception as exc:
            self.last_status = "FAILED"
            self.last_error = str(exc)
            logger.exception("[{}] Unexpected error: {}", self.SOURCE_PORTAL, exc)
            return []

    @abstractmethod
    async def _fetch(
        self,
        page: Page,
        route: Route,
        travel_date: date,
    ) -> list[FareRecord]:
        """
        Implement this in each scraper subclass.
        Navigate to the site, extract fares, return FareRecord list.
        """
        ...

    # ── Helpers for subclasses ────────────────────────────────────────────────
    async def human_delay(self, min_s: float | None = None, max_s: float | None = None) -> None:
        """Pause for a random human-like delay."""
        lo = min_s if min_s is not None else settings.request_delay_min
        hi = max_s if max_s is not None else settings.request_delay_max
        delay = random.uniform(lo, hi)
        await asyncio.sleep(delay)

    async def human_type(self, page: Page, selector: str, text: str) -> None:
        """Click an input, clear it, and type with random delays per keystroke."""
        await page.click(selector)
        await page.fill(selector, "")
        for char in text:
            await page.type(selector, char, delay=random.randint(50, 180))
        await self.human_delay(0.3, 0.8)

    def setup_xhr_intercept(self, page: Page, url_patterns: list[str]) -> None:
        """
        Register a response listener to capture XHR/Fetch JSON API calls.
        Captured responses are stored in self._intercepted_responses.

        Args:
            url_patterns: List of substrings — if any match the response URL,
                          the JSON body is captured.
        """
        async def _on_response(response: Response) -> None:
            if not any(pat in response.url for pat in url_patterns):
                return
            try:
                if "application/json" in response.headers.get("content-type", ""):
                    data = await response.json()
                    self._intercepted_responses.append(data)
                    logger.debug(
                        "[{}] Intercepted XHR: {} ({} bytes)",
                        self.SOURCE_PORTAL,
                        response.url[:80],
                        len(str(data)),
                    )
            except Exception:
                pass  # Non-JSON or already consumed

        page.on("response", _on_response)

    async def check_for_block(self, page: Page) -> None:
        """
        Check common block indicators on the current page.
        Raises ScraperBlocked if detected, unless running headful (gives user a chance to solve).
        """
        if not settings.headless:
            return  # Let the user solve the CAPTCHA manually; timeouts will handle failures.

        content = await page.content()
        block_signals = [
            "access denied",
            "403 forbidden",
            "robot",
            "captcha",
            "cloudflare",
            "datadome",
            "too many requests",
            "rate limit",
            "unusual traffic",
        ]
        content_lower = content.lower()
        for signal in block_signals:
            if signal in content_lower:
                raise ScraperBlocked(
                    f"Block detected on {page.url!r}: matched '{signal}'"
                )

    async def wait_for_results(
        self,
        page: Page,
        selector: str,
        timeout: int = 30_000,
    ) -> bool:
        """
        Wait for a CSS selector to appear. Returns True if found, False on timeout.
        Raises ScraperBlocked if a block is detected while waiting.
        """
        try:
            await page.wait_for_selector(selector, timeout=timeout)
            await self.check_for_block(page)
            return True
        except Exception:
            await self.check_for_block(page)
            return False

    # ── ScrapeRun audit helpers ───────────────────────────────────────────────
    def _create_run(self, route: Route, travel_date: date, proxy_used: str = "") -> int:
        """Insert a ScrapeRun record and return its ID."""
        with get_db() as db:
            run = ScrapeRun(
                started_at=datetime.now(tz=timezone.utc),
                source_portal=self.SOURCE_PORTAL,
                origin=route.origin,
                destination=route.destination,
                travel_date=travel_date,
                status="RUNNING",
                proxy_used=proxy_used or None,
            )
            db.add(run)
            db.flush()
            return run.id

    def _finish_run(
        self,
        run_id: int,
        status: str,
        records: int = 0,
        error: str = "",
    ) -> None:
        """Update a ScrapeRun record with final status."""
        with get_db() as db:
            run = db.get(ScrapeRun, run_id)
            if run:
                run.finished_at = datetime.now(tz=timezone.utc)
                run.status = status
                run.records_inserted = records
                run.error_message = error or None
