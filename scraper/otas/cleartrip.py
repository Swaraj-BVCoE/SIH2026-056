"""
scraper/otas/cleartrip.py
──────────────────────────
Cleartrip OTA scraper (cleartrip.com).

Strategy: XHR/GraphQL API Interception
  Cleartrip uses a GraphQL-style internal API.
  We intercept the POST responses to /api/flights/results.
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
    "api/flights",
    "flights/results",
    "search/flights",
    "cleartrip",
    "graphql",
    "availability",
]

SEARCH_URL_TEMPLATE = (
    "https://www.cleartrip.com/flights/results?"
    "adults=1&childs=0&infants=0&class=Economy"
    "&depart_date={date}&from={origin}&to={dest}&intl=n&origin={origin}&destination={dest}"
)

AIRLINE_MAP = {
    "6E": "IndiGo", "AI": "Air India", "IX": "Air India Express",
    "QP": "Akasa Air", "SG": "SpiceJet", "UK": "Vistara",
}


class CleartripScraper(BaseScraper):
    SOURCE_PORTAL = "cleartrip"

    async def _fetch(self, page: Page, route: Route, travel_date: date) -> list[FareRecord]:
        self.setup_xhr_intercept(page, INTERCEPT_PATTERNS)

        date_str = travel_date.strftime("%d/%m/%Y")
        search_url = SEARCH_URL_TEMPLATE.format(
            origin=route.origin,
            dest=route.destination,
            date=date_str,
        )

        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=50_000)
        except Exception as exc:
            raise ScraperParseError(f"Failed to load Cleartrip page: {exc}") from exc

        await self.check_for_block(page)

        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass
        await self.human_delay(4.0, 8.0)

        if self._intercepted_responses:
            logger.debug("[cleartrip] {} XHR responses captured", len(self._intercepted_responses))
            records = self._parse_xhr_responses(route, travel_date)
            if records:
                return records
        else:
            logger.debug("[cleartrip] No XHR captured — trying HTML")

        records = await self._parse_html(page, route, travel_date)
        if records:
            return records

        return await self._parse_fullpage_text(page, route, travel_date)

    def _parse_xhr_responses(self, route: Route, travel_date: date) -> list[FareRecord]:
        records: list[FareRecord] = []
        for resp in self._intercepted_responses:
            try:
                records.extend(self._extract_from_xhr(resp, route, travel_date))
            except Exception as exc:
                logger.debug("[cleartrip] XHR parse error: {}", exc)
        return records

    def _extract_from_xhr(self, data: dict, route: Route, travel_date: date) -> list[FareRecord]:
        records: list[FareRecord] = []
        # Cleartrip commonly structures as { results: { outbound: [...] } }
        flights = (
            data.get("results", {}).get("outbound")
            or data.get("flights")
            or data.get("data", {}).get("flights")
            or data.get("Flights")
            or []
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
        # Price paths
        total = (
            f.get("fare", {}).get("totalFare")
            or f.get("totalFare") or f.get("price")
            or f.get("amount") or f.get("lowestFare")
        )
        if not total:
            return None

        base = float(f.get("fare", {}).get("baseFare") or f.get("baseFare") or 0)
        total = float(total)

        segs = f.get("segments") or f.get("Segments") or []
        seg = segs[0] if segs else {}
        airline_code = (
            seg.get("carrier") or f.get("airlineCode")
            or f.get("carrier") or ""
        ).upper()

        fn = seg.get("flightNumber") or f.get("flightNumber") or ""

        return FareRecord(
            origin=route.origin,
            destination=route.destination,
            travel_date=travel_date,
            airline=AIRLINE_MAP.get(airline_code, airline_code or "Unknown"),
            airline_code=airline_code,
            flight_number=f"{airline_code}-{fn}" if fn else "",
            departure_time=(seg.get("departureTime") or f.get("departureTime") or "")[:5],
            arrival_time=(seg.get("arrivalTime") or f.get("arrivalTime") or "")[:5],
            duration_minutes=int(f.get("duration") or f.get("totalDuration") or 0),
            stops=max(0, len(segs) - 1),
            fare_class=f.get("cabinClass") or f.get("class") or "Economy",
            base_fare=base,
            taxes_fees=total - base,
            total_fare=total,
            currency="INR",
            raw=f,
        )

    async def _parse_html(self, page: Page, route: Route, travel_date: date) -> list[FareRecord]:
        records: list[FareRecord] = []
        sel = (
            ".flight-card, .FlightCard, [class*='flight-card'], [class*='FlightCard'], "
            "[class*='flight_card'], [class*='result'], [data-testid*='flight']"
        )
        found = await self.wait_for_results(page, sel, timeout=20_000)
        if not found:
            logger.debug("[cleartrip] No HTML card selectors matched")
            return records

        cards = await page.query_selector_all(sel)
        for card in cards:
            try:
                text = await card.inner_text()
                price_m = re.search(r"₹\s*([\d,]+)", text)
                if not price_m:
                    continue
                total = float(price_m.group(1).replace(",", ""))
                if total < 500 or total > 200_000:
                    continue
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

    async def _parse_fullpage_text(
        self, page: Page, route: Route, travel_date: date
    ) -> list[FareRecord]:
        """Last resort: regex over all body text to find prices."""
        records: list[FareRecord] = []
        try:
            full_text = await page.inner_text("body")
        except Exception:
            return records

        price_matches = re.findall(r"₹\s*([\d,]+)", full_text)
        time_matches = re.findall(r"\b(\d{2}:\d{2})\b", full_text)

        if not price_matches:
            logger.warning("[cleartrip] No prices found on page")
            return records

        seen: set[float] = set()
        for i, ps in enumerate(price_matches):
            try:
                total = float(ps.replace(",", ""))
                if total < 500 or total > 200_000 or total in seen:
                    continue
                seen.add(total)
                detected_code = ""
                for code in AIRLINE_MAP:
                    if code in full_text:
                        detected_code = code
                        break
                dep = time_matches[i * 2] if i * 2 < len(time_matches) else ""
                arr = time_matches[i * 2 + 1] if i * 2 + 1 < len(time_matches) else ""
                records.append(FareRecord(
                    origin=route.origin,
                    destination=route.destination,
                    travel_date=travel_date,
                    airline=AIRLINE_MAP.get(detected_code, "Unknown"),
                    airline_code=detected_code,
                    departure_time=dep,
                    arrival_time=arr,
                    total_fare=total,
                    currency="INR",
                ))
            except Exception:
                continue

        if records:
            logger.info("[cleartrip] Full-page extraction found {} fares", len(records))
        else:
            logger.warning("[cleartrip] Full-page extraction found no valid fares")
        return records
