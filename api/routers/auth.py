"""POST /api/auth/login  — validate credentials, set JWT cookie.
POST /api/auth/logout — revoke token, clear cookie.
GET  /api/auth/me     — return current auth state (safe to call unauthenticated).
"""
from __future__ import annotations

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
    record_attempt,
    revoke_token,
    validate_request,
    verify_password,
)

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

    users  = _users()
    user   = users.get(body.username)
    # Always call verify_password — even for unknown users — to prevent
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
