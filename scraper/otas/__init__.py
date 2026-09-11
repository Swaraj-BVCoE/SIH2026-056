"""
scraper/otas/__init__.py
"""
from scraper.otas.makemytrip import MakeMyTripScraper
from scraper.otas.cleartrip import CleartripScraper
from scraper.otas.ixigo import IxigoScraper
from scraper.otas.easemytrip import EaseMyTripScraper

OTA_SCRAPERS = [
    MakeMyTripScraper,
    CleartripScraper,
    IxigoScraper,
    EaseMyTripScraper,
]

__all__ = [
    "MakeMyTripScraper",
    "CleartripScraper",
    "IxigoScraper",
    "EaseMyTripScraper",
    "OTA_SCRAPERS",
]
