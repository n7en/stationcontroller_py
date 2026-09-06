"""
GET /api/radio/hamlib-models  — list all Hamlib radio models.

Calls ``rigctl -l`` as a subprocess and parses the fixed-width output.
Result is cached after the first successful call so subsequent requests
are instant.  Returns an empty list (not an error) if rigctl is not installed.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/radio", tags=["radio"])
log    = logging.getLogger(__name__)

_MODEL_CACHE: Optional[list[dict]] = None


def _parse_rigctl_list(output: str) -> list[dict]:
    """
    Parse 'rigctl -l' fixed-width output.

    rigctld prints with format string: ``%6d  %-24s  %-24s  %-8s  %s``
    Column positions (0-indexed):
        0-5   model_id
        8-31  manufacturer (24 chars)
        34-57 model name   (24 chars)
        60-67 version      (8 chars)
        70+   status
    """
    models = []
    for line in output.splitlines():
        line = line.rstrip()
        if not line:
            continue
        # Skip header lines
        stripped = line.lstrip()
        if stripped.startswith("Rig#") or stripped.startswith("Mfg"):
            continue
        try:
            model_id = int(line[:6])
        except ValueError:
            continue
        mfg      = line[8:32].strip()  if len(line) > 8  else ""
        model    = line[34:58].strip() if len(line) > 34 else ""
        version  = line[60:68].strip() if len(line) > 60 else ""
        status   = line[70:].strip()   if len(line) > 70 else ""
        if model_id <= 0:
            continue
        models.append({
            "model_id":     model_id,
            "manufacturer": mfg,
            "model":        model,
            "version":      version,
            "status":       status,
        })
    return models


async def _fetch_models() -> list[dict]:
    global _MODEL_CACHE
    if _MODEL_CACHE is not None:
        return _MODEL_CACHE

    for exe in ("rigctl", "rigctl.exe"):
        try:
            proc = await asyncio.create_subprocess_exec(
                exe, "-l",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15.0)
            models = _parse_rigctl_list(stdout.decode(errors="replace"))
            if models:
                log.info("Loaded %d Hamlib models from %s -l", len(models), exe)
                _MODEL_CACHE = models
                return models
        except FileNotFoundError:
            continue
        except asyncio.TimeoutError:
            log.warning("rigctl -l timed out")
            break
        except Exception as exc:
            log.warning("rigctl -l failed: %s", exc)
            break

    log.info("rigctl not found or returned no models; Hamlib model list unavailable")
    _MODEL_CACHE = []
    return []


@router.get("/hamlib-models")
async def list_hamlib_models(
    search: str = Query(default="", description="Filter by manufacturer or model name"),
    status: str = Query(default="", description="Filter by status (e.g. Stable, Alpha, Beta)"),
) -> dict:
    """Return all Hamlib-supported radio models, optionally filtered."""
    models = await _fetch_models()

    if search:
        q = search.lower()
        models = [
            m for m in models
            if q in m["manufacturer"].lower() or q in m["model"].lower()
        ]
    if status:
        s = status.lower()
        models = [m for m in models if m["status"].lower() == s]

    return {"models": models, "total": len(models)}


@router.post("/hamlib-models/refresh")
async def refresh_hamlib_models() -> dict:
    """Force a fresh ``rigctl -l`` call, discarding the cached model list."""
    global _MODEL_CACHE
    _MODEL_CACHE = None
    models = await _fetch_models()
    return {"total": len(models)}
