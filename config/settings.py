"""
config/settings.py
──────────────────
Central configuration loaded from environment variables (.env file).
All other modules import from here — never use os.getenv() directly.
"""

from __future__ import annotations

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator

# ── Project root ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'airfare.db'}"

    # ── Proxy ────────────────────────────────────────────────────────────────
    proxy_enabled: bool = False
    proxy_url: str = ""
    proxy_username: str = ""
    proxy_password: str = ""

    # ── Scraper behaviour ────────────────────────────────────────────────────
    headless: bool = True
    max_concurrent_scrapers: int = 1   # Keep at 1 — concurrent requests trigger IP bans
    request_delay_min: float = 3.0    # seconds — be polite to avoid rate limits
    request_delay_max: float = 7.0    # seconds
    scrape_retry_attempts: int = 2
    scrape_retry_delay: int = 30     # seconds between retries

    # ── Scheduling ───────────────────────────────────────────────────────────
    scrape_cron: str = "0 6,12,18 * * *"

    # ── Look-ahead window ────────────────────────────────────────────────────
    lookahead_days_min: int = 1
    lookahead_days_max: int = 60
    advance_purchase_windows: str = "1,7,15,30,45"
    scheduled_routes_per_cycle: int = 6
    stale_run_hours: int = 6

    freshness_fresh_hours: int = 6
    freshness_delayed_hours: int = 24
    index_base_period: str = "earliest-observed-period"
    index_weights_file: Path = BASE_DIR / "config" / "index_weights.csv"

    # ── Logging ──────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_dir: Path = BASE_DIR / "logs"

    @field_validator("log_dir", mode="before")
    @classmethod
    def resolve_log_dir(cls, v: str | Path) -> Path:
        return BASE_DIR / v if not Path(str(v)).is_absolute() else Path(str(v))

    @property
    def proxy_server(self) -> str | None:
        """Returns full proxy URL with credentials if proxy is enabled."""
        if not self.proxy_enabled or not self.proxy_url:
            return None
        if self.proxy_username and self.proxy_password:
            proto, rest = self.proxy_url.split("://", 1)
            return f"{proto}://{self.proxy_username}:{self.proxy_password}@{rest}"
        return self.proxy_url

    @property
    def data_dir(self) -> Path:
        return BASE_DIR / "data"

    @property
    def lead_time_days(self) -> list[int]:
        """Configured CPI lead-time observations, sanitized and sorted."""
        values = []
        for value in self.advance_purchase_windows.split(","):
            try:
                day = int(value.strip())
            except ValueError:
                continue
            if self.lookahead_days_min <= day <= self.lookahead_days_max:
                values.append(day)
        return sorted(set(values)) or [1, 7, 15, 30, 45]


# ── Singleton instance ───────────────────────────────────────────────────────
settings = Settings()

# Ensure required directories exist
settings.log_dir.mkdir(parents=True, exist_ok=True)
settings.data_dir.mkdir(parents=True, exist_ok=True)
