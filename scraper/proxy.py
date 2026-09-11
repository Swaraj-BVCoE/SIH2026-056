"""
scraper/proxy.py
─────────────────
Proxy rotation pool manager.

Features:
  - Loads proxies from settings or a proxy list file
  - Round-robin + random selection modes
  - Health-checks proxies and blacklists failing ones
  - Falls back to direct (no-proxy) mode in dev
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx
from loguru import logger

from config.settings import settings

# ── Proxy list file (optional) ───────────────────────────────────────────────
PROXY_LIST_FILE = Path(__file__).resolve().parent.parent / "proxies.txt"


@dataclass
class ProxyEntry:
    url: str                          # Full proxy URL with credentials
    failures: int = 0
    last_used: float = field(default_factory=time.time)
    is_healthy: bool = True

    @property
    def display(self) -> str:
        """Masked URL for logging (hides credentials)."""
        try:
            proto, rest = self.url.split("://", 1)
            if "@" in rest:
                creds, host = rest.rsplit("@", 1)
                return f"{proto}://***@{host}"
        except Exception:
            pass
        return self.url


class ProxyPool:
    """
    A rotating proxy pool.

    Priority order for proxy sources:
      1. PROXY_URL in settings (single proxy)
      2. proxies.txt file (one proxy per line)
      3. No proxy (direct connection)
    """

    def __init__(self) -> None:
        self._proxies: list[ProxyEntry] = []
        self._index: int = 0
        self._lock = asyncio.Lock()

    def load(self) -> None:
        """Load proxies from settings and/or proxies.txt."""
        proxies: list[str] = []

        if not settings.proxy_enabled:
            logger.info("Proxy disabled — using direct connection.")
            return

        # Single proxy from env
        if settings.proxy_server:
            proxies.append(settings.proxy_server)

        # Additional proxies from file
        if PROXY_LIST_FILE.exists():
            lines = PROXY_LIST_FILE.read_text().strip().splitlines()
            for line in lines:
                line = line.strip()
                if line and not line.startswith("#"):
                    proxies.append(line)

        if not proxies:
            logger.warning(
                "Proxy enabled but no proxies found. "
                "Set PROXY_URL in .env or create proxies.txt"
            )
            return

        self._proxies = [ProxyEntry(url=p) for p in set(proxies)]
        logger.info("Loaded {} proxy/proxies into pool.", len(self._proxies))

    async def get_proxy(self) -> Optional[str]:
        """
        Returns the next healthy proxy URL, or None if no proxies available.
        Uses round-robin with random jitter to distribute load.
        """
        if not self._proxies:
            return None  # Direct connection

        healthy = [p for p in self._proxies if p.is_healthy]
        if not healthy:
            logger.warning("All proxies are blacklisted! Resetting health status.")
            for p in self._proxies:
                p.is_healthy = True
                p.failures = 0
            healthy = self._proxies[:]

        async with self._lock:
            self._index = (self._index + 1) % len(healthy)
            proxy = healthy[self._index]
            proxy.last_used = time.time()

        return proxy.url

    def mark_failure(self, proxy_url: str) -> None:
        """Increment failure count; blacklist after 3 consecutive failures."""
        for proxy in self._proxies:
            if proxy.url == proxy_url:
                proxy.failures += 1
                if proxy.failures >= 3:
                    proxy.is_healthy = False
                    logger.warning(
                        "Proxy blacklisted after {} failures: {}",
                        proxy.failures,
                        proxy.display,
                    )
                break

    def mark_success(self, proxy_url: str) -> None:
        """Reset failure count on success."""
        for proxy in self._proxies:
            if proxy.url == proxy_url:
                proxy.failures = 0
                break

    async def health_check_all(self, timeout: int = 10) -> None:
        """Ping all proxies and update their health status."""
        logger.info("Running proxy health checks...")
        tasks = [self._check_one(p, timeout) for p in self._proxies]
        await asyncio.gather(*tasks)
        healthy = sum(1 for p in self._proxies if p.is_healthy)
        logger.info("{}/{} proxies are healthy.", healthy, len(self._proxies))

    async def _check_one(self, proxy: ProxyEntry, timeout: int) -> None:
        test_url = "https://httpbin.org/ip"
        try:
            async with httpx.AsyncClient(
                proxy=proxy.url, timeout=timeout, verify=False
            ) as client:
                resp = await client.get(test_url)
                if resp.status_code == 200:
                    proxy.is_healthy = True
                    proxy.failures = 0
                    logger.debug("Proxy OK: {}", proxy.display)
                else:
                    proxy.is_healthy = False
        except Exception as exc:
            proxy.is_healthy = False
            logger.debug("Proxy FAILED: {} — {}", proxy.display, exc)

    def stats(self) -> dict:
        return {
            "total": len(self._proxies),
            "healthy": sum(1 for p in self._proxies if p.is_healthy),
            "blacklisted": sum(1 for p in self._proxies if not p.is_healthy),
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
proxy_pool = ProxyPool()
proxy_pool.load()
