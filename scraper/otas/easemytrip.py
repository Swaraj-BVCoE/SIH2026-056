"""
scraper/otas/easemytrip.py
───────────────────────────
EaseMyTrip OTA scraper (easemytrip.com).

Strategy: Playwright + XHR interception + HTML fallback
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

from loguru import logger
from playwright.async_api import Page

from config.routes import Route
from scraper.base_scraper import BaseScraper, FareRecord, ScraperParseError

INTERCEPT_PATTERNS = [
    "easemytrip",
    "flightSearch",
    "SearchFlight",
    "availability",
    "api/flight",
]

SEARCH_URL_TEMPLATE = (
    "https://flight.easemytrip.com/FlightList/Index?"
    "from={origin}&to={dest}&date={date}&pax=1-0-0&isNearBy=False&cabin=1"
)
SEARCH_DATE_FORMAT = "%d/%m/%Y"

AIRLINE_MAP = {
    "6E": "IndiGo", "AI": "Air India", "IX": "Air India Express",
    "QP": "Akasa Air", "SG": "SpiceJet", "UK": "Vistara",
}


class EaseMyTripScraper(BaseScraper):
    SOURCE_PORTAL = "easemytrip"

    async def _fetch(self, page: Page, route: Route, travel_date: date) -> list[FareRecord]:
        self.setup_xhr_intercept(page, INTERCEPT_PATTERNS)

        # EaseMyTrip expects day/month/year. Month/day generates invalid dates
        # such as 09/16/2026 and the misleading "no flights found" overlay.
        date_str = travel_date.strftime(SEARCH_DATE_FORMAT)
        search_url = SEARCH_URL_TEMPLATE.format(
            origin=route.origin,
            dest=route.destination,
            date=date_str,
        )

        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=50_000)
        except Exception as exc:
            raise ScraperParseError(f"Failed to load EaseMyTrip page: {exc}") from exc

        await self.check_for_block(page)
        await self.human_delay(5.0, 8.0)

        if self._intercepted_responses:
            records = self._parse_xhr_responses(route, travel_date)
            if records:
                return records

        return await self._parse_html(page, route, travel_date)

    def _parse_xhr_responses(self, route: Route, travel_date: date) -> list[FareRecord]:
        records: list[FareRecord] = []
        for resp in self._intercepted_responses:
            try:
                records.extend(self._extract_from_xhr(resp, route, travel_date))
            except Exception as exc:
                logger.debug("[easemytrip] XHR parse: {}", exc)
        return records

    def _extract_from_xhr(self, data: dict, route: Route, travel_date: date) -> list[FareRecord]:
        records: list[FareRecord] = []
        flights = (
            data.get("FlightDetails") or data.get("flightDetails")
            or data.get("flights") or data.get("Results") or []
        )
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
            or f.get("Price") or f.get("price")
        )
        if not total:
            return None

        base = float(f.get("BaseFare") or f.get("baseFare") or 0)
        total = float(total)
        airline_code = (f.get("AirlineCode") or f.get("airlineCode") or "").upper()
        fn = f.get("FlightNumber") or f.get("flightNumber") or ""

        return FareRecord(
            origin=route.origin,
            destination=route.destination,
            travel_date=travel_date,
            airline=AIRLINE_MAP.get(airline_code, airline_code or "Unknown"),
            airline_code=airline_code,
            flight_number=f"{airline_code}-{fn}" if fn else "",
            departure_time=(f.get("DepartureTime") or f.get("departureTime") or "")[:5],
            arrival_time=(f.get("ArrivalTime") or f.get("arrivalTime") or "")[:5],
            duration_minutes=int(f.get("Duration") or f.get("duration") or 0),
            stops=int(f.get("Stops") or f.get("stops") or 0),
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
            ".flt-list-main, .flightItem, [class*='flt-card']",
            timeout=25_000,
        )
        if not found:
            logger.warning("[easemytrip] No HTML results found.")
            return records

        cards = await page.query_selector_all(".flt-list-main li, .flightItem, [class*='flt-card']")
        for card in cards:
            try:
                text = await card.inner_text()
                price_m = re.search(r"₹\s*([\d,]+)", text)
                if not price_m:
                    continue
                total = float(price_m.group(1).replace(",", ""))
                times = re.findall(r"\b(\d{2}:\d{2})\b", text)
                detected_code = ""
                for code in AIRLINE_MAP:
                    if code in text:
                        detected_code = code
                        break
                records.append(FareRecord(
                    origin=route.origin,
                    destination=route.destination,
                    travel_date=travel_date,
                    airline=AIRLINE_MAP.get(detected_code, "Unknown"),
                    airline_code=detected_code,
                    departure_time=times[0] if times else "",
                    arrival_time=times[1] if len(times) > 1 else "",
                    total_fare=total,
                    currency="INR",
                ))
            except Exception:
                continue
        return records
