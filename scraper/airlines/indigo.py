"""
scraper/airlines/indigo.py
───────────────────────────
IndiGo direct website scraper (goindigo.in).

Strategy: Direct URL navigation + XHR Interception
  Navigate directly to the search results URL — no form filling needed.
  IndiGo's React frontend makes JSON API calls; we intercept those.
  Fallback: full-page text extraction with regex.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

from loguru import logger
from playwright.async_api import Page

from config.routes import Route
from scraper.base_scraper import BaseScraper, FareRecord, ScraperBlocked, ScraperParseError

# ── XHR patterns to intercept ─────────────────────────────────────────────────
INTERCEPT_PATTERNS = [
    "availability",
    "Availability",
    "searchflights",
    "search-flights",
    "flightSearch",
    "api/v1",
    "api/v2",
    "6e",
]

# ── Direct search URL templates (try in order) ────────────────────────────────
SEARCH_URL_TEMPLATES = [
    # Pattern 1 — goindigo booking page with query params
    (
        "https://www.goindigo.in/flight-booking.html?"
        "origin={origin}&destination={dest}&departDate={date_dmy}"
        "&tripType=O&paxType=ADT&paxCount=1&cabinClass=ECONOMY"
    ),
    # Pattern 2 — alternate format used in some versions
    (
        "https://www.goindigo.in/flight-booking.html?"
        "from={origin}&to={dest}&depart={date_ymd}"
        "&adults=1&children=0&infants=0&tripType=O"
    ),
    # Pattern 3 — book.goindigo.in subdomain
    (
        "https://book.goindigo.in/booking/flight-list?"
        "orig={origin}&dest={dest}&deptDt={date_ymd}"
        "&adult=1&child=0&infant=0&cabinClass=Y&tripType=O"
    ),
]


class IndigoScraper(BaseScraper):
    SOURCE_PORTAL = "indigo_direct"

    async def _fetch(self, page: Page, route: Route, travel_date: date) -> list[FareRecord]:
        # Set up XHR interception BEFORE navigating
        self.setup_xhr_intercept(page, INTERCEPT_PATTERNS)

        date_ymd = travel_date.strftime("%Y-%m-%d")
        date_dmy = travel_date.strftime("%d%m%Y")

        # Try each URL pattern until one loads flight data
        navigated = False
        for template in SEARCH_URL_TEMPLATES:
            url = template.format(
                origin=route.origin,
                dest=route.destination,
                date_ymd=date_ymd,
                date_dmy=date_dmy,
            )
            try:
                logger.debug("[indigo_direct] Trying URL: {}", url)
                await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                navigated = True
                break
            except Exception as exc:
                logger.debug("[indigo_direct] URL failed: {} — {}", url, exc)
                continue

        if not navigated:
            raise ScraperParseError("All IndiGo URL patterns failed to load")

        await self.check_for_block(page)

        # Wait longer — IndiGo React app needs time to fetch and render results
        await self.human_delay(6.0, 10.0)

        # Try to wait for network to settle
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass  # Proceed anyway after timeout

        # ── Try XHR interception first ────────────────────────────────────────
        if self._intercepted_responses:
            logger.debug(
                "[indigo_direct] {} XHR responses intercepted",
                len(self._intercepted_responses),
            )
            records = self._parse_xhr_responses(route, travel_date)
            if records:
                return records
        else:
            logger.debug("[indigo_direct] No XHR responses intercepted — trying HTML")

        # ── Fallback: HTML card parsing ───────────────────────────────────────
        records = await self._parse_html(page, route, travel_date)
        if records:
            return records

        # ── Last resort: full-page text regex extraction ──────────────────────
        return await self._parse_fullpage_text(page, route, travel_date)

    # ── XHR Response Parser ───────────────────────────────────────────────────
    def _parse_xhr_responses(self, route: Route, travel_date: date) -> list[FareRecord]:
        records: list[FareRecord] = []
        for resp_data in self._intercepted_responses:
            try:
                extracted = self._extract_from_xhr(resp_data, route, travel_date)
                records.extend(extracted)
            except Exception as exc:
                logger.debug("[indigo_direct] XHR parse error: {}", exc)
        return records

    def _extract_from_xhr(
        self, data: dict, route: Route, travel_date: date
    ) -> list[FareRecord]:
        records: list[FareRecord] = []

        # Pattern 1: itineraries[] array
        itineraries = (
            data.get("itineraries")
            or data.get("Itineraries")
            or data.get("data", {}).get("itineraries")
            or data.get("result", {}).get("itineraries")
            or []
        )
        for itin in itineraries:
            try:
                fare = self._parse_itinerary(itin, route, travel_date)
                if fare:
                    records.append(fare)
            except Exception as exc:
                logger.debug("[indigo_direct] Itinerary parse error: {}", exc)

        # Pattern 2: flights[] array
        flights = (
            data.get("flights")
            or data.get("Flights")
            or data.get("data", {}).get("flights")
            or []
        )
        for flight in flights:
            try:
                fare = self._parse_flight_block(flight, route, travel_date)
                if fare:
                    records.append(fare)
            except Exception as exc:
                logger.debug("[indigo_direct] Flight block parse error: {}", exc)

        return records

    def _parse_itinerary(
        self, itin: dict, route: Route, travel_date: date
    ) -> Optional[FareRecord]:
        total = (
            itin.get("totalFare")
            or itin.get("TotalFare")
            or itin.get("price", {}).get("total")
            or itin.get("fare", {}).get("totalAmount")
        )
        if not total:
            return None

        base = (
            itin.get("baseFare")
            or itin.get("BaseFare")
            or itin.get("fare", {}).get("baseFare")
            or 0
        )
        taxes = float(total) - float(base) if base else 0.0

        segments = itin.get("segments") or itin.get("Segments") or []
        seg = segments[0] if segments else {}

        flight_num = seg.get("flightNumber") or seg.get("FlightNumber") or ""
        dep_time = seg.get("departureTime") or seg.get("DepartureTime") or ""
        arr_time = seg.get("arrivalTime") or seg.get("ArrivalTime") or ""
        duration = (
            itin.get("durationInMinutes")
            or itin.get("duration")
            or seg.get("duration")
            or 0
        )
        stops = len(segments) - 1 if segments else itin.get("stops", 0)

        dep_time = dep_time[:5] if len(dep_time) >= 5 else dep_time
        arr_time = arr_time[:5] if len(arr_time) >= 5 else arr_time

        return FareRecord(
            origin=route.origin,
            destination=route.destination,
            travel_date=travel_date,
            airline="IndiGo",
            airline_code="6E",
            flight_number=f"6E-{flight_num}" if flight_num else "",
            departure_time=dep_time,
            arrival_time=arr_time,
            duration_minutes=int(duration),
            stops=int(stops),
            fare_class=itin.get("fareClass") or itin.get("cabinClass") or "Economy",
            base_fare=float(base),
            taxes_fees=float(taxes),
            total_fare=float(total),
            currency="INR",
            seats_left=int(itin.get("seatsAvailable") or itin.get("seatsLeft") or 0),
            raw=itin,
        )

    def _parse_flight_block(
        self, flight: dict, route: Route, travel_date: date
    ) -> Optional[FareRecord]:
        price = flight.get("price") or flight.get("fare") or {}
        total = price.get("total") or price.get("totalAmount") or flight.get("totalFare")
        if not total:
            return None

        return FareRecord(
            origin=route.origin,
            destination=route.destination,
            travel_date=travel_date,
            airline="IndiGo",
            airline_code="6E",
            flight_number=f"6E-{flight.get('flightNumber', '')}",
            departure_time=(flight.get("departureTime") or "")[:5],
            arrival_time=(flight.get("arrivalTime") or "")[:5],
            duration_minutes=int(flight.get("duration", 0)),
            stops=int(flight.get("stops", 0)),
            fare_class=flight.get("class") or "Economy",
            base_fare=float(price.get("base", 0)),
            taxes_fees=float(price.get("taxes", 0)),
            total_fare=float(total),
            currency="INR",
            raw=flight,
        )

    # ── HTML Card Parser ──────────────────────────────────────────────────────
    async def _parse_html(
        self, page: Page, route: Route, travel_date: date
    ) -> list[FareRecord]:
        records: list[FareRecord] = []

        # Broad set of selectors — catches current and future class names
        card_selectors = [
            ".flight-card",
            ".result-item",
            "[class*='FlightCard']",
            "[class*='flight-card']",
            "[class*='flightCard']",
            "[class*='flight_card']",
            "[data-testid='flight-card']",
            "[class*='listing']",
            "[class*='result']",
        ]
        selector_str = ", ".join(card_selectors)

        found = await self.wait_for_results(page, selector_str, timeout=20_000)
        if not found:
            logger.debug("[indigo_direct] No flight cards found via HTML selectors")
            return records

        cards = await page.query_selector_all(selector_str)
        for card in cards:
            try:
                text = await card.inner_text()
                fare = self._parse_card_text(text, route, travel_date)
                if fare:
                    records.append(fare)
            except Exception as exc:
                logger.debug("[indigo_direct] Card parse error: {}", exc)

        return records

    # ── Full-page text fallback ───────────────────────────────────────────────
    async def _parse_fullpage_text(
        self, page: Page, route: Route, travel_date: date
    ) -> list[FareRecord]:
        """
        Last resort: grab ALL text on the page and use regex to find
        price + time patterns. Works even if class names are completely unknown.
        """
        records: list[FareRecord] = []
        try:
            full_text = await page.inner_text("body")
        except Exception:
            logger.warning("[indigo_direct] Could not extract full page text")
            return records

        # Find all ₹ prices
        price_matches = re.findall(r"₹\s*([\d,]+)", full_text)
        # Find all HH:MM times
        time_matches = re.findall(r"\b(\d{2}:\d{2})\b", full_text)
        # Find all 6E flight numbers
        fn_matches = re.findall(r"6E[- ]?(\d{3,4})", full_text)

        if not price_matches:
            logger.warning("[indigo_direct] No prices found on page — site may have changed layout")
            return records

        logger.debug(
            "[indigo_direct] Full-page text found {} prices, {} times, {} flight numbers",
            len(price_matches), len(time_matches), len(fn_matches),
        )

        for i, price_str in enumerate(price_matches):
            try:
                total = float(price_str.replace(",", ""))
                if total < 500 or total > 200_000:
                    continue  # Skip non-fare numbers

                dep = time_matches[i * 2] if i * 2 < len(time_matches) else ""
                arr = time_matches[i * 2 + 1] if i * 2 + 1 < len(time_matches) else ""
                fn = f"6E-{fn_matches[i]}" if i < len(fn_matches) else ""

                records.append(FareRecord(
                    origin=route.origin,
                    destination=route.destination,
                    travel_date=travel_date,
                    airline="IndiGo",
                    airline_code="6E",
                    flight_number=fn,
                    departure_time=dep,
                    arrival_time=arr,
                    total_fare=total,
                    currency="INR",
                ))
            except Exception:
                continue

        # Deduplicate by price
        seen_prices: set[float] = set()
        unique: list[FareRecord] = []
        for r in records:
            if r.total_fare not in seen_prices:
                seen_prices.add(r.total_fare)
                unique.append(r)

        if unique:
            logger.info("[indigo_direct] Full-page extraction found {} fares", len(unique))
        else:
            logger.warning("[indigo_direct] Full-page extraction found no valid fares")

        return unique

    def _parse_card_text(
        self, text: str, route: Route, travel_date: date
    ) -> Optional[FareRecord]:
        price_match = re.search(r"₹\s*([\d,]+)", text)
        if not price_match:
            price_match = re.search(r"INR\s*([\d,]+)", text)
        if not price_match:
            return None

        total_fare = float(price_match.group(1).replace(",", ""))
        fn_match = re.search(r"6E[- ]?(\d{3,4})", text)
        flight_num = f"6E-{fn_match.group(1)}" if fn_match else ""
        time_matches = re.findall(r"\b(\d{2}:\d{2})\b", text)
        dep_time = time_matches[0] if len(time_matches) > 0 else ""
        arr_time = time_matches[1] if len(time_matches) > 1 else ""

        return FareRecord(
            origin=route.origin,
            destination=route.destination,
            travel_date=travel_date,
            airline="IndiGo",
            airline_code="6E",
            flight_number=flight_num,
            departure_time=dep_time,
            arrival_time=arr_time,
            total_fare=total_fare,
            currency="INR",
        )
