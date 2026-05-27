"""
FastAPI application factory.

Usage (development):
    uvicorn api.app:create_app --factory --reload --port 8080

Usage (production / embedded in main.py):
    from api.app import create_app
    app = create_app(state)
    uvicorn.run(app, host="0.0.0.0", port=8080)
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .auth import COOKIE_NAME, auth_enabled, decode_token, _is_revoked, load_auth_config
import jwt as _jwt
from .deps import AppState, get_state, _state
from .ws_hub import WSHub
from .routers import automations, auth, band_plan, comms, config, dashboards, devices, dx, hamlib, history, labels, logbook, notifications, radio, relays, sensors, streamdeck, system, update, ws

UI_DIST = Path("ui_dist")
_log    = logging.getLogger(__name__)


async def _update_check_loop(ws_hub: WSHub) -> None:
    """Background task: check GitHub for updates on a configurable interval."""
    # Short initial delay so startup noise settles before hitting the network.
    await asyncio.sleep(60)
    while True:
        try:
            cfg        = update._read_app_cfg()
            interval_h = max(cfg.get("updates", {}).get("check_interval_hours", 24), 1)

            result = await update._do_check()
            update._cached_result = result

            if result.get("update_available"):
                _log.info("Update available: %s - %s",
                          result.get("latest_version"), result.get("release_url"))
                await ws_hub.broadcast_update_available(result)
            else:
                _log.debug("Update check complete - already up to date (%s)",
                           result.get("current_version"))

        except asyncio.CancelledError:
            raise
        except Exception:
            _log.debug("Update check failed", exc_info=True)

        await asyncio.sleep(interval_h * 3600)


_UNPROTECTED_PREFIXES = ("/api/auth/", "/ws")


def create_app(app_state: Optional[AppState] = None) -> FastAPI:
    """
    Create and return the FastAPI app.

    Pass a populated AppState to wire live hardware singletons.
    Called without arguments the app starts in standalone mode - API
    endpoints work but return empty/offline responses (useful for
    frontend development).
    """
    if app_state is not None:
        # Populate the module-level singleton that Depends(get_state) returns
        for attr in vars(app_state):
            setattr(_state, attr, getattr(app_state, attr))

    if _state.ws_hub is None:
        _state.ws_hub = WSHub()

    # Write the hub back so the caller's app_state.ws_hub is populated.
    # main.py does `ws_hub = state.ws_hub` after create_app(); without this
    # that reference would be None and all radio/log broadcasts would silently fail.
    if app_state is not None:
        app_state.ws_hub = _state.ws_hub

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if _state.sensor_registry is not None:
            _state.ws_hub.attach_sensor_registry(_state.sensor_registry)

        task = asyncio.create_task(
            _update_check_loop(_state.ws_hub),
            name="update_check_loop",
        )
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app = FastAPI(
        title="StationController",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def _auth_guard(request: Request, call_next):
        path = request.url.path
        if not auth_enabled() or not path.startswith("/api/"):
            return await call_next(request)
        if any(path.startswith(p) for p in _UNPROTECTED_PREFIXES):
            return await call_next(request)
        token = request.cookies.get(COOKIE_NAME)
        if not token:
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
        try:
            payload = decode_token(token)
            if _is_revoked(payload):
                return JSONResponse({"detail": "Token revoked"}, status_code=401)
        except _jwt.ExpiredSignatureError:
            return JSONResponse({"detail": "Token expired"}, status_code=401)
        except _jwt.InvalidTokenError:
            return JSONResponse({"detail": "Invalid token"}, status_code=401)
        return await call_next(request)

    # API routers
    app.include_router(auth.router)
    app.include_router(ws.router)
    app.include_router(devices.router)
    app.include_router(sensors.router)
    app.include_router(labels.router)
    app.include_router(radio.router)
    app.include_router(hamlib.router)
    app.include_router(relays.router)
    app.include_router(dashboards.router)
    app.include_router(automations.router)
    app.include_router(notifications.router)
    app.include_router(update.router)
    app.include_router(comms.router)
    app.include_router(logbook.router)
    app.include_router(dx.router)
    app.include_router(config.router)
    app.include_router(history.router)
    app.include_router(system.router)
    app.include_router(band_plan.router)
    app.include_router(streamdeck.router)

    # Serve built frontend - falls back gracefully if not yet built
    if UI_DIST.exists() and any(UI_DIST.iterdir()):
        app.mount("/", StaticFiles(directory=str(UI_DIST), html=True), name="ui")

    return app
