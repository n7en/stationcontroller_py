"""
Radio state-change wiring shared by startup (main.py) and the radio config
rebuild endpoint (PUT /api/radio/config).

Handlers resolve their dependencies (ws_hub, engine, band registry, primary
interface) through AppState at call time, so a radio rebuild never leaves
automations bound to stale objects.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .deps import AppState

log = logging.getLogger(__name__)


def wire_radio_handlers(state: "AppState") -> None:
    """Attach WS-broadcast + automation handlers to every radio interface.

    Call after (re)building state.radio_manager.  Each interface gets exactly
    one handler; only the primary interface (state.radio_interface) drives the
    automation engine.
    """
    if state.radio_manager is None:
        return

    for iface in state.radio_manager:
        def _make(_iface=iface):
            async def _on_radio(rs, changed: dict) -> None:
                if state.ws_hub is not None:
                    await state.ws_hub.broadcast_radio(_iface.name, rs)
                if "ptt" in changed:
                    log.info("Radio %s PTT %s", _iface.name, "ON" if rs.ptt else "off")
                if "connected" in changed:
                    log.info(
                        "Radio %s %s",
                        _iface.name,
                        "connected" if rs.connected else "disconnected",
                    )
                if (
                    _iface is state.radio_interface
                    and state.engine is not None
                    and state.band_registry is not None
                ):
                    from automation.context import AutomationContext
                    ctx = AutomationContext(
                        radio_state=rs,
                        registry=state.sensor_registry,
                        band_registry=state.band_registry,
                        radio_interface=_iface,
                        control_network=state.control_network,
                    )
                    await state.engine.process(ctx)
            return _on_radio

        iface.on_state_change(_make())
