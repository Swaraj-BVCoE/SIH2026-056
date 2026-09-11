"""
scraper/otas/makemytrip.py
───────────────────────────
MakeMyTrip OTA scraper (makemytrip.com).

Strategy: XHR API Interception (primary)
  MMT's React frontend calls a JSON API at api.makemytrip.com.
  We intercept these responses. The advantage: we get fares from
  ALL airlines in one query (IndiGo, Air India, Vistara, etc.)

Key XHR endpoints (observed via DevTools):
  - /api/mmt/FLIGHTS/v4/listing/  (POST — main search API)
  - Response: { tripInfos: [{ sI: [...segments], totalPriceList: [...] }] }
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

from loguru import logger
from playwright.async_api import Page

from config.routes import Route
from scraper.base_scraper import BaseScraper, FareRecord, ScraperParseError
from scraper.page_health import navigate_to_working_page, page_is_usable

INTERCEPT_PATTERNS = [
    "api.makemytrip.com",
    "FLIGHTS",
    "listing",
    "airSearch",
    "flightSearch",
]

SEARCH_URL_TEMPLATE = (
    "https://www.makemytrip.com/flight/search?"
    "tripType=O&itinerary={origin}-{dest}-{date}&paxType=A-1_C-0_I-0"
    "&cabinClass=E&sTime={stime}&sSpeed=5"
)
LANDING_URL = "https://www.makemytrip.com/flights/"

# Airline code → name mapping
AIRLINE_MAP = {
    "6E": "IndiGo",
    "AI": "Air India",
    "IX": "Air India Express",
    "QP": "Akasa Air",
    "SG": "SpiceJet",
    "UK": "Vistara",
    "G8": "Go First",
    "I5": "AirAsia India",
}


class MakeMyTripScraper(BaseScraper):
    SOURCE_PORTAL = "makemytrip"

    async def _fetch(self, page: Page, route: Route, travel_date: date) -> list[FareRecord]:
        self.setup_xhr_intercept(page, INTERCEPT_PATTERNS)

        # MMT expects date in DDMMYYYY format for the itinerary parameter
        date_str = travel_date.strftime("%d%m%Y")
        import time as _time
        search_url = SEARCH_URL_TEMPLATE.format(
            origin=route.origin,
            dest=route.destination,
            date=date_str,
            stime=int(_time.time() * 1000),
        )

        loaded_url = await navigate_to_working_page(
            page,
            (search_url, LANDING_URL),
            "makemytrip",
            expected_terms=("flight", "from", "search"),
            timeout=50_000,
        )

        if loaded_url == LANDING_URL:
            await self._dismiss_login_modal(page)
            if not await self._search_from_landing(page, route, travel_date):
                raise ScraperParseError(
                    "MakeMyTrip returned a placeholder page and its booking form could not be used"
                )

        await self.check_for_block(page)

        # MMT takes 8–12s to fully load all fares via JS
        try:
            await page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception:
            pass
        await self.human_delay(5.0, 9.0)

        if self._intercepted_responses:
            logger.debug("[makemytrip] {} XHR responses captured", len(self._intercepted_responses))
            records = self._parse_xhr_responses(route, travel_date)
            if records:
                logger.success("[makemytrip] {} fares via XHR interception", len(records))
                return records
        else:
            logger.debug("[makemytrip] No XHR captured — trying HTML")

        usable, reason = await page_is_usable(page)
        if not usable:
            raise ScraperParseError(f"MakeMyTrip result page is unusable: {reason}")

        records = await self._parse_html(page, route, travel_date)
        if records:
            return records

        return await self._parse_fullpage_text(page, route, travel_date)

    async def _search_from_landing(
        self, page: Page, route: Route, travel_date: date
    ) -> bool:
        """Use the public booking form when MakeMyTrip rejects a deep link."""
        try:
            await page.get_by_text("One Way", exact=True).first.click(timeout=5_000)
        except Exception:
            pass

        async def choose(
            selectors: tuple[str, ...], editable_selectors: tuple[str, ...], value: str
        ) -> bool:
            for selector in selectors:
                try:
                    control = page.locator(selector).first
                    if await control.count() == 0:
                        continue
                    await control.click()
                    for editable_selector in editable_selectors:
                        editable = page.locator(editable_selector).last
                        if await editable.count() == 0 or not await editable.is_visible():
                            continue
                        await editable.fill(value)
                        await self.human_delay(0.8, 1.4)
                        await page.keyboard.press("ArrowDown")
                        await page.keyboard.press("Enter")
                        return True
                except Exception:
                    continue
            return False

        origin_ok = await choose(
            ("#fromCity", "[data-cy='fromCity']"),
            ("input[placeholder='From']", "input[placeholder*='city']"),
            route.origin,
        )
        destination_ok = await choose(
            ("#toCity", "[data-cy='toCity']"),
            ("input[placeholder='To']", "input[placeholder*='city']"),
            route.destination,
        )
        if not origin_ok or not destination_ok:
            return False

        try:
            await page.locator("#departure, [data-cy='departureDate']").first.click()
            if not await self._click_departure_date(page, travel_date):
                return False
            await page.locator(
                "a.primaryBtn:has-text('Search'), button:has-text('Search')"
            ).first.click(timeout=8_000)
            return True
        except Exception as exc:
            logger.debug("[makemytrip] Landing-form search failed: {}", exc)
            return False

    async def _dismiss_login_modal(self, page: Page) -> None:
        """Close MMT's optional login wall so the public search form is usable."""
        for selector in (
            "[data-cy='closeModal']",
            ".commonModal__close",
            ".loginModal .modalClose",
            "button[aria-label*='Close']",
            "span[aria-label*='Close']",
        ):
            try:
                close = page.locator(selector).first
                if await close.count() and await close.is_visible():
                    await close.click(timeout=3_000)
                    await self.human_delay(0.3, 0.7)
                    return
            except Exception:
                continue

    async def _click_departure_date(self, page: Page, travel_date: date) -> bool:
        month = travel_date.strftime("%b")
        year = str(travel_date.year)
        day = str(travel_date.day)
        labels = (
            travel_date.strftime("%a %b %d %Y"),
            f"{travel_date.strftime('%a')} {month} {day} {year}",
        )
        for label in labels:
            try:
                cell = page.locator(f"[aria-label='{label}']").first
                if await cell.count() and await cell.is_visible():
                    await cell.click(timeout=5_000)
                    return True
            except Exception:
                continue
        try:
            cell = page.locator(
                f".DayPicker-Day[aria-label*='{month}'][aria-label*='{day}'][aria-label*='{year}']"
            ).first
            if await cell.count() and await cell.is_visible():
                await cell.click(timeout=5_000)
                return True
        except Exception:
            pass
        try:
            panels = page.locator(".DayPicker-Month")
            for index in range(await panels.count()):
                panel = panels.nth(index)
                caption = await panel.locator(".DayPicker-Caption").inner_text()
                if travel_date.strftime("%B %Y") not in caption:
                    continue
                candidate = panel.get_by_text(day, exact=True).first
                if await candidate.count() and await candidate.is_visible():
                    await candidate.click(timeout=5_000)
                    return True
        except Exception as exc:
            logger.debug("[makemytrip] Date picker selection failed: {}", exc)
        return False

    # ── XHR Parsing ──────────────────────────────────────────────────────────
    def _parse_xhr_responses(self, route: Route, travel_date: date) -> list[FareRecord]:
        records: list[FareRecord] = []
        for resp in self._intercepted_responses:
            try:
                records.extend(self._extract_from_xhr(resp, route, travel_date))
            except Exception as exc:
                logger.debug("[makemytrip] XHR parse error: {}", exc)
        return records

    def _extract_from_xhr(self, data: dict, route: Route, travel_date: date) -> list[FareRecord]:
        """
        Parse MMT's tripInfos[] structure.
        Each tripInfo has segments (sI[]) + pricing options (totalPriceList[]).
        """
        records: list[FareRecord] = []
        if not isinstance(data, dict):
            return records
        trip_infos = (
            data.get("data", {}).get("tripInfos")
            or data.get("tripInfos")
            or data.get("results")
            or []
        )

        for trip in trip_infos:
            try:
                segments = trip.get("sI") or trip.get("segments") or []
                price_list = trip.get("totalPriceList") or trip.get("prices") or []

                if not segments or not price_list:
                    continue

                first_seg = segments[0]
                last_seg = segments[-1]

                airline_code = (
                    first_seg.get("fD", {}).get("aI", {}).get("code")
                    or first_seg.get("airlineCode")
                    or ""
                ).upper()

                flight_num = (
                    first_seg.get("fD", {}).get("fN")
                    or first_seg.get("flightNumber")
                    or ""
                )
                dep_time = (first_seg.get("dt") or first_seg.get("departureTime") or "")
                arr_time = (last_seg.get("at") or last_seg.get("arrivalTime") or "")
                duration = trip.get("tt") or trip.get("totalTime") or 0
                stops = len(segments) - 1

                # Extract cheapest price from price_list
                for price_info in price_list:
                    try:
                        fd = price_info.get("fd") or {}
                        total = (
                            price_info.get("totalFare")
                            or fd.get("ADULT", {}).get("fC", {}).get("TF")
                            or fd.get("totalFare")
                        )
                        base = (
                            fd.get("ADULT", {}).get("fC", {}).get("BF")
                            or fd.get("baseFare")
                            or 0
                        )
                        cabin = (
                            fd.get("ADULT", {}).get("cc")
                            or price_info.get("cabinClass")
                            or "Economy"
                        )

                        if not total:
                            continue

                        records.append(FareRecord(
                            origin=route.origin,
                            destination=route.destination,
                            travel_date=travel_date,
                            airline=AIRLINE_MAP.get(airline_code, airline_code),
                            airline_code=airline_code,
                            flight_number=f"{airline_code}-{flight_num}" if flight_num else "",
                            departure_time=dep_time[:5] if dep_time else "",
                            arrival_time=arr_time[:5] if arr_time else "",
                            duration_minutes=int(duration),
                            stops=stops,
                            fare_class=cabin,
                            base_fare=float(base),
                            taxes_fees=float(total) - float(base),
                            total_fare=float(total),
                            currency="INR",
                            raw=trip,
                        ))
                    except Exception:
                        continue
            except Exception as exc:
                logger.debug("[makemytrip] Trip parse error: {}", exc)

        return records

    # ── HTML Fallback ─────────────────────────────────────────────────────────
    async def _parse_html(self, page: Page, route: Route, travel_date: date) -> list[FareRecord]:
        records: list[FareRecord] = []
        sel = (
            ".listingCard, .flight-card-wrapper, [class*='listingCard'], "
            "[class*='listing-card'], [class*='flight-card'], [data-testid*='listing'], "
            "[data-testid*='flight']"
        )
        found = await self.wait_for_results(page, sel, timeout=25_000)
        if not found:
            logger.debug("[makemytrip] No HTML listing cards found")
            return records

        cards = await page.query_selector_all(sel)
        for card in cards:
            try:
                text = await card.inner_text()
                record = self._parse_card_text(text, route, travel_date)
                if record:
                    records.append(record)
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
            logger.warning("[makemytrip] No prices found on page")
            return records

        seen: set[float] = set()
        for i, ps in enumerate(price_matches):
            try:
                total = float(ps.replace(",", ""))
                if total < 500 or total > 200_000 or total in seen:
                    continue
                seen.add(total)
                detected_airline = "Unknown"
                detected_code = ""
                for code, name in AIRLINE_MAP.items():
                    if name.lower() in full_text.lower() or code in full_text:
                        detected_airline = name
                        detected_code = code
                        break
                dep = time_matches[i * 2] if i * 2 < len(time_matches) else ""
                arr = time_matches[i * 2 + 1] if i * 2 + 1 < len(time_matches) else ""
                records.append(FareRecord(
                    origin=route.origin,
                    destination=route.destination,
                    travel_date=travel_date,
                    airline=detected_airline,
                    airline_code=detected_code,
                    departure_time=dep,
                    arrival_time=arr,
                    total_fare=total,
                    currency="INR",
                ))
            except Exception:
                continue

        if records:
            logger.info("[makemytrip] Full-page extraction found {} fares", len(records))
        else:
            logger.warning("[makemytrip] Full-page extraction found no valid fares")
        return records

    def _parse_card_text(
        self, text: str, route: Route, travel_date: date
    ) -> Optional[FareRecord]:
        price_m = re.search(r"₹\s*([\d,]+)", text)
        if not price_m:
            return None
        total = float(price_m.group(1).replace(",", ""))

        # Detect airline
        detected_airline = "Unknown"
        detected_code = ""
        for code, name in AIRLINE_MAP.items():
            if name.lower() in text.lower() or code in text:
                detected_airline = name
                detected_code = code
                break

        times = re.findall(r"\b(\d{2}:\d{2})\b", text)
        return FareRecord(
            origin=route.origin,
            destination=route.destination,
            travel_date=travel_date,
            airline=detected_airline,
            airline_code=detected_code,
            departure_time=times[0] if times else "",
            arrival_time=times[1] if len(times) > 1 else "",
            total_fare=total,
            currency="INR",
        )
