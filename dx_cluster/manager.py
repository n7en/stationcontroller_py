"""
DXClusterManager — periodic Spothole polling + in-memory spot cache.

Usage::

    mgr = DXClusterManager.from_config(cfg)
    mgr.add_spots_callback(my_fn)          # called when new spots arrive
    await mgr.start()

    spots = mgr.spots()                    # list[dict] - most recent first
    solar = mgr.solar()                    # dict | None
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Callable, Optional

from .models import DXSpot, SolarConditions
from .spothole import SpotholeClient

log = logging.getLogger(__name__)

SpotsCallback = Callable[[list[DXSpot]], None]

_DEFAULT_SPOTS_LIMIT    = 200
_DEFAULT_SPOT_INTERVAL  = 60      # seconds
_DEFAULT_SOLAR_INTERVAL = 600     # seconds


class DXClusterManager:

    def __init__(
        self,
        client: SpotholeClient,
        spot_interval_s: float = _DEFAULT_SPOT_INTERVAL,
        solar_interval_s: float = _DEFAULT_SOLAR_INTERVAL,
        max_spots: int = _DEFAULT_SPOTS_LIMIT,
        band_filter: Optional[str] = None,
        continent_filter: Optional[str] = None,
    ) -> None:
        self._client = client
        self._spot_interval  = spot_interval_s
        self._solar_interval = solar_interval_s
        self._max_spots = max_spots
        self._band_filter      = band_filter
        self._continent_filter = continent_filter

        self._spots: deque[DXSpot] = deque(maxlen=max_spots)
        self._spot_ids: set[str]   = set()          # de-dupe
        self._solar: Optional[SolarConditions] = None

        self._spot_callbacks: list[SpotsCallback] = []
        self._last_received: Optional[float] = None  # for incremental fetches
        self._task_spots:  Optional[asyncio.Task] = None
        self._task_solar:  Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, cfg: dict) -> "DXClusterManager":
        base_url = cfg.get("base_url", "https://spothole.app/api/v1")
        client = SpotholeClient(
            base_url=base_url,
            timeout_s=float(cfg.get("timeout_s", 10.0)),
        )
        return cls(
            client=client,
            spot_interval_s=float(cfg.get("spot_interval_s", _DEFAULT_SPOT_INTERVAL)),
            solar_interval_s=float(cfg.get("solar_interval_s", _DEFAULT_SOLAR_INTERVAL)),
            max_spots=int(cfg.get("max_spots", _DEFAULT_SPOTS_LIMIT)),
            band_filter=cfg.get("band_filter"),
            continent_filter=cfg.get("continent_filter"),
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._task_spots = asyncio.create_task(self._poll_spots_loop(), name="dx_spots_poll")
        self._task_solar = asyncio.create_task(self._poll_solar_loop(), name="dx_solar_poll")
        log.info("DX cluster manager started (spots every %ds, solar every %ds)",
                 self._spot_interval, self._solar_interval)

    async def stop(self) -> None:
        for task in (self._task_spots, self._task_solar):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        await self._client.close()
        log.info("DX cluster manager stopped")

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def add_spots_callback(self, cb: SpotsCallback) -> None:
        """Register a callback invoked whenever new spots are fetched."""
        self._spot_callbacks.append(cb)

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def spots(self, limit: int = 100) -> list[dict]:
        """Return most recent *limit* spots as dicts (newest first)."""
        recs = list(self._spots)
        return [s.as_dict() for s in reversed(recs)][:limit]

    def solar(self) -> Optional[dict]:
        return self._solar.as_dict() if self._solar else None

    @property
    def enabled(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # Poll loops
    # ------------------------------------------------------------------

    async def _poll_spots_loop(self) -> None:
        # Initial fetch (no received_since filter — get current spots)
        await self._fetch_spots(initial=True)
        while True:
            await asyncio.sleep(self._spot_interval)
            await self._fetch_spots()

    async def _poll_solar_loop(self) -> None:
        await self._fetch_solar()
        while True:
            await asyncio.sleep(self._solar_interval)
            await self._fetch_solar()

    async def _fetch_spots(self, initial: bool = False) -> None:
        try:
            new_spots = await self._client.get_spots(
                max_age=3600,
                limit=self._max_spots,
                band=self._band_filter,
                continent=self._continent_filter,
                dedupe=True,
                received_since=None if initial else self._last_received,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("DX spot fetch failed: %s", exc)
            return

        fresh: list[DXSpot] = []
        for spot in new_spots:
            if spot.id and spot.id in self._spot_ids:
                continue
            if spot.id:
                self._spot_ids.add(spot.id)
            self._spots.append(spot)
            fresh.append(spot)
            if spot.time and (self._last_received is None or spot.time > self._last_received):
                self._last_received = spot.time

        if fresh:
            log.debug("DX cluster: %d new spot(s)", len(fresh))
            for cb in self._spot_callbacks:
                try:
                    cb(fresh)
                except Exception:
                    log.exception("DX spots callback raised")

    async def _fetch_solar(self) -> None:
        try:
            solar = await self._client.get_solar()
            if solar is not None:
                self._solar = solar
                log.debug("Solar: SFI=%s K=%s", solar.sfi, solar.k_index)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Solar fetch failed: %s", exc)
