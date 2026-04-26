"""
POST /api/push/subscribe    — store a Web Push subscription
POST /api/push/unsubscribe  — remove a subscription
GET  /api/push/subscriptions — list active subscriptions (admin)
POST /api/push/test         — send a test notification to all subscribers
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

SUBSCRIPTIONS_FILE = Path("notifications/subscriptions.json")
log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/push", tags=["notifications"])


def _load() -> list[dict]:
    if not SUBSCRIPTIONS_FILE.exists():
        return []
    try:
        return json.loads(SUBSCRIPTIONS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save(subs: list[dict]) -> None:
    SUBSCRIPTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SUBSCRIPTIONS_FILE.write_text(json.dumps(subs, indent=2), encoding="utf-8")


class PushSubscription(BaseModel):
    endpoint: str
    keys: dict
    label: str = ""


@router.post("/subscribe")
async def subscribe(sub: PushSubscription) -> dict:
    subs = _load()
    # Replace existing entry for the same endpoint
    subs = [s for s in subs if s.get("endpoint") != sub.endpoint]
    subs.append({"endpoint": sub.endpoint, "keys": sub.keys, "label": sub.label})
    _save(subs)
    return {"ok": True, "subscribed": len(subs)}


@router.post("/unsubscribe")
async def unsubscribe(sub: PushSubscription) -> dict:
    subs = _load()
    before = len(subs)
    subs = [s for s in subs if s.get("endpoint") != sub.endpoint]
    _save(subs)
    return {"ok": True, "removed": before - len(subs)}


@router.get("/subscriptions")
async def list_subscriptions() -> list[dict]:
    return [
        {"endpoint": s["endpoint"][:60] + "...", "label": s.get("label", "")}
        for s in _load()
    ]


class TestNotification(BaseModel):
    title: str = "StationController"
    message: str = "Test notification"


@router.post("/test")
async def send_test(req: TestNotification) -> dict:
    sent, failed = await _dispatch(req.title, req.message)
    return {"sent": sent, "failed": failed}


async def _dispatch(title: str, message: str, urgency: str = "normal") -> tuple[int, int]:
    """Send a Web Push notification to all subscribers. Returns (sent, failed)."""
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        log.warning("pywebpush not installed — notifications disabled")
        return 0, 0

    from .._vapid import load_vapid_claims
    claims = load_vapid_claims()
    if claims is None:
        log.warning("VAPID keys not configured — notifications disabled")
        return 0, 0

    subs = _load()
    payload = json.dumps({"title": title, "body": message, "urgency": urgency})
    sent = failed = 0
    dead_endpoints: list[str] = []

    for sub in subs:
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=claims["private_key"],
                vapid_claims={"sub": claims["sub"]},
            )
            sent += 1
        except WebPushException as e:
            if e.response and e.response.status_code in (404, 410):
                dead_endpoints.append(sub["endpoint"])
            else:
                log.warning("Push failed for %s: %s", sub["endpoint"][:40], e)
            failed += 1
        except Exception as e:
            log.warning("Push error: %s", e)
            failed += 1

    if dead_endpoints:
        subs = [s for s in subs if s["endpoint"] not in dead_endpoints]
        _save(subs)

    return sent, failed
