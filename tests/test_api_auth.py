"""
Security-focused tests for the authentication system.

Coverage:
  - Happy path login / logout / /me
  - Wrong and missing credentials
  - User enumeration prevention (constant-time comparison)
  - Input validation (empty fields, oversized payloads)
  - Rate limiting (brute-force protection)
  - Cookie attributes (httpOnly, SameSite)
  - JWT tampering
  - Expired tokens
  - Token revocation — logout prevents replay
  - Protected routes require authentication
  - Auth-disabled mode — all routes open
  - Injection characters in username / password
"""
from __future__ import annotations

import time
from contextlib import contextmanager

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from api import auth as auth_mod
from api.app  import create_app
from api.deps import AppState, _state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GOOD_HASH = auth_mod.hash_password("correct-horse")

_USERS = {
    "admin": {"password_hash": auth_mod.hash_password("correct-horse")},
}


@contextmanager
def _auth_cfg(
    users: dict = _USERS,
    enabled: bool = True,
    secret: str = "test-secret-key",
    expiry_hours: int = 1,
):
    """Temporarily override auth module state for the duration of a test."""
    old_cfg      = auth_mod._cfg
    old_attempts = dict(auth_mod._attempts)
    old_revoked  = dict(auth_mod._revoked)
    auth_mod._cfg = {
        "auth": {
            "enabled":           enabled,
            "secret":            secret,
            "token_expiry_hours": expiry_hours,
            "secure_cookie":     False,
            "users":             users,
        }
    }
    auth_mod._attempts.clear()
    auth_mod._revoked.clear()
    try:
        yield
    finally:
        auth_mod._cfg = old_cfg
        auth_mod._attempts.clear()
        auth_mod._attempts.update(old_attempts)
        auth_mod._revoked.clear()
        auth_mod._revoked.update(old_revoked)


def _make_app(users=_USERS, enabled=True):
    fresh = AppState()
    for attr in vars(fresh):
        setattr(_state, attr, getattr(fresh, attr))
    return create_app(AppState())


@contextmanager
def _client_ctx(users=_USERS, enabled=True):
    with _auth_cfg(users=users, enabled=enabled):
        app = _make_app()
        yield app


@pytest.fixture
def auth_app():
    with _auth_cfg():
        app = _make_app()
        yield app


@pytest.fixture
async def client(auth_app):
    async with AsyncClient(
        transport=ASGITransport(app=auth_app), base_url="http://test"
    ) as c:
        yield c


@pytest.fixture
async def logged_in_client(auth_app):
    """Client that has already completed login."""
    async with AsyncClient(
        transport=ASGITransport(app=auth_app), base_url="http://test"
    ) as c:
        r = await c.post("/api/auth/login",
                         json={"username": "admin", "password": "correct-horse"})
        assert r.status_code == 200
        yield c


# ---------------------------------------------------------------------------
# Login — happy path
# ---------------------------------------------------------------------------

