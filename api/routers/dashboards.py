"""
GET  /api/dashboards        - list all dashboard configs
GET  /api/dashboards/{id}   - get one dashboard config
PUT  /api/dashboards/{id}   - save dashboard config (JSON body)
POST /api/dashboards        - create new dashboard
"""
from __future__ import annotations

import re
from pathlib import Path
import yaml
from fastapi import APIRouter, HTTPException, Request

DASHBOARDS_DIR = Path("config/dashboards")
router = APIRouter(prefix="/api/dashboards", tags=["dashboards"])

_SAFE_ID = re.compile(r"^[a-zA-Z0-9_\-]+$")


def _dashboard_path(dashboard_id: str) -> Path:
    if not _SAFE_ID.match(dashboard_id):
        raise HTTPException(status_code=422, detail="Invalid dashboard id")
    return DASHBOARDS_DIR / f"{dashboard_id}.yaml"


def _load(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise HTTPException(status_code=422, detail=f"YAML parse error: {e}")


@router.get("")
async def list_dashboards() -> list[dict]:
    DASHBOARDS_DIR.mkdir(parents=True, exist_ok=True)
    result = []
    for p in sorted(DASHBOARDS_DIR.glob("*.yaml")):
        cfg = _load(p)
        result.append({
            "id": p.stem,
            "title": cfg.get("title", p.stem),
            "icon": cfg.get("icon", "view-dashboard"),
        })
    return result


@router.get("/{dashboard_id}")
async def get_dashboard(dashboard_id: str) -> dict:
    path = _dashboard_path(dashboard_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Dashboard {dashboard_id!r} not found")
    return _load(path)


@router.get("/{dashboard_id}/raw")
async def get_dashboard_raw(dashboard_id: str) -> dict:
    path = _dashboard_path(dashboard_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Dashboard {dashboard_id!r} not found")
    return {"yaml": path.read_text(encoding="utf-8")}


@router.put("/{dashboard_id}")
async def save_dashboard(dashboard_id: str, request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid JSON body")
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="Dashboard config must be a JSON object")
    path = _dashboard_path(dashboard_id)
    DASHBOARDS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(body, default_flow_style=False, allow_unicode=True),
        encoding="utf-8", newline="\n",
    )
    return {"ok": True, "id": dashboard_id}


@router.post("")
async def create_dashboard(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid JSON body")
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="Dashboard config must be a JSON object")
    dashboard_id = body.get("id")
    if not dashboard_id or not _SAFE_ID.match(str(dashboard_id)):
        raise HTTPException(status_code=422, detail="Dashboard must have a valid 'id' field")
    path = _dashboard_path(str(dashboard_id))
    if path.exists():
        raise HTTPException(status_code=409, detail=f"Dashboard {dashboard_id!r} already exists")
    DASHBOARDS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(body, default_flow_style=False, allow_unicode=True),
        encoding="utf-8", newline="\n",
    )
    return {"ok": True, "id": dashboard_id}


@router.delete("/{dashboard_id}")
async def delete_dashboard(dashboard_id: str) -> dict:
    path = _dashboard_path(dashboard_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Dashboard {dashboard_id!r} not found")
    path.unlink()
    return {"ok": True}
