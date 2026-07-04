"""
GET    /api/labels           - list all friendly name labels
PUT    /api/labels/{key}     - set or update a label
DELETE /api/labels/{key}     - remove a label
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import AppState, get_state
from ..paths import CONFIG_DIR

LABELS_PATH = CONFIG_DIR / "labels.yaml"

router = APIRouter(prefix="/api/labels", tags=["labels"])


@router.get("")
async def get_labels(state: AppState = Depends(get_state)) -> dict[str, str]:
    """Return all hardware_key -> friendly_label mappings."""
    if state.label_registry is None:
        return {}
    return state.label_registry.all()


class LabelBody(BaseModel):
    label: str


@router.put("/{key}")
async def set_label(
    key: str,
    body: LabelBody,
    state: AppState = Depends(get_state),
) -> dict:
    """Set or update the friendly label for *key*, then persist to disk."""
    if not body.label.strip():
        raise HTTPException(status_code=422, detail="label must not be empty")
    if state.label_registry is None:
        raise HTTPException(status_code=503, detail="Label registry not available")
    state.label_registry.set(key, body.label.strip())
    state.label_registry.save(LABELS_PATH)
    if state.ws_hub:
        await state.ws_hub.broadcast_labels(state.label_registry.all())
    return {"ok": True, "key": key, "label": body.label.strip()}


@router.delete("/{key}")
async def delete_label(
    key: str,
    state: AppState = Depends(get_state),
) -> dict:
    """Remove the friendly label for *key*, then persist to disk."""
    if state.label_registry is None:
        raise HTTPException(status_code=503, detail="Label registry not available")
    if key not in state.label_registry:
        raise HTTPException(status_code=404, detail=f"No label for {key!r}")
    state.label_registry.remove(key)
    state.label_registry.save(LABELS_PATH)
    if state.ws_hub:
        await state.ws_hub.broadcast_labels(state.label_registry.all())
    return {"ok": True, "key": key}
