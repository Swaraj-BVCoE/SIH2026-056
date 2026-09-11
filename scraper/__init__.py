"""
scraper/__init__.py
"""
from scraper.airlines import AIRLINE_SCRAPERS
from scraper.otas import OTA_SCRAPERS
from scraper.base_scraper import BaseScraper, FareRecord, ScraperBlocked, ScraperParseError, ScraperNetworkError
from scraper.browser import BrowserPool
from scraper.proxy import proxy_pool

ALL_SCRAPERS = AIRLINE_SCRAPERS + OTA_SCRAPERS

__all__ = [
    "AIRLINE_SCRAPERS",
    "OTA_SCRAPERS",
    "ALL_SCRAPERS",
    "BaseScraper",
    "FareRecord",
    "ScraperBlocked",
    "ScraperParseError",
    "ScraperNetworkError",
    "BrowserPool",
    "proxy_pool",
]
