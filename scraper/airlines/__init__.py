"""
scraper/airlines/__init__.py
"""
from scraper.airlines.indigo import IndigoScraper
from scraper.airlines.air_india import AirIndiaScraper
from scraper.airlines.akasa import AkasaScraper
from scraper.airlines.spicejet import SpiceJetScraper

AIRLINE_SCRAPERS = [
    IndigoScraper,
    AirIndiaScraper,
    AkasaScraper,
    SpiceJetScraper,
]

__all__ = [
    "IndigoScraper",
    "AirIndiaScraper",
    "AkasaScraper",
    "SpiceJetScraper",
    "AIRLINE_SCRAPERS",
]
