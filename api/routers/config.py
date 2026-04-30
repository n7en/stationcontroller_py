"""GET /api/config/{name} and PUT /api/config/{name} — read/write YAML config files."""
from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/config", tags=["config"])

_CONFIG_FILES: dict[str, Path] = {
    "comms":      Path("config/comms_config.yaml"),
    "labels":     Path("config/labels.yaml"),
    "radio":      Path("config/radio_config.yaml"),
    "automation": Path("config/automation_config.yaml"),
    "telemetry":  Path("config/telemetry_config.yaml"),
    "auth":       Path("config/auth_config.yaml"),
}


@router.get("/{name}", response_class=PlainTextResponse)
async def get_config(name: str) -> str:
    path = _CONFIG_FILES.get(name)
    if path is None:
        raise HTTPException(status_code=404, detail=f"Unknown config: {name}")
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


class ConfigBody(BaseModel):
    content: str


@router.put("/{name}")
async def put_config(name: str, body: ConfigBody) -> dict:
    path = _CONFIG_FILES.get(name)
    if path is None:
        raise HTTPException(status_code=404, detail=f"Unknown config: {name}")
    try:
        yaml.safe_load(body.content)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid YAML: {exc}") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.content, encoding="utf-8", newline="\n")
    return {"ok": True, "name": name}
