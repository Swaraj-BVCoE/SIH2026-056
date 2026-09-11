"""
scraper/airlines/air_india.py
──────────────────────────────
Air India direct website scraper (airindia.com).
Also covers Air India Express (IX) routes where available.

Strategy: XHR API Interception + HTML fallback
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

# pyrefly: ignore [missing-import]
from loguru import logger
from playwright.async_api import Page

from config.routes import Route
from scraper.base_scraper import BaseScraper, FareRecord, ScraperBlocked, ScraperParseError
from scraper.page_health import navigate_to_working_page

INTERCEPT_PATTERNS = [
    "availability",
    "Availability",
    "flightSearch",
    "searchFlights",
    "search-flights",
    "api/flights",
    "offers",
]

SEARCH_URLS = (
    "https://www.airindia.com/in/en/book/search-flights.html",
    "https://www.airindia.com/en-in/book-flights/",
)


class AirIndiaScraper(BaseScraper):
    SOURCE_PORTAL = "air_india_direct"

    async def _fetch(self, page: Page, route: Route, travel_date: date) -> list[FareRecord]:
        self.setup_xhr_intercept(page, INTERCEPT_PATTERNS)

        await navigate_to_working_page(
            page, SEARCH_URLS, "air_india", expected_terms=("search", "book")
        )

        await self.check_for_block(page)
        await self.human_delay(2.5, 4.0)
        await self._dismiss_cookie_banner(page)

        await self._select_oneway(page)
        if not await self._fill_origin(page, route.origin):
            raise ScraperParseError("Air India origin control was not found")
        await self.human_delay(1.0, 2.0)
        if not await self._fill_destination(page, route.destination):
            raise ScraperParseError("Air India destination control was not found")
        await self.human_delay(1.0, 2.0)
        if not await self._select_date(page, travel_date):
            raise ScraperParseError("Air India departure-date control was not found")
        await self.human_delay(0.8, 1.5)
        if not await self._submit_search(page):
            raise ScraperParseError("Air India search button was not found")
        await self.human_delay(4.0, 7.0)

        if self._intercepted_responses:
            records = self._parse_xhr_responses(route, travel_date)
            if records:
                return records

        return await self._parse_html(page, route, travel_date)

    async def _select_oneway(self, page: Page) -> None:
        try:
            await page.get_by_role("radio", name="One Way", exact=True).click(timeout=5_000)
            return
        except Exception:
            pass
        for sel in ["input[value='OW']", "label:has-text('One Way')", ".one-way", "[aria-label='One Way']"]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click()
                    await self.human_delay(0.5, 1.0)
                    return
            except Exception:
                continue

    async def _dismiss_cookie_banner(self, page: Page) -> None:
        for sel in [
            "#onetrust-accept-btn-handler",
            "button:has-text('Accept All')",
        ]:
            try:
                button = page.locator(sel).first
                if await button.count() and await button.is_visible():
                    await button.click(timeout=3_000)
                    return
            except Exception:
                continue

    async def _choose_airport(self, page: Page, field: str, iata: str) -> bool:
        """Use Air India's button-driven airport picker."""
        try:
            await page.get_by_role("button", name=field, exact=True).click(timeout=6_000)
            search = page.get_by_role("textbox", name="Search airport...", exact=True)
            await search.fill(iata, timeout=5_000)
            option = page.get_by_role(
                "button", name=re.compile(rf"^{re.escape(iata)}\b")
            ).first
            await option.click(timeout=6_000)
            return True
        except Exception:
            return False

    async def _fill_origin(self, page: Page, iata: str) -> bool:
        if await self._choose_airport(page, "FROM", iata):
            return True
        for sel in ["[placeholder*='From']", "[aria-label*='Origin']", "#origin", ".origin input"]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click()
                    await el.fill("")
                    await el.type(iata, delay=120)
                    await self.human_delay(1.0, 2.0)
                    await page.keyboard.press("ArrowDown")
                    await page.keyboard.press("Enter")
                    return True
            except Exception:
                continue
        return False

    async def _fill_destination(self, page: Page, iata: str) -> bool:
        if await self._choose_airport(page, "TO", iata):
            return True
        for sel in ["[placeholder*='To']", "[aria-label*='Destination']", "#destination", ".destination input"]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click()
                    await el.fill("")
                    await el.type(iata, delay=120)
                    await self.human_delay(1.0, 2.0)
                    await page.keyboard.press("ArrowDown")
                    await page.keyboard.press("Enter")
                    return True
            except Exception:
                continue
        return False

    async def _select_date(self, page: Page, travel_date: date) -> bool:
        try:
            await page.get_by_role("button", name=re.compile(r"^Depart\b")).first.click(
                timeout=6_000
            )
            if await self._click_calendar_date(page, travel_date):
                confirm = page.get_by_role("button", name="Confirm", exact=True)
                if await confirm.count() and await confirm.is_visible():
                    await confirm.click(timeout=5_000)
                return True
        except Exception:
            pass
        for sel in ["[aria-label*='Depart']", ".departure-date input", "#departureDate"]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click()
                    await self.human_delay(0.5, 1.0)
                    # Navigate calendar to click date
                    if await self._click_calendar_date(page, travel_date):
                        return True
            except Exception:
                continue
        return False

    async def _click_calendar_date(self, page: Page, target: date) -> bool:
        """Click the target date in a calendar widget."""
        month_name = target.strftime("%B %Y")
        try:
            month = page.get_by_role("heading", name=month_name, exact=True).first
            if await month.count():
                await month.locator("..").get_by_role(
                    "button", name=str(target.day), exact=True
                ).click(timeout=6_000)
                return True
        except Exception as exc:
            logger.debug("[air_india] Scoped calendar click failed: {}", exc)
        for label in (
            target.strftime("%A, %B %d, %Y"),
            target.strftime("%B %d, %Y"),
            target.strftime("%B %d"),
        ):
            try:
                day = page.locator(f"[aria-label*='{label}']").first
                if await day.count():
                    await day.click(timeout=4_000)
                    return True
            except Exception:
                continue
        return False

    async def _submit_search(self, page: Page) -> bool:
        for sel in [
            "button:has-text('Search')",
            "button:has-text('SEARCH')",
            "button[type='submit']",
            ".search-button",
            "#searchBtn",
        ]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click()
                    return True
            except Exception:
                continue
        return False

    def _parse_xhr_responses(self, route: Route, travel_date: date) -> list[FareRecord]:
        records: list[FareRecord] = []
        for resp in self._intercepted_responses:
            try:
                records.extend(self._extract_from_xhr(resp, route, travel_date))
            except Exception as exc:
                logger.debug("[air_india] XHR parse error: {}", exc)
        return records

    def _extract_from_xhr(self, data: dict, route: Route, travel_date: date) -> list[FareRecord]:
        records: list[FareRecord] = []

        # Air India typically returns a 'flightOptions' or 'Itineraries' array
        flights = (
            data.get("flightOptions")
            or data.get("itineraries")
            or data.get("Itineraries")
            or data.get("flights")
            or data.get("data", {}).get("flights")
            or []
        )

        for f in flights:
            try:
                record = self._parse_flight(f, route, travel_date)
                if record:
                    records.append(record)
            except Exception as exc:
                logger.debug("[air_india] Flight parse error: {}", exc)

        return records

    def _parse_flight(self, f: dict, route: Route, travel_date: date) -> Optional[FareRecord]:
        total = (
            f.get("totalFare") or f.get("TotalFare")
            or f.get("price", {}).get("total")
            or f.get("fare", {}).get("totalAmount")
        )
        if not total:
            return None

        base = float(f.get("baseFare") or f.get("base") or 0)
        total = float(total)
        taxes = total - base if base else 0

        segs = f.get("segments") or f.get("Segments") or []
        seg = segs[0] if segs else {}
        fn = seg.get("flightNumber") or f.get("flightNumber") or ""
        airline_code = "AI"  # Could also be "IX" for Air India Express

        # Detect Air India Express
        if fn.startswith("IX") or "Express" in f.get("operatingCarrier", ""):
            airline_code = "IX"
            airline_name = "Air India Express"
        else:
            airline_name = "Air India"

        return FareRecord(
            origin=route.origin,
            destination=route.destination,
            travel_date=travel_date,
            airline=airline_name,
            airline_code=airline_code,
            flight_number=fn,
            departure_time=(seg.get("departureTime") or "")[:5],
            arrival_time=(seg.get("arrivalTime") or "")[:5],
            duration_minutes=int(f.get("durationInMinutes") or f.get("duration") or 0),
            stops=max(0, len(segs) - 1),
            fare_class=f.get("cabinClass") or f.get("fareClass") or "Economy",
            base_fare=base,
            taxes_fees=taxes,
            total_fare=total,
            currency="INR",
            raw=f,
        )

    async def _parse_html(self, page: Page, route: Route, travel_date: date) -> list[FareRecord]:
        records: list[FareRecord] = []
        found = await self.wait_for_results(
            page,
            ".flight-result, .flight-card, [class*='FlightResult'], [class*='flight-row']",
            timeout=25_000,
        )
        if not found:
            logger.warning("[air_india] No HTML results found.")
            return records

        cards = await page.query_selector_all(".flight-result, .flight-card, [class*='flight-row']")
        for card in cards:
            try:
                text = await card.inner_text()
                price_m = re.search(r"₹\s*([\d,]+)", text)
                fn_m = re.search(r"AI[- ]?(\d{3,4})", text)
                if not price_m:
                    continue
                total = float(price_m.group(1).replace(",", ""))
                times = re.findall(r"\b(\d{2}:\d{2})\b", text)
                records.append(
                    FareRecord(
                        origin=route.origin,
                        destination=route.destination,
                        travel_date=travel_date,
                        airline="Air India",
                        airline_code="AI",
                        flight_number=f"AI-{fn_m.group(1)}" if fn_m else "",
                        departure_time=times[0] if times else "",
                        arrival_time=times[1] if len(times) > 1 else "",
                        total_fare=total,
                        currency="INR",
                    )
                )
            except Exception as exc:
                logger.debug("[air_india] HTML card error: {}", exc)

        return records
