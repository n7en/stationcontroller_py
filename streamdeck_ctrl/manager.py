"""
Stream Deck manager — detects, connects, and drives Elgato Stream Deck devices.

Optional dependency: pip install streamdeck Pillow
If either is missing the manager logs a warning and does nothing.

Supported actions per button:
  relay_toggle  — toggle a DCN relay; button reflects live sensor state
  coax_select   — select a coax switch port; button highlights when active
  radio_tune    — tune the primary radio to a preset frequency/mode
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sensors.sensor_registry import SensorRegistry

log = logging.getLogger(__name__)

RECONNECT_DELAY = 5.0

try:
    from StreamDeck.DeviceManager import DeviceManager
    from StreamDeck.ImageHelpers import PILHelper
    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False

try:
    from PIL import Image  # noqa: F401
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


class StreamDeckManager:
    """
    Manages a single connected Stream Deck device.

    Call start() once after the asyncio event loop is running.
    Call stop() on shutdown.
    """

    def __init__(
        self,
        config: dict,
        *,
        state: Any,          # AppState — passed at runtime to avoid circular import
    ) -> None:
        self._cfg   = config
        self._state = state
        self._deck  = None
        self._lock  = threading.Lock()
        self._stop_event = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        # Current sensor values tracked for button re-renders
        self._sensor_values: dict[str, Any] = {}
        # Map sensor_key → list of button indices that care about it
        self._key_watchers: dict[str, list[int]] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._deck is not None and self._deck.is_open()

    @property
    def device_info(self) -> dict:
        with self._lock:
            if self._deck is None or not self._deck.is_open():
                return {"connected": False}
            return {
                "connected":  True,
                "model":      self._deck.deck_type(),
                "key_count":  self._deck.key_count(),
                "rows":       self._deck.key_layout()[0],
                "cols":       self._deck.key_layout()[1],
                "image_size": list(self._deck.key_image_format()["size"]),
            }

    def reload_config(self, config: dict) -> None:
        """Hot-reload button assignments without restarting."""
        self._cfg = config
        self._build_watchers()
        self._render_all()

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        if not _SDK_AVAILABLE:
            log.warning(
                "streamdeck package not installed — Stream Deck support disabled. "
                "Install with: pip install streamdeck Pillow"
            )
            return
        if not _PIL_AVAILABLE:
            log.warning(
                "Pillow not installed — Stream Deck support disabled. "
                "Install with: pip install Pillow"
            )
            return
        self._loop = loop
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="streamdeck"
        )
        self._thread.start()
        log.info("Stream Deck manager started")

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            if self._deck is not None:
                try:
                    self._deck.reset()
                    self._deck.close()
                except Exception:
                    pass
                self._deck = None
        log.info("Stream Deck manager stopped")

    # ── Background thread ─────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                decks = DeviceManager().enumerate()
                if not decks:
                    time.sleep(RECONNECT_DELAY)
                    continue

                deck = decks[0]
                deck.open()
                deck.reset()
                brightness = int(self._cfg.get("brightness", 70))
                deck.set_brightness(brightness)
                deck.set_key_callback(self._on_key_change)

                with self._lock:
                    self._deck = deck

                log.info(
                    "Stream Deck connected: %s (%d keys)",
                    deck.deck_type(), deck.key_count(),
                )

                self._build_watchers()
                self._render_all()

                # Register sensor callbacks now that we have a deck
                self._attach_sensor_callbacks()

                # Wait until device is disconnected or stop requested
                while not self._stop_event.is_set():
                    with self._lock:
                        if self._deck is None or not self._deck.is_open():
                            break
                    time.sleep(1.0)

            except Exception:
                log.exception("Stream Deck error — will retry in %.0fs", RECONNECT_DELAY)

            with self._lock:
                if self._deck is not None:
                    try:
                        self._deck.close()
                    except Exception:
                        pass
                    self._deck = None

            if not self._stop_event.is_set():
                log.info("Stream Deck disconnected — retrying in %.0fs", RECONNECT_DELAY)
                time.sleep(RECONNECT_DELAY)

    # ── Sensor callbacks ──────────────────────────────────────────────────────

    def _attach_sensor_callbacks(self) -> None:
        reg: Optional[SensorRegistry] = getattr(self._state, "sensor_registry", None)
        if reg is None:
            return

        def _on_sensor(measurement) -> None:
            key = measurement.name
            if key not in self._key_watchers:
                return
            self._sensor_values[key] = measurement.value
            for btn_idx in self._key_watchers[key]:
                self._render_button(btn_idx)

        reg.on_any(_on_sensor)

    def _build_watchers(self) -> None:
        self._key_watchers = {}
        for btn in self._cfg.get("buttons", []):
            sk = btn.get("sensor_key", "")
            if not sk:
                continue
            idx = btn.get("index", -1)
            if idx < 0:
                continue
            self._key_watchers.setdefault(sk, []).append(idx)

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render_all(self) -> None:
        with self._lock:
            deck = self._deck
        if deck is None:
            return
        count = deck.key_count()
        btn_map = {b["index"]: b for b in self._cfg.get("buttons", []) if "index" in b}
        for i in range(count):
            self._render_button(i, btn_map.get(i))

    def _render_button(self, index: int, btn: Optional[dict] = None) -> None:
        with self._lock:
            deck = self._deck
        if deck is None:
            return
        if btn is None:
            btn_map = {b["index"]: b for b in self._cfg.get("buttons", []) if "index" in b}
            btn = btn_map.get(index)

        from .renderer import render_button
        fmt    = deck.key_image_format()
        w, h   = fmt["size"]
        btype  = btn.get("type", "blank") if btn else "blank"
        label  = btn.get("label", "") if btn else ""
        active, state_text = self._resolve_state(btn)

        try:
            img = render_button(
                w, h,
                btn_type=btype,
                label=label,
                state_text=state_text,
                active=active,
            )
            native = PILHelper.to_native_format(deck, img)
            with self._lock:
                if self._deck is not None and self._deck.is_open():
                    self._deck.set_key_image(index, native)
        except Exception:
            log.exception("Stream Deck: failed to render button %d", index)

    def _resolve_state(self, btn: Optional[dict]) -> tuple[bool, str]:
        """Return (active, state_text) for a button based on current sensor values."""
        if not btn:
            return False, ""
        btype = btn.get("type", "blank")

        if btype == "relay_toggle":
            sk  = btn.get("sensor_key", "")
            val = self._sensor_values.get(sk)
            on  = bool(val) if val is not None else False
            return on, "ON" if on else "OFF"

        if btype == "coax_select":
            sk   = btn.get("sensor_key", "")
            port = int(btn.get("port", 0))
            cur  = self._sensor_values.get(sk)
            sel  = (int(cur) == port) if cur is not None else False
            return sel, f"Port {port + 1}"

        if btype == "radio_tune":
            hz   = int(btn.get("frequency_hz", 0))
            mode = btn.get("mode", "")
            mhz  = f"{hz / 1_000_000:.3f}".rstrip("0").rstrip(".")
            return False, f"{mhz}\n{mode}"

        return False, ""

    # ── Key press handler (called from SDK thread) ────────────────────────────

    def _on_key_change(self, deck, key: int, pressed: bool) -> None:
        if not pressed:
            return
        btn_map = {b["index"]: b for b in self._cfg.get("buttons", []) if "index" in b}
        btn = btn_map.get(key)
        if not btn:
            return
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(self._dispatch(btn), self._loop)

    async def _dispatch(self, btn: dict) -> None:
        btype = btn.get("type", "")
        try:
            if btype == "relay_toggle":
                await self._action_relay(btn)
            elif btype == "coax_select":
                await self._action_coax(btn)
            elif btype == "radio_tune":
                await self._action_radio(btn)
        except Exception:
            log.exception("Stream Deck: action error for button type %r", btype)

    # ── Actions ───────────────────────────────────────────────────────────────

    async def _action_relay(self, btn: dict) -> None:
        sk         = btn.get("sensor_key", "")
        relay_num  = int(btn.get("relay_num", 0))
        device_addr = btn.get("device_addr", "01")
        bus        = btn.get("bus") or None

        cur = self._sensor_values.get(sk)
        new_state = 0 if cur else 1

        network = self._state.network_for_addr(device_addr, bus=bus)
        if network is None:
            log.warning("Stream Deck relay: no network for addr %s bus %s", device_addr, bus)
            return
        await network.send(device_addr, f"RY{relay_num},{new_state}")

    async def _action_coax(self, btn: dict) -> None:
        port        = int(btn.get("port", 0))
        device_addr = btn.get("device_addr", "02")
        bus         = btn.get("bus") or None

        for dev in self._state.devices.values():
            if getattr(dev, "address", None) == device_addr and hasattr(dev, "optimistic_select"):
                if not bus or getattr(dev, "bus", None) == bus:
                    dev.optimistic_select(port)
                    break

        network = self._state.network_for_addr(device_addr, bus=bus)
        if network is None:
            log.warning("Stream Deck coax: no network for addr %s bus %s", device_addr, bus)
            return
        await network.send(device_addr, f"CX,{port}")

    async def _action_radio(self, btn: dict) -> None:
        radio_name = btn.get("radio_name", "")
        hz         = float(btn.get("frequency_hz", 0))
        mode       = btn.get("mode", "")

        rm = getattr(self._state, "radio_manager", None)
        if rm is None:
            log.warning("Stream Deck radio_tune: no radio_manager")
            return

        iface = (
            rm[radio_name]
            if radio_name and hasattr(rm, "__getitem__") and radio_name in getattr(rm, "_radios", {})
            else getattr(self._state, "radio_interface", None)
        )
        if iface is None:
            log.warning("Stream Deck radio_tune: no radio interface")
            return

        if hz:
            await iface.set_frequency(hz)
        if mode:
            await iface.set_mode(mode, 0)