class TestLoginHappyPath:

    async def test_correct_credentials_return_200(self, client):
        r = await client.post("/api/auth/login",
                              json={"username": "admin", "password": "correct-horse"})
        assert r.status_code == 200

    async def test_response_body_contains_username(self, client):
        r = await client.post("/api/auth/login",
                              json={"username": "admin", "password": "correct-horse"})
        assert r.json()["ok"] is True
        assert r.json()["username"] == "admin"

    async def test_cookie_is_set(self, client):
        r = await client.post("/api/auth/login",
                              json={"username": "admin", "password": "correct-horse"})
        assert auth_mod.COOKIE_NAME in r.cookies

    async def test_cookie_is_httponly(self, client):
        r = await client.post("/api/auth/login",
                              json={"username": "admin", "password": "correct-horse"})
        set_cookie = r.headers.get("set-cookie", "")
        assert "httponly" in set_cookie.lower()

    async def test_cookie_is_samesite_lax(self, client):
        r = await client.post("/api/auth/login",
                              json={"username": "admin", "password": "correct-horse"})
        set_cookie = r.headers.get("set-cookie", "")
        assert "samesite=lax" in set_cookie.lower()

    async def test_cookie_contains_valid_jwt(self, client):
        r = await client.post("/api/auth/login",
                              json={"username": "admin", "password": "correct-horse"})
        token   = r.cookies[auth_mod.COOKIE_NAME]
        payload = auth_mod.decode_token(token)
        assert payload["sub"] == "admin"

    async def test_jwt_has_expiry_claim(self, client):
        r = await client.post("/api/auth/login",
                              json={"username": "admin", "password": "correct-horse"})
        token   = r.cookies[auth_mod.COOKIE_NAME]
        payload = auth_mod.decode_token(token)
        assert "exp" in payload
        assert payload["exp"] > time.time()

    async def test_jwt_has_unique_jti(self, client):
        r1 = await client.post("/api/auth/login",
                               json={"username": "admin", "password": "correct-horse"})
        r2 = await client.post("/api/auth/login",
                               json={"username": "admin", "password": "correct-horse"})
        t1 = auth_mod.decode_token(r1.cookies[auth_mod.COOKIE_NAME])
        t2 = auth_mod.decode_token(r2.cookies[auth_mod.COOKIE_NAME])
        assert t1["jti"] != t2["jti"]


# ---------------------------------------------------------------------------
# Login — wrong / missing credentials
# ---------------------------------------------------------------------------

class TestLoginRejection:

    async def test_wrong_password_returns_401(self, client):
        r = await client.post("/api/auth/login",
                              json={"username": "admin", "password": "wrong"})
        assert r.status_code == 401

    async def test_unknown_user_returns_401(self, client):
        r = await client.post("/api/auth/login",
                              json={"username": "nobody", "password": "anything"})
        assert r.status_code == 401

    async def test_wrong_and_unknown_return_same_message(self, client):
        """No user enumeration — both cases return identical error text."""
        r_wrong   = await client.post("/api/auth/login",
                                      json={"username": "admin", "password": "wrong"})
        r_unknown = await client.post("/api/auth/login",
                                      json={"username": "nobody", "password": "wrong"})
        assert r_wrong.json()["detail"] == r_unknown.json()["detail"]

    async def test_no_cookie_on_failed_login(self, client):
        r = await client.post("/api/auth/login",
                              json={"username": "admin", "password": "wrong"})
        assert auth_mod.COOKIE_NAME not in r.cookies


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestInputValidation:

    async def test_empty_username_returns_422(self, client):
        r = await client.post("/api/auth/login",
                              json={"username": "", "password": "anything"})
        assert r.status_code == 422

    async def test_empty_password_returns_422(self, client):
        r = await client.post("/api/auth/login",
                              json={"username": "admin", "password": ""})
        assert r.status_code == 422

    async def test_missing_body_returns_422(self, client):
        r = await client.post("/api/auth/login")
        assert r.status_code == 422

    async def test_username_too_long_returns_422(self, client):
        r = await client.post("/api/auth/login",
                              json={"username": "a" * 300, "password": "pw"})
        assert r.status_code == 422

    async def test_password_too_long_returns_422(self, client):
        r = await client.post("/api/auth/login",
                              json={"username": "admin", "password": "x" * 300})
        assert r.status_code == 422

    async def test_sql_injection_in_username_returns_401(self, client):
        r = await client.post("/api/auth/login",
                              json={"username": "' OR 1=1 --", "password": "anything"})
        assert r.status_code == 401

    async def test_special_chars_in_username_returns_401(self, client):
        r = await client.post("/api/auth/login",
                              json={"username": "<script>alert(1)</script>", "password": "pw"})
        assert r.status_code == 401

    async def test_newline_injection_in_password_returns_401(self, client):
        r = await client.post("/api/auth/login",
                              json={"username": "admin", "password": "pass\nword"})
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class TestRateLimiting:

    async def test_fifth_attempt_still_allowed(self, client):
        for _ in range(5):
            r = await client.post("/api/auth/login",
                                  json={"username": "admin", "password": "wrong"})
        assert r.status_code == 401   # 401, not 429

    async def test_sixth_attempt_is_blocked(self, client):
        for _ in range(5):
            await client.post("/api/auth/login",
                              json={"username": "admin", "password": "wrong"})
        r = await client.post("/api/auth/login",
                              json={"username": "admin", "password": "wrong"})
        assert r.status_code == 429

    async def test_429_before_password_check(self, client):
        """Rate limit fires before credentials are evaluated — correct password blocked too."""
        for _ in range(5):
            await client.post("/api/auth/login",
                              json={"username": "admin", "password": "wrong"})
        r = await client.post("/api/auth/login",
                              json={"username": "admin", "password": "correct-horse"})
        assert r.status_code == 429

    async def test_old_attempts_outside_window_do_not_count(self):
        """Attempts older than the window are pruned and don't block new logins."""
        with _auth_cfg():
            app = _make_app()
            now = time.time()
            # httpx ASGITransport presents scope["client"] = ("testclient", 50000)
            # so request.client.host == "testclient"
            auth_mod._attempts["testclient"] = [now - 61] * 5
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                r = await c.post("/api/auth/login",
                                 json={"username": "admin", "password": "correct-horse"})
            assert r.status_code == 200


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

