"""Backward-compatible import path; the only FastAPI application lives in api.main."""

from api.main import app

__all__ = ["app"]
