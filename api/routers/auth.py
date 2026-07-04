"""POST /api/auth/login  - validate credentials, set JWT cookie.
POST /api/auth/logout - revoke token, clear cookie.
GET  /api/auth/me     - return current auth state (safe to call unauthenticated).
"""
from __future__ import annotations

from pathlib import Path

import yaml as _yaml
from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, field_validator

from ..auth import (
    COOKIE_NAME,
    _DUMMY_HASH,
    _secure_cookie,
    _users,
    auth_enabled,
    check_rate_limit,
    create_token,
    hash_password,
    load_auth_config,
    reload_if_changed,
    record_attempt,
    revoke_token,
    validate_request,
    verify_password,
)

from ..paths import CONFIG_DIR

_AUTH_CFG = CONFIG_DIR / "auth_config.yaml"

router = APIRouter(prefix="/api/auth", tags=["auth"])

_MAX_FIELD = 256


class LoginBody(BaseModel):
    username: str
    password: str

    @field_validator("username", "password")
    @classmethod
    def _check(cls, v: str) -> str:
        if not v:
            raise ValueError("must not be empty")
        if len(v) > _MAX_FIELD:
            raise ValueError(f"must not exceed {_MAX_FIELD} characters")
        return v


@router.post("/login")
async def login(body: LoginBody, request: Request, response: Response) -> dict:
    ip = (request.client.host if request.client else None) or "unknown"
    check_rate_limit(ip)
    record_attempt(ip)

    reload_if_changed()  # pick up user/config changes without a restart
    users  = _users()
    user   = users.get(body.username)
    # Always call verify_password - even for unknown users - to prevent
    # timing-based username enumeration.
    hashed = user.get("password_hash", _DUMMY_HASH) if isinstance(user, dict) else _DUMMY_HASH
    valid  = bool(user) and verify_password(body.password, hashed)

    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    token = create_token(body.username)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=_secure_cookie(),
        max_age=86400,
    )
    return {"ok": True, "username": body.username}


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        revoke_token(token)
    response.delete_cookie(COOKIE_NAME, samesite="lax")
    return {"ok": True}


@router.get("/me")
async def me(request: Request) -> dict:
    if not auth_enabled():
        return {"username": "anonymous", "auth_enabled": False}
    try:
        username = validate_request(request)
        return {"username": username, "auth_enabled": True}
    except HTTPException:
        return {"username": None, "auth_enabled": True}


# ---------------------------------------------------------------------------
# User management (used by the setup wizard)
# ---------------------------------------------------------------------------

def _load_auth_yaml() -> dict:
    if not _AUTH_CFG.exists():
        return {}
    with open(_AUTH_CFG, encoding="utf-8") as fh:
        return _yaml.safe_load(fh) or {}


def _save_auth_yaml(cfg: dict) -> None:
    _AUTH_CFG.parent.mkdir(parents=True, exist_ok=True)
    with open(_AUTH_CFG, "w", encoding="utf-8", newline="\n") as fh:
        _yaml.dump(cfg, fh, default_flow_style=False, allow_unicode=True)
    load_auth_config(_AUTH_CFG)


@router.get("/users")
async def list_users() -> dict:
    """Return the list of configured usernames (no hashes)."""
    reload_if_changed()
    return {"users": sorted(_users().keys())}


class UserBody(BaseModel):
    username: str
    password: str

    @field_validator("username", "password")
    @classmethod
    def _check(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        if len(v) > _MAX_FIELD:
            raise ValueError(f"must not exceed {_MAX_FIELD} characters")
        return v


@router.post("/users")
async def create_or_update_user(body: UserBody) -> dict:
    """Create or update a user with a bcrypt-hashed password."""
    cfg = _load_auth_yaml()
    cfg.setdefault("auth", {}).setdefault("users", {})[body.username] = {
        "password_hash": hash_password(body.password)
    }
    _save_auth_yaml(cfg)
    return {"ok": True, "username": body.username}


@router.delete("/users/{username}")
async def delete_user(username: str) -> dict:
    """Remove a user from the auth config."""
    cfg = _load_auth_yaml()
    users = cfg.get("auth", {}).get("users", {})
    if username not in users:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found")
    del users[username]
    _save_auth_yaml(cfg)
    return {"ok": True}
