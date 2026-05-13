"""
RadioManager - orchestrates multiple RadioInterface instances.
"""
from __future__ import annotations

import logging

from .backends.elecraft_k4 import ElecraftK4Backend
from .backends.hamlib_direct import HamlibDirectBackend
from .backends.managed_rigctld import ManagedRigctldBackend
from .backends.rigctld import RigctldBackend
from .config import load_radio_config
from .radio_interface import RadioInterface

log = logging.getLogger(__name__)

_BACKEND_REGISTRY: dict[str, type] = {
    "rigctld":         RigctldBackend,
    "hamlib_direct":   HamlibDirectBackend,
    "managed_rigctld": ManagedRigctldBackend,
    "elecraft_k4":     ElecraftK4Backend,
}

_INTERFACE_KEYS = {"name", "backend", "enabled", "poll_interval_s", "reconnect_delay_s"}


class RadioManager:
    """
    Manages a collection of named RadioInterface instances.

    Usage::

        async with RadioManager.from_config("config/radio_config.yaml") as mgr:
            radio = mgr["ic7300"]
            await radio.set_frequency(14_200_000)
    """

    def __init__(self) -> None:
        self._radios: dict[str, RadioInterface] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def add_radio(self, name: str, interface: RadioInterface) -> None:
        log.debug("Registering radio '%s'", name)
        self._radios[name] = interface

    def get(self, name: str) -> RadioInterface:
        try:
            return self._radios[name]
        except KeyError:
            raise KeyError(f"No radio named '{name}'") from None

    def __getitem__(self, name: str) -> RadioInterface:
        return self.get(name)

    def names(self) -> list[str]:
        return list(self._radios.keys())

    def __iter__(self):
        return iter(self._radios.values())

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start_all(self) -> None:
        log.info("Starting all %d radio(s): %s", len(self._radios), list(self._radios))
        for iface in self._radios.values():
            await iface.connect()
            await iface.start()

    async def stop_all(self) -> None:
        log.info("Stopping all %d radio(s): %s", len(self._radios), list(self._radios))
        for iface in self._radios.values():
            await iface.stop()
            await iface.disconnect()

    async def __aenter__(self) -> "RadioManager":
        await self.start_all()
        return self

    async def __aexit__(self, *_) -> None:
        await self.stop_all()

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, config_path: str) -> "RadioManager":
        log.info("Loading radio configuration from %s", config_path)
        cfg = load_radio_config(config_path)
        manager = cls()

        for entry in cfg.get("radios", []):
            if not entry.get("enabled", True):
                log.info("Radio '%s' is disabled - skipping", entry.get("name", "?"))
                continue
            name = entry["name"]
            backend_type = entry["backend"]

            backend_cls = _BACKEND_REGISTRY.get(backend_type)
            if backend_cls is None:
                log.error(
                    "Unknown backend '%s' for radio '%s' - skipping (available: %s)",
                    backend_type, name, list(_BACKEND_REGISTRY),
                )
                raise ValueError(
                    f"Unknown backend '{backend_type}' for radio '{name}'. "
                    f"Available: {list(_BACKEND_REGISTRY)}"
                )

            backend_kwargs = {k: v for k, v in entry.items() if k not in _INTERFACE_KEYS}
            log.debug("Building radio '%s': backend=%s kwargs=%s", name, backend_type, backend_kwargs)
            backend = backend_cls(**backend_kwargs)

            iface = RadioInterface(
                name=name,
                backend=backend,
                poll_interval_s=entry.get("poll_interval_s", 0.5),
                reconnect_delay_s=entry.get("reconnect_delay_s", 5.0),
            )
            manager.add_radio(name, iface)
            log.info("Configured radio '%s' (backend: %s)", name, backend_type)

        log.info("RadioManager ready: %d radio(s) configured", len(manager._radios))
        return manager
