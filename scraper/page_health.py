"""Small page-health checks shared by browser-based source adapters."""

from __future__ import annotations

from collections.abc import Sequence

from loguru import logger
from playwright.async_api import Page

from scraper.base_scraper import ScraperParseError


BAD_PAGE_MARKERS = (
    "404 not found",
    "page not found",
    "the page you requested could not be found",
    "this site can’t be reached",
    "this site can't be reached",
)


async def page_is_usable(page: Page, expected_terms: Sequence[str] = ()) -> tuple[bool, str]:
    """Reject HTTP-success placeholders and obvious error pages."""
    try:
        body = (await page.locator("body").inner_text(timeout=8_000)).strip()
    except Exception as exc:
        return False, f"body could not be read: {exc}"

    compact = " ".join(body.lower().split())
    if compact in {"200-ok", "200 ok", "ok"}:
        return False, f"placeholder response: {body[:80]}"
    if any(marker in compact for marker in BAD_PAGE_MARKERS):
        return False, f"error page: {body[:120]}"
    if len(compact) < 20:
        return False, f"page content is unexpectedly short: {body[:80]}"
    if expected_terms and not any(term.lower() in compact for term in expected_terms):
        return False, "booking/search controls were not found in page text"
    return True, ""


async def navigate_to_working_page(
    page: Page,
    urls: Sequence[str],
    source_name: str,
    *,
    expected_terms: Sequence[str] = (),
    timeout: int = 45_000,
) -> str:
    """Try current official entry points and return the first usable one."""
    failures: list[str] = []
    for url in urls:
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            status = response.status if response else None
            if status in {403, 429}:
                failures.append(f"{url}: HTTP {status}")
                continue
            if status is not None and status >= 400:
                failures.append(f"{url}: HTTP {status}")
                continue
            usable, reason = await page_is_usable(page, expected_terms)
            if usable:
                return url
            failures.append(f"{url}: {reason}")
        except Exception as exc:
            failures.append(f"{url}: {exc}")
        logger.warning("[{}] Entry page failed; trying fallback: {}", source_name, failures[-1])

    detail = "; ".join(failures)
    raise ScraperParseError(f"No usable {source_name} booking page. {detail}")
