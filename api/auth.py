"""
Authentication utilities - JWT, bcrypt, per-IP rate limiting, token revocation.

Auth is opt-in: if auth.enabled is false (or config is absent), every route
treats the caller as "anonymous" and all checks pass.  Enable by creating
config/auth_config.yaml and setting auth.enabled: true.
"""
from __future__ import annotations

import secrets
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

import bcrypt as _bcrypt
import jwt
import yaml
from fastapi import HTTPException, Request, status

ALGORITHM   = "HS256"
COOKIE_NAME = "sc_token"

# Pre-computed dummy hash - ensures verify_password is always called even
# when the username does not exist, preventing timing-based user enumeration.
_DUMMY_HASH: str = _bcrypt.hashpw(b"__dummy_sentinel__", _bcrypt.gensalt()).decode()

# ---------------------------------------------------------------------------
# Runtime config
# ---------------------------------------------------------------------------

_cfg:      dict  = {}
_cfg_mtime: float = 0.0  # mtime of the last successful load


def load_auth_config(path: Optional[Path] = None) -> None:
    global _cfg, _cfg_mtime
    p = path or Path("config/auth_config.yaml")
    _cfg = {}
    _cfg_mtime = 0.0
    if p.exists():
        _cfg_mtime = p.stat().st_mtime
        with open(p, encoding="utf-8") as fh:
            _cfg = yaml.safe_load(fh) or {}


def reload_if_changed(path: Optional[Path] = None) -> None:
    """Re-read config from disk only when the file has been modified since last load."""
    global _cfg, _cfg_mtime
    p = path or Path("config/auth_config.yaml")
    if not p.exists():
        return
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return
    if mtime <= _cfg_mtime:
        return
    _cfg_mtime = mtime
    with open(p, encoding="utf-8") as fh:
        _cfg = yaml.safe_load(fh) or {}


def _auth() -> dict:
    return _cfg.get("auth", {})


def auth_enabled() -> bool:
    return bool(_auth().get("enabled", False))


def _secret() -> str:
    return str(_auth().get("secret", "changeme-insecure-please-set"))


def _expiry_seconds() -> int:
    return int(_auth().get("token_expiry_hours", 24)) * 3600


def _users() -> dict:
    return _auth().get("users", {})


def _secure_cookie() -> bool:
    return bool(_auth().get("secure_cookie", False))


# ---------------------------------------------------------------------------
# Password utilities
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt. Use to generate auth_config entries."""
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JWT + token revocation
# ---------------------------------------------------------------------------

# Maps jti -> expiry timestamp.  Entries are pruned after their JWT expires.
_revoked: dict[str, float] = {}


def _prune_revoked() -> None:
    now  = time.time()
    dead = [jti for jti, exp in _revoked.items() if exp < now]
    for jti in dead:
        del _revoked[jti]


def create_token(username: str) -> str:
    now = int(time.time())
    exp = now + _expiry_seconds()
    payload = {
        "sub": username,
        "iat": now,
        "exp": exp,
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, _secret(), algorithms=[ALGORITHM])


def revoke_token(token: str) -> None:
    """Add a token's jti to the revocation set so logout prevents replay."""
    try:
        payload = jwt.decode(
            token, _secret(), algorithms=[ALGORITHM],
            options={"verify_exp": False},
        )
        jti = payload.get("jti")
        exp = float(payload.get("exp", 0))
        if jti:
            _revoked[jti] = exp
            _prune_revoked()
    except Exception:
        pass  # token was already invalid; nothing to revoke


def _is_revoked(payload: dict) -> bool:
    return payload.get("jti") in _revoked


# ---------------------------------------------------------------------------
# Rate limiter (per-IP, in-memory)
# ---------------------------------------------------------------------------

_attempts: dict[str, list[float]] = defaultdict(list)
MAX_ATTEMPTS = 5
WINDOW_SECS  = 60.0


def check_rate_limit(ip: str) -> None:
    now = time.time()
    _attempts[ip] = [t for t in _attempts[ip] if now - t < WINDOW_SECS]
    if len(_attempts[ip]) >= MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
        )


def record_attempt(ip: str) -> None:
    _attempts[ip].append(time.time())


# ---------------------------------------------------------------------------
# FastAPI request validator (used by middleware)
# ---------------------------------------------------------------------------

def validate_request(request: Request) -> str:
    """
    Validate the JWT cookie on an incoming request.
    Returns the username on success; raises HTTP 401 on any failure.
    When auth is disabled returns 'anonymous' unconditionally.
    """
    if not auth_enabled():
        return "anonymous"

    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    if _is_revoked(payload):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token revoked",
        )
    return payload["sub"]
