"""
Band plan API router.

GET  /api/band_plan           - current plan (config + full serialized plan)
GET  /api/band_plan/built_ins - list of built-in plan keys and labels
GET  /api/band_plan/built_in/{key} - serialize one built-in plan
PUT  /api/band_plan           - save plan config to config/band_plan.yaml
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Request

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/band_plan", tags=["band_plan"])

from ..paths import CONFIG_DIR

BAND_PLAN_CFG = CONFIG_DIR / "band_plan.yaml"

BUILT_IN_PLANS = [
    {"key": "us_extra",     "label": "US Amateur Extra"},
    {"key": "us_general",   "label": "US General"},
    {"key": "ca_amateur",   "label": "Canadian Amateur"},
    {"key": "itu_region_1", "label": "ITU Region 1 (Europe / Africa)"},
    {"key": "itu_region_2", "label": "ITU Region 2 (Americas)"},
    {"key": "itu_region_3", "label": "ITU Region 3 (Asia / Pacific)"},
]


def _load_cfg() -> dict:
    if BAND_PLAN_CFG.exists():
        with open(BAND_PLAN_CFG, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    return {}


@router.get("/built_ins")
def list_built_ins() -> list[dict]:
    return BUILT_IN_PLANS


@router.get("/built_in/{key}")
def get_built_in(key: str) -> dict:
    from automation.bands import BandPlan, band_plan_to_dict
    try:
        plan = BandPlan.from_built_in(key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return band_plan_to_dict(plan)


@router.get("")
def get_band_plan() -> dict:
    from automation.bands import band_plan_from_config, band_plan_to_dict
    cfg = _load_cfg()
    plan = band_plan_from_config(cfg)
    return {"config": cfg, "plan": band_plan_to_dict(plan)}


@router.put("")
async def save_band_plan(request: Request) -> dict[str, Any]:
    body: dict[str, Any] = await request.json()
    BAND_PLAN_CFG.parent.mkdir(parents=True, exist_ok=True)
    with open(BAND_PLAN_CFG, "w", encoding="utf-8", newline="\n") as fh:
        yaml.dump(body, fh, default_flow_style=False, allow_unicode=True)
    log.info("Band plan saved to %s", BAND_PLAN_CFG)
    return {"ok": True}
