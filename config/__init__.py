"""
config/__init__.py
"""
from config.settings import settings
from config.routes import ROUTE_BASKET, AIRPORTS, Route, get_route, list_routes

__all__ = ["settings", "ROUTE_BASKET", "AIRPORTS", "Route", "get_route", "list_routes"]
