"""
scraper/airlines/akasa.py
──────────────────────────
Akasa Air direct website scraper (akasaair.com).

Strategy: XHR API Interception (primary)
  Akasa uses a REST API internally — their React frontend fetches
  flight data via a clean JSON endpoint. We capture this via response interception.
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
    "flightSearch",
    "availability",
    "search",
    "api/v1/flight",
    "api/v2/flight",
    "AkasaAir",
    "akasaair",
]

SEARCH_URLS = (
    "https://www.akasaair.com/flight-booking",
    "https://www.akasaair.com/",
)


class AkasaScraper(BaseScraper):
    SOURCE_PORTAL = "akasa_direct"

    async def _fetch(self, page: Page, route: Route, travel_date: date) -> list[FareRecord]:
        self.setup_xhr_intercept(page, INTERCEPT_PATTERNS)

        await navigate_to_working_page(
            page, SEARCH_URLS, "akasa", expected_terms=("search", "book", "flight")
        )

        await self.check_for_block(page)
        await self.human_delay(2.0, 3.5)

        await self._select_oneway(page)
        if not await self._fill_origin(page, route.origin):
            raise ScraperParseError("Akasa origin control was not found")
        await self.human_delay(1.0, 2.0)
        if not await self._fill_destination(page, route.destination):
            raise ScraperParseError("Akasa destination control was not found")
        await self.human_delay(1.0, 2.0)
        if not await self._select_date(page, travel_date):
            raise ScraperParseError("Akasa departure-date control was not found")
        await self.human_delay(0.5, 1.2)
        if not await self._submit_search(page):
            raise ScraperParseError("Akasa search button was not found")
        await self.human_delay(4.0, 6.0)

        if self._intercepted_responses:
            records = self._parse_xhr_responses(route, travel_date)
            if records:
                return records

        return await self._parse_html(page, route, travel_date)

    async def _select_oneway(self, page: Page) -> None:
        for sel in [
            "label:has-text('One-way')", "label:has-text('One Way')",
            "input[value='oneway']", "input[value='OW']",
            "[data-id='one-way']",
        ]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click()
                    return
            except Exception:
                continue

    async def _fill_origin(self, page: Page, iata: str) -> bool:
        for sel in [
            "#From", "input#From",
            "[placeholder*='From']", "[placeholder*='Origin']",
            "[aria-label*='From']", ".from-input input", "#fromCity",
        ]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click()
                    await el.fill("")
                    await el.type(iata, delay=110)
                    await self.human_delay(1.0, 2.0)
                    try:
                        await page.get_by_text(iata, exact=True).first.click(timeout=4_000)
                    except Exception:
                        await page.keyboard.press("ArrowDown")
                        await page.keyboard.press("Enter")
                    return True
            except Exception:
                continue
        return False

    async def _fill_destination(self, page: Page, iata: str) -> bool:
        for sel in [
            "#To", "input#To",
            "[placeholder*='To']", "[placeholder*='Destination']",
            "[aria-label*='To']", ".to-input input", "#toCity",
        ]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click()
                    await el.fill("")
                    await el.type(iata, delay=110)
                    await self.human_delay(1.0, 2.0)
                    try:
                        await page.get_by_text(iata, exact=True).first.click(timeout=4_000)
                    except Exception:
                        await page.keyboard.press("ArrowDown")
                        await page.keyboard.press("Enter")
                    return True
            except Exception:
                continue
        return False

    async def _select_date(self, page: Page, travel_date: date) -> bool:
        for sel in [
            "button:has-text('Select departure date')",
            "input[placeholder='Departure date']",
            "[aria-label*='Depart']", "[placeholder*='Date']",
            ".date-input", "#departDate",
        ]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click()
                    await self.human_delay(0.5, 1.0)
                    # Try to click target date in calendar
                    month_str = travel_date.strftime("%B")
                    for day_sel in [
                        f"[aria-label*='{month_str}'][aria-label*='{travel_date.day}'][aria-label*='{travel_date.year}']",
                        f"button:has-text('{travel_date.day}')",
                    ]:
                        day = page.locator(day_sel).first
                        if await day.count() and await day.is_visible():
                            await day.click(timeout=5_000)
                            return True
            except Exception:
                continue
        return False

    async def _submit_search(self, page: Page) -> bool:
        for sel in [
            "button:has-text('Search Flights')",
            "button:has-text('Search')",
            "button[type='submit']",
            ".search-btn",
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
                logger.debug("[akasa] XHR parse error: {}", exc)
        return records

    def _extract_from_xhr(self, data: dict, route: Route, travel_date: date) -> list[FareRecord]:
        records: list[FareRecord] = []
        if not isinstance(data, dict):
            return records
        nested = data.get("data")
        nested_flights = nested.get("flights") if isinstance(nested, dict) else None
        flights = (
            data.get("flights") or data.get("Flights")
            or data.get("itineraries") or nested_flights
            or []
        )
        if not isinstance(flights, list):
            return records

        # Akasa currently uses Navitaire/New Skies. Its availability payload
        # nests journeys under trips[].journeysAvailableByMarket["DEL|BOM"].
        if not flights:
            flights = list(self._find_navitaire_journeys(data))
        for f in flights:
            try:
                record = self._parse_flight(f, route, travel_date)
                if record:
                    records.append(record)
            except Exception:
                continue
        return records

    def _find_navitaire_journeys(self, value):
        """Yield journey dictionaries without treating reference-data lists as flights."""
        if isinstance(value, dict):
            markets = value.get("journeysAvailableByMarket")
            if isinstance(markets, dict):
                for journeys in markets.values():
                    if isinstance(journeys, list):
                        for journey in journeys:
                            if isinstance(journey, dict) and isinstance(journey.get("segments"), list):
                                yield journey
            for nested in value.values():
                yield from self._find_navitaire_journeys(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from self._find_navitaire_journeys(nested)

    def _parse_flight(self, f: dict, route: Route, travel_date: date) -> Optional[FareRecord]:
        total = (
            f.get("totalFare") or f.get("price", {}).get("total")
            or f.get("fare", {}).get("total") or f.get("amount")
        )
        navitaire_fare = None
        navitaire_base = 0.0
        if not total:
            fare_options = []
            for segment in f.get("segments") or []:
                fare_options.extend(segment.get("fares") or [])
            priced_options: list[tuple[float, float, dict]] = []
            for fare in fare_options:
                passenger_fares = fare.get("passengerFares") or []
                if not passenger_fares:
                    continue
                passenger_fare = passenger_fares[0]
                base = float(passenger_fare.get("fareAmount") or 0)
                charges = passenger_fare.get("serviceCharges") or []
                charge_total = sum(
                    float(charge.get("amount") or 0)
                    for charge in charges
                    if isinstance(charge, dict)
                )
                candidate_total = max(base, charge_total)
                if candidate_total > 0:
                    priced_options.append((candidate_total, base, fare))
            if priced_options:
                total, navitaire_base, navitaire_fare = min(priced_options, key=lambda item: item[0])
        if not total:
            return None

        base = float(f.get("baseFare") or f.get("base") or navitaire_base or 0)
        total = float(total)

        segs = f.get("segments") or []
        seg = segs[0] if segs else {}
        designator = seg.get("designator") or f.get("designator") or {}
        identifier = seg.get("identifier") or {}
        flight_number = identifier.get("identifier") or seg.get("flightNumber") or f.get("flightNumber", "")
        fare_class = (
            (navitaire_fare or {}).get("productClass")
            or (navitaire_fare or {}).get("fareClassOfService")
            or f.get("cabinClass")
            or "Economy"
        )

        return FareRecord(
            origin=route.origin,
            destination=route.destination,
            travel_date=travel_date,
            airline="Akasa Air",
            airline_code="QP",
            flight_number=f"QP-{flight_number}" if flight_number else "",
            departure_time=(seg.get("departureTime") or designator.get("departure") or "")[-8:-3],
            arrival_time=(seg.get("arrivalTime") or designator.get("arrival") or "")[-8:-3],
            duration_minutes=int(f.get("duration") or f.get("durationInMinutes") or 0),
            stops=max(0, len(segs) - 1),
            fare_class=fare_class,
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
            ".flight-card, [class*='FlightCard'], [class*='flight-result']",
            timeout=20_000,
        )
        if not found:
            logger.warning("[akasa] No HTML results found.")
            return records

        cards = await page.query_selector_all(".flight-card, [class*='FlightCard']")
        for card in cards:
            try:
                text = await card.inner_text()
                price_m = re.search(r"₹\s*([\d,]+)", text)
                fn_m = re.search(r"QP[- ]?(\d{3,4})", text)
                if not price_m:
                    continue
                total = float(price_m.group(1).replace(",", ""))
                times = re.findall(r"\b(\d{2}:\d{2})\b", text)
                records.append(FareRecord(
                    origin=route.origin,
                    destination=route.destination,
                    travel_date=travel_date,
                    airline="Akasa Air",
                    airline_code="QP",
                    flight_number=f"QP-{fn_m.group(1)}" if fn_m else "",
                    departure_time=times[0] if times else "",
                    arrival_time=times[1] if len(times) > 1 else "",
                    total_fare=total,
                    currency="INR",
                ))
            except Exception:
                continue
        return records
