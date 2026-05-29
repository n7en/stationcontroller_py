"""System control endpoints - restart, etc."""
from __future__ import annotations

import asyncio
import logging
import os
import sys

from fastapi import APIRouter

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/system", tags=["system"])


@router.post("/restart")
async def restart_app() -> dict:
    """Schedule a full process restart after the response is sent."""
    async def _restart() -> None:
        await asyncio.sleep(0.5)   # give the HTTP response time to leave
        log.info("Restarting application: %s %s", sys.executable, sys.argv)
        os.execv(sys.executable, [sys.executable] + sys.argv)

    asyncio.create_task(_restart(), name="app_restart")
    return {"ok": True}
