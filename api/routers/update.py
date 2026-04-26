"""Update-check endpoints — reads GitHub releases and compares against VERSION."""
from __future__ import annotations

from pathlib import Path

import httpx
import yaml
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/update", tags=["update"])

_APP_CFG      = Path("config/app_config.yaml")
_VERSION_FILE = Path("VERSION")

_GH_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

# Cached result from the most recent check (background or manual).
_cached_result: dict | None = None


# ── helpers ───────────────────────────────────────────────────────────────────

def _current_version() -> str:
    if _VERSION_FILE.exists():
        return _VERSION_FILE.read_text(encoding="utf-8").strip()
    return "unknown"


def _read_app_cfg() -> dict:
    if not _APP_CFG.exists():
        return {}
    with open(_APP_CFG, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _write_app_cfg(cfg: dict) -> None:
    _APP_CFG.parent.mkdir(parents=True, exist_ok=True)
    with open(_APP_CFG, "w", encoding="utf-8") as fh:
        yaml.dump(cfg, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _parse_owner_repo(url: str) -> tuple[str, str] | tuple[None, None]:
    parts = url.rstrip("/").split("/")
    if len(parts) >= 2 and "github.com" in url:
        return parts[-2], parts[-1]
    return None, None


def _version_gt(a: str, b: str) -> bool:
    def to_tuple(v: str) -> tuple[int, ...]:
        try:
            return tuple(int(x) for x in v.lstrip("v").split("."))
        except ValueError:
            return (0,)
    return to_tuple(a) > to_tuple(b)


# ── core check logic (shared by endpoint and background task) ─────────────────

async def _do_check() -> dict:
    cfg     = _read_app_cfg()
    gh_url  = cfg.get("updates", {}).get("github_url", "").strip()
    current = _current_version()

    if not gh_url:
        return {"configured": False, "current_version": current}

    owner, repo = _parse_owner_repo(gh_url)
    if not owner:
        return {
            "configured": False,
            "current_version": current,
            "error": "Invalid GitHub URL — expected https://github.com/owner/repo",
        }

    api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(api_url, headers=_GH_HEADERS)

        if resp.status_code == 404:
            return {
                "configured": True,
                "current_version": current,
                "update_available": False,
                "message": "No releases published for this repository yet.",
            }

        resp.raise_for_status()
        data = resp.json()

        latest           = data["tag_name"]
        update_available = _version_gt(latest, current)

        return {
            "configured":       True,
            "current_version":  current,
            "latest_version":   latest,
            "update_available": update_available,
            "release_url":      data.get("html_url", ""),
            "release_notes":    (data.get("body") or "").strip(),
            "published_at":     data.get("published_at", ""),
        }

    except httpx.TimeoutException:
        return {"configured": True, "current_version": current,
                "error": "Request timed out — check your internet connection."}
    except httpx.HTTPStatusError as exc:
        return {"configured": True, "current_version": current,
                "error": f"GitHub returned HTTP {exc.response.status_code}."}
    except Exception as exc:  # noqa: BLE001
        return {"configured": True, "current_version": current, "error": str(exc)}


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.get("/config")
def get_update_config():
    cfg = _read_app_cfg()
    return {
        "github_url":      cfg.get("updates", {}).get("github_url", ""),
        "current_version": _current_version(),
    }


class UpdateConfigBody(BaseModel):
    github_url: str


@router.put("/config")
def put_update_config(body: UpdateConfigBody):
    cfg = _read_app_cfg()
    cfg.setdefault("updates", {})["github_url"] = body.github_url.strip()
    _write_app_cfg(cfg)
    return {"ok": True}


@router.get("/status")
def get_update_status():
    """Return the cached result from the last check without a network call."""
    if _cached_result is not None:
        return _cached_result
    cfg = _read_app_cfg()
    return {
        "configured":      bool(cfg.get("updates", {}).get("github_url", "").strip()),
        "current_version": _current_version(),
    }


@router.get("/check")
async def check_for_updates():
    """Trigger a live check and refresh the cache."""
    global _cached_result
    _cached_result = await _do_check()
    return _cached_result
