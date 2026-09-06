"""
Spothole API client — https://spothole.app/api/v1

Polls /spots and /solar periodically.  Provides callbacks for new spots
and solar data.  Uses httpx with a shared AsyncClient for connection reuse.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Optional

import httpx

from .models import DXSpot, SolarConditions

log = logging.getLogger(__name__)

_BASE = "https://spothole.app/api/v1"


class SpotholeClient:
    """
    Thin async wrapper around the Spothole REST API.

    All calls are fire-and-read — no streaming.  The caller (DXClusterManager)
    owns the polling schedule and retry logic.
    """

    def __init__(self, base_url: str = _BASE, timeout_s: float = 10.0) -> None:
        self._base = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout_s)

    async def close(self) -> None:
        await self._client.aclose()

    async def get_spots(
        self,
        *,
        max_age: int = 3600,
        limit: int = 200,
        band: Optional[str] = None,
        mode: Optional[str] = None,
        continent: Optional[str] = None,
        dedupe: bool = True,
        received_since: Optional[float] = None,
    ) -> list[DXSpot]:
        """Fetch recent spots, optionally filtered."""
        params: dict = {"max_age": max_age, "limit": limit, "dedupe": str(dedupe).lower()}
        if band:
            params["band"] = band
        if mode:
            params["mode"] = mode
        if continent:
            params["dx_continent"] = continent
        if received_since is not None:
            params["received_since"] = received_since

        try:
            r = await self._client.get(f"{self._base}/spots", params=params)
            r.raise_for_status()
            return [DXSpot.from_api(d) for d in r.json()]
        except Exception as exc:
            log.warning("Spothole /spots error: %s", exc)
            return []

    async def get_solar(self) -> Optional[SolarConditions]:
        """Fetch current solar and propagation conditions."""
        try:
            r = await self._client.get(f"{self._base}/solar")
            r.raise_for_status()
            return SolarConditions.from_api(r.json())
        except Exception as exc:
            log.warning("Spothole /solar error: %s", exc)
            return None
