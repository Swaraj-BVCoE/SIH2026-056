"""
scraper/airlines/spicejet.py
─────────────────────────────
SpiceJet direct website scraper (spicejet.com).

Strategy: XHR + HTML hybrid
  SpiceJet mixes server-rendered HTML with JSON API calls.
  We try XHR interception first; fall back to HTML parsing.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

from loguru import logger
from playwright.async_api import Page

from config.routes import Route
from scraper.base_scraper import BaseScraper, FareRecord, ScraperParseError
from scraper.page_health import navigate_to_working_page

INTERCEPT_PATTERNS = [
    "flightAvailability",
    "AvailabilityRequest",
    "searchFlights",
    "api/Search",
    "api/search",
    "GetItinerary",
]

SEARCH_URLS = (
    "https://book.spicejet.com/",
    "https://www.spicejet.com/",
)


class SpiceJetScraper(BaseScraper):
    SOURCE_PORTAL = "spicejet_direct"
    ORIGIN_SELECT = "#ControlGroupSearchView_AvailabilitySearchInputSearchVieworiginStation1"
    DESTINATION_SELECT = "#ControlGroupSearchView_AvailabilitySearchInputSearchViewdestinationStation1"
    DAY_SELECT = "#ControlGroupSearchView_AvailabilitySearchInputSearchView_DropDownListMarketDay1"
    MONTH_SELECT = "#ControlGroupSearchView_AvailabilitySearchInputSearchView_DropDownListMarketMonth1"

    async def _fetch(self, page: Page, route: Route, travel_date: date) -> list[FareRecord]:
        self.setup_xhr_intercept(page, INTERCEPT_PATTERNS)

        await navigate_to_working_page(
            page, SEARCH_URLS, "spicejet", expected_terms=("search", "book", "flight")
        )

        await self.check_for_block(page)
        await self.human_delay(2.0, 3.5)

        await self._select_oneway(page)
        if not await self._fill_origin(page, route.origin):
            raise ScraperParseError("SpiceJet origin control was not found")
        await self.human_delay(1.0, 2.0)
        if not await self._fill_destination(page, route.destination):
            raise ScraperParseError("SpiceJet destination control was not found")
        await self.human_delay(1.0, 2.0)
        if not await self._select_date(page, travel_date):
            raise ScraperParseError("SpiceJet departure-date control was not found")
        await self.human_delay(0.8, 1.5)
        if not await self._submit_search(page):
            raise ScraperParseError("SpiceJet search button was not found")
        await self.human_delay(5.0, 8.0)

        if self._intercepted_responses:
            records = self._parse_xhr_responses(route, travel_date)
            if records:
                return records

        return await self._parse_html(page, route, travel_date)

    async def _select_oneway(self, page: Page) -> None:
        for sel in [
            "label:has-text('One Way')", "input[value='O']",
            "[data-trip-type='OW']", "#oneWay",
        ]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click()
                    return
            except Exception:
                continue

    async def _fill_origin(self, page: Page, iata: str) -> bool:
        try:
            control = page.locator(self.ORIGIN_SELECT)
            if await control.count():
                await control.select_option(iata)
                return await control.input_value() == iata
        except Exception:
            pass
        for sel in [
            "[data-origin]", "[placeholder*='From']",
            "#origin-ip-target", ".origin-input",
        ]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click()
                    await el.fill("")
                    await el.type(iata, delay=120)
                    await self.human_delay(1.0, 1.5)
                    await page.keyboard.press("ArrowDown")
                    await page.keyboard.press("Enter")
                    return True
            except Exception:
                continue
        return False

    async def _fill_destination(self, page: Page, iata: str) -> bool:
        try:
            control = page.locator(self.DESTINATION_SELECT)
            if await control.count():
                await control.select_option(iata)
                return await control.input_value() == iata
        except Exception:
            pass
        for sel in [
            "[data-destination]", "[placeholder*='To']",
            "#destination-ip-target", ".destination-input",
        ]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click()
                    await el.fill("")
                    await el.type(iata, delay=120)
                    await self.human_delay(1.0, 1.5)
                    await page.keyboard.press("ArrowDown")
                    await page.keyboard.press("Enter")
                    return True
            except Exception:
                continue
        return False

    async def _select_date(self, page: Page, travel_date: date) -> bool:
        # The current SpiceJet page keeps native ASP.NET day/month fields behind
        # the styled date box. Set those authoritative form controls directly.
        try:
            selected = await page.evaluate(
                """({daySelector, monthSelector, inputSelector, day, month, display}) => {
                    const setSelect = (selector, value) => {
                        const el = document.querySelector(selector);
                        if (!el) return false;
                        if (![...el.options].some(option => option.value === value)) {
                            el.add(new Option(value, value));
                        }
                        el.value = value;
                        el.dispatchEvent(new Event('input', {bubbles: true}));
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                        return el.value === value;
                    };
                    const dayOk = setSelect(daySelector, day);
                    const monthOk = setSelect(monthSelector, month);
                    const input = document.querySelector(inputSelector);
                    if (input) {
                        input.value = display;
                        input.dispatchEvent(new Event('input', {bubbles: true}));
                        input.dispatchEvent(new Event('change', {bubbles: true}));
                    }
                    return dayOk && monthOk;
                }""",
                {
                    "daySelector": self.DAY_SELECT,
                    "monthSelector": self.MONTH_SELECT,
                    "inputSelector": "#custom_date_picker_id_1",
                    "day": str(travel_date.day),
                    "month": travel_date.strftime("%Y-%m"),
                    "display": travel_date.strftime("%m/%d"),
                },
            )
            if selected:
                return True
        except Exception as exc:
            logger.debug("[spicejet] Native date fields failed: {}", exc)
        try:
            await page.click(".datePickerInput, [class*='DatePicker'], #dep-date")
            await self.human_delay(0.5, 1.0)
            month_str = travel_date.strftime("%B")
            day_sel = f"[aria-label*='{month_str}'] td:has-text('{travel_date.day}')"
            el = page.locator(day_sel).first
            if await el.count() > 0:
                await el.click()
                return True
        except Exception as exc:
            logger.debug("[spicejet] Date select error: {}", exc)
        return False

    async def _submit_search(self, page: Page) -> bool:
        for sel in [
            "button:has-text('Search Flights')",
            "button:has-text('Search')",
            "#ControlGroupSearchView_AvailabilitySearchInputSearchView_ButtonSubmit",
            "#search-btn",
            ".search-button",
            "button[type='submit']",
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
                logger.debug("[spicejet] XHR parse error: {}", exc)
        return records

    def _extract_from_xhr(self, data: dict, route: Route, travel_date: date) -> list[FareRecord]:
        records: list[FareRecord] = []
        if not isinstance(data, dict):
            return records
        # SpiceJet commonly uses 'Itinerary' or 'Trip' structures
        flights = (
            data.get("Itinerary") or data.get("Trips")
            or data.get("flights") or data.get("FlightList")
            or []
        )
        if isinstance(flights, dict):
            flights = flights.get("Flights") or []

        for f in flights:
            try:
                record = self._parse_flight(f, route, travel_date)
                if record:
                    records.append(record)
            except Exception:
                continue
        return records

    def _parse_flight(self, f: dict, route: Route, travel_date: date) -> Optional[FareRecord]:
        total = (
            f.get("TotalFare") or f.get("totalFare")
            or f.get("Fare", {}).get("TotalFare")
            or f.get("price", {}).get("total")
        )
        if not total:
            return None

        base = float(
            f.get("BaseFare") or f.get("baseFare")
            or f.get("Fare", {}).get("BaseFare") or 0
        )
        total = float(total)
        segs = f.get("Segments") or f.get("segments") or []
        seg = segs[0] if segs else {}
        fn = seg.get("FlightNumber") or seg.get("flightNumber") or f.get("FlightNo") or ""

        return FareRecord(
            origin=route.origin,
            destination=route.destination,
            travel_date=travel_date,
            airline="SpiceJet",
            airline_code="SG",
            flight_number=f"SG-{fn}" if fn else "",
            departure_time=(seg.get("DepartureTime") or seg.get("departureTime") or "")[:5],
            arrival_time=(seg.get("ArrivalTime") or seg.get("arrivalTime") or "")[:5],
            duration_minutes=int(
                f.get("DurationInMinutes") or f.get("duration")
                or f.get("Duration") or 0
            ),
            stops=max(0, len(segs) - 1),
            fare_class=f.get("CabinClass") or f.get("cabinClass") or "Economy",
            base_fare=base,
            taxes_fees=total - base,
            total_fare=total,
            currency="INR",
            raw=f,
        )

    async def _parse_html(self, page: Page, route: Route, travel_date: date) -> list[FareRecord]:
        records: list[FareRecord] = []
        found = await self.wait_for_results(
            page,
            ".flight-card, .FlightList, [class*='flight-row'], .sj-flight",
            timeout=25_000,
        )
        if not found:
            logger.warning("[spicejet] No HTML results found.")
            return records

        cards = await page.query_selector_all(".flight-card, .sj-flight, [class*='flight-row']")
        for card in cards:
            try:
                text = await card.inner_text()
                price_m = re.search(r"₹\s*([\d,]+)", text)
                fn_m = re.search(r"SG[- ]?(\d{3,4})", text)
                if not price_m:
                    continue
                total = float(price_m.group(1).replace(",", ""))
                times = re.findall(r"\b(\d{2}:\d{2})\b", text)
                records.append(FareRecord(
                    origin=route.origin,
                    destination=route.destination,
                    travel_date=travel_date,
                    airline="SpiceJet",
                    airline_code="SG",
                    flight_number=f"SG-{fn_m.group(1)}" if fn_m else "",
                    departure_time=times[0] if times else "",
                    arrival_time=times[1] if len(times) > 1 else "",
                    total_fare=total,
                    currency="INR",
                ))
            except Exception:
                continue
        return records