class TestLogout:

    async def test_logout_returns_200(self, logged_in_client):
        r = await logged_in_client.post("/api/auth/logout")
        assert r.status_code == 200

    async def test_logout_clears_cookie(self, logged_in_client):
        await logged_in_client.post("/api/auth/logout")
        # After logout the cookie value is empty or absent
        assert not logged_in_client.cookies.get(auth_mod.COOKIE_NAME)

    async def test_token_is_revoked_after_logout(self, auth_app):
        """Replaying the original token after logout must be rejected (anti-replay)."""
        async with AsyncClient(
            transport=ASGITransport(app=auth_app), base_url="http://test"
        ) as c:
            r = await c.post("/api/auth/login",
                             json={"username": "admin", "password": "correct-horse"})
            assert r.status_code == 200
            token = r.cookies[auth_mod.COOKIE_NAME]
            # Logout — adds jti to _revoked within the same _auth_cfg context
            await c.post("/api/auth/logout")
            # Replay the captured token (simulates attacker reusing a stolen cookie)
            c.cookies.set(auth_mod.COOKIE_NAME, token)
            r2 = await c.get("/api/sensors")
        assert r2.status_code == 401

    async def test_logout_without_cookie_is_safe(self, client):
        r = await client.post("/api/auth/logout")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# JWT security
# ---------------------------------------------------------------------------

