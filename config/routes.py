"""
config/routes.py
────────────────
MoSPI representative city-pair basket for the Airfare Price Index.

Each route is stored as a namedtuple with IATA origin/destination codes
and a human-readable label. The IATA codes are validated against the
AIRPORTS registry below.

Extend ROUTE_BASKET to add or remove city pairs.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Route:
    origin: str        # IATA code (e.g. "DEL")
    destination: str   # IATA code (e.g. "BOM")

    @property
    def code(self) -> str:
        return f"{self.origin}-{self.destination}"

    @property
    def reverse(self) -> "Route":
        return Route(origin=self.destination, destination=self.origin)

    def __str__(self) -> str:
        return self.code


# ── Airport registry ─────────────────────────────────────────────────────────
AIRPORTS: dict[str, str] = {
    "DEL": "Indira Gandhi International Airport, New Delhi",
    "BOM": "Chhatrapati Shivaji Maharaj International Airport, Mumbai",
    "BLR": "Kempegowda International Airport, Bengaluru",
    "CCU": "Netaji Subhas Chandra Bose International Airport, Kolkata",
    "HYD": "Rajiv Gandhi International Airport, Hyderabad",
    "MAA": "Chennai International Airport, Chennai",
    "AMD": "Sardar Vallabhbhai Patel International Airport, Ahmedabad",
    "PNQ": "Pune Airport, Pune",
    "GOI": "Goa International Airport (Dabolim), Goa",
    "JAI": "Jaipur International Airport, Jaipur",
    "LKO": "Chaudhary Charan Singh International Airport, Lucknow",
    "PAT": "Jay Prakash Narayan International Airport, Patna",
    "BBI": "Biju Patnaik International Airport, Bhubaneswar",
    "COK": "Cochin International Airport, Kochi",
    "TRV": "Trivandrum International Airport, Thiruvananthapuram",
    "IXC": "Chandigarh International Airport, Chandigarh",
    "GAU": "Lokpriya Gopinath Bordoloi International Airport, Guwahati",
    "NAG": "Dr. Babasaheb Ambedkar International Airport, Nagpur",
    "VTZ": "Vishakhapatnam Airport, Visakhapatnam",
    "SXR": "Sheikh ul-Alam International Airport, Srinagar",
}


# ── MoSPI representative city-pair basket ────────────────────────────────────
# Based on Problem Statement #26056 — covers high-traffic domestic corridors
ROUTE_BASKET: List[Route] = [
    # Metro-to-Metro (Tier-1 corridors)
    Route("DEL", "BOM"),
    Route("BOM", "DEL"),
    Route("DEL", "BLR"),
    Route("BLR", "DEL"),
    Route("DEL", "CCU"),
    Route("CCU", "DEL"),
    Route("BOM", "BLR"),
    Route("BLR", "BOM"),
    Route("BOM", "CCU"),
    Route("CCU", "BOM"),
    Route("BLR", "CCU"),
    Route("CCU", "BLR"),

    # Metro-to-South
    Route("DEL", "HYD"),
    Route("HYD", "DEL"),
    Route("DEL", "MAA"),
    Route("MAA", "DEL"),
    Route("BOM", "HYD"),
    Route("HYD", "BOM"),
    Route("BOM", "MAA"),
    Route("MAA", "BOM"),
    Route("BLR", "HYD"),
    Route("HYD", "BLR"),

    # Metro-to-West
    Route("DEL", "AMD"),
    Route("AMD", "DEL"),
    Route("BOM", "AMD"),

    # Metro-to-East/Northeast
    Route("DEL", "GAU"),
    Route("GAU", "DEL"),
    Route("BOM", "PAT"),

    # Leisure & Tier-2
    Route("DEL", "GOI"),
    Route("BOM", "GOI"),
    Route("DEL", "JAI"),
    Route("DEL", "SXR"),
    Route("COK", "DEL"),
    Route("TRV", "DEL"),
]


def get_route(code: str) -> Route:
    """Look up a route by its code string, e.g. 'DEL-BOM'."""
    parts = code.upper().split("-")
    if len(parts) != 2:
        raise ValueError(f"Invalid route code '{code}'. Expected format: 'ORG-DST'")
    origin, destination = parts
    if origin not in AIRPORTS:
        raise ValueError(f"Unknown IATA code: {origin}")
    if destination not in AIRPORTS:
        raise ValueError(f"Unknown IATA code: {destination}")
    return Route(origin=origin, destination=destination)


def list_routes() -> List[str]:
    """Return a sorted list of all route codes in the basket."""
    return sorted(r.code for r in ROUTE_BASKET)
