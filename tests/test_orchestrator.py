from datetime import date

import pytest

from config.routes import Route
from config.settings import settings
from orchestrator.job_runner import build_job_plan, default_travel_dates
from scraper.base_scraper import BaseScraper, ScraperBlocked, ScraperParseError


class SourceA(BaseScraper):
    SOURCE_PORTAL = "source_a"

    async def _fetch(self, page, route, travel_date):
        return []


class SourceB(BaseScraper):
    SOURCE_PORTAL = "source_b"

    async def _fetch(self, page, route, travel_date):
        return []


def test_default_dates_use_required_lead_time_windows(monkeypatch):
    monkeypatch.setattr(settings, "advance_purchase_windows", "1,7,15,30,45")
    today = date(2026, 9, 9)
    assert [(item - today).days for item in default_travel_dates(today)] == [1, 7, 15, 30, 45]


def test_job_plan_is_complete_and_route_fair():
    routes = [Route("DEL", "BOM"), Route("BOM", "DEL"), Route("DEL", "BLR")]
    plan = build_job_plan([SourceA, SourceB], routes, [date(2026, 9, 10)])
    assert len(plan) == 6
    assert [job[1].code for job in plan[:3]] == [route.code for route in routes]
    assert {job[0].SOURCE_PORTAL for job in plan[:3]} == {"source_a", "source_b"}
    assert len({(job[0].SOURCE_PORTAL, job[1].code, job[2]) for job in plan}) == 6


@pytest.mark.asyncio
async def test_empty_fetch_is_no_data(monkeypatch):
    monkeypatch.setattr(settings, "scrape_retry_attempts", 1)
    scraper = SourceA()
    assert await scraper.scrape(object(), Route("DEL", "BOM"), date(2026, 9, 10)) == []
    assert scraper.last_status == "NO_DATA"


@pytest.mark.asyncio
async def test_blocked_and_parse_failures_are_not_success(monkeypatch):
    monkeypatch.setattr(settings, "scrape_retry_attempts", 1)
    monkeypatch.setattr(settings, "scrape_retry_delay", 0)

    class Blocked(SourceA):
        async def _fetch(self, page, route, travel_date):
            raise ScraperBlocked("captcha present")

    class Broken(SourceA):
        async def _fetch(self, page, route, travel_date):
            raise ScraperParseError("layout changed")

    blocked = Blocked()
    broken = Broken()
    await blocked.scrape(object(), Route("DEL", "BOM"), date(2026, 9, 10))
    await broken.scrape(object(), Route("DEL", "BOM"), date(2026, 9, 10))
    assert blocked.last_status == "BLOCKED"
    assert broken.last_status == "FAILED"