class TestJwtSecurity:

    async def test_tampered_signature_rejected(self, client):
        r = await client.post("/api/auth/login",
                              json={"username": "admin", "password": "correct-horse"})
        token = r.cookies[auth_mod.COOKIE_NAME]
        # Flip last character of signature
        bad_token = token[:-1] + ("A" if token[-1] != "A" else "B")
        with _auth_cfg():
            app = _make_app()
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test",
                cookies={auth_mod.COOKIE_NAME: bad_token},
            ) as c:
                r2 = await c.get("/api/sensors")
        assert r2.status_code == 401

    async def test_expired_token_rejected(self):
        """Token with exp in the past must be rejected."""
        with _auth_cfg(expiry_hours=1):
            past_payload = {
                "sub":  "admin",
                "iat":  int(time.time()) - 7200,
                "exp":  int(time.time()) - 3600,   # already expired
                "jti":  "testjti",
            }
            expired_token = jwt.encode(
                past_payload, "test-secret-key", algorithm=auth_mod.ALGORITHM
            )
            app = _make_app()
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test",
                cookies={auth_mod.COOKIE_NAME: expired_token},
            ) as c:
                r = await c.get("/api/sensors")
        assert r.status_code == 401

    async def test_token_signed_with_wrong_secret_rejected(self, client):
        wrong_token = jwt.encode(
            {"sub": "admin", "exp": int(time.time()) + 3600, "jti": "x"},
            "wrong-secret",
            algorithm=auth_mod.ALGORITHM,
        )
        with _auth_cfg():
            app = _make_app()
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test",
                cookies={auth_mod.COOKIE_NAME: wrong_token},
            ) as c:
                r = await c.get("/api/sensors")
        assert r.status_code == 401

    async def test_none_algorithm_token_rejected(self, client):
        """'alg: none' attack must be rejected."""
        # jwt.encode with algorithm="none" produces an unsigned token
        forged = jwt.encode(
            {"sub": "admin", "exp": int(time.time()) + 3600, "jti": "y"},
            "",
            algorithm="none",
        )
        with _auth_cfg():
            app = _make_app()
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test",
                cookies={auth_mod.COOKIE_NAME: forged},
            ) as c:
                r = await c.get("/api/sensors")
        assert r.status_code == 401

    async def test_missing_cookie_rejected(self, client):
        with _auth_cfg():
            app = _make_app()
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                r = await c.get("/api/sensors")
        assert r.status_code == 401

    async def test_garbage_cookie_value_rejected(self, client):
        with _auth_cfg():
            app = _make_app()
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test",
                cookies={auth_mod.COOKIE_NAME: "not.a.jwt"},
            ) as c:
                r = await c.get("/api/sensors")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Protected routes
# ---------------------------------------------------------------------------

class TestProtectedRoutes:

    async def test_sensors_requires_auth(self, client):
        r = await client.get("/api/sensors")
        assert r.status_code == 401

    async def test_relays_requires_auth(self, client):
        r = await client.get("/api/relays")
        assert r.status_code == 401

    async def test_history_requires_auth(self, client):
        r = await client.get("/api/history/sensors/names")
        assert r.status_code == 401

    async def test_authenticated_client_can_access_sensors(self, logged_in_client):
        r = await logged_in_client.get("/api/sensors")
        assert r.status_code == 200

    async def test_login_endpoint_is_not_protected(self, client):
        """Login must be reachable before authentication — auth guard must not intercept it."""
        r = await client.post("/api/auth/login",
                              json={"username": "x", "password": "y"})
        # Auth guard says "Not authenticated"; login handler says "Invalid credentials".
        # Either way the login route was reached, not blocked by the middleware.
        assert r.json().get("detail") == "Invalid credentials"


# ---------------------------------------------------------------------------
# /api/auth/me
# ---------------------------------------------------------------------------

class TestMeEndpoint:

    async def test_me_returns_null_username_when_not_logged_in(self, client):
        r = await client.get("/api/auth/me")
        assert r.status_code == 200
        body = r.json()
        assert body["auth_enabled"] is True
        assert body["username"] is None

    async def test_me_returns_username_when_logged_in(self, logged_in_client):
        r = await logged_in_client.get("/api/auth/me")
        assert r.status_code == 200
        assert r.json()["username"] == "admin"
        assert r.json()["auth_enabled"] is True

    async def test_me_not_gated_by_auth_middleware(self, client):
        """/me must always be reachable so the UI can determine auth state."""
        r = await client.get("/api/auth/me")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Auth disabled mode
# ---------------------------------------------------------------------------

class TestAuthDisabled:

    async def test_sensors_accessible_without_credentials(self):
        with _auth_cfg(enabled=False):
            app = _make_app()
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                r = await c.get("/api/sensors")
        assert r.status_code == 200

    async def test_me_reports_auth_disabled(self):
        with _auth_cfg(enabled=False):
            app = _make_app()
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                r = await c.get("/api/auth/me")
        assert r.json()["auth_enabled"] is False
        assert r.json()["username"] == "anonymous"

    async def test_history_accessible_without_credentials(self):
        with _auth_cfg(enabled=False):
            app = _make_app()
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                r = await c.get("/api/history/sensors/names")
        assert r.status_code == 200
