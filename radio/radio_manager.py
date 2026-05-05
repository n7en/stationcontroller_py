"""
RadioManager — orchestrates multiple RadioInterface instances.
"""
from __future__ import annotations

from .backends.hamlib_direct import HamlibDirectBackend
from .backends.managed_rigctld import ManagedRigctldBackend
from .backends.rigctld import RigctldBackend
from .config import load_radio_config
from .radio_interface import RadioInterface

_BACKEND_REGISTRY: dict[str, type] = {
    "rigctld":         RigctldBackend,
    "hamlib_direct":   HamlibDirectBackend,
    "managed_rigctld": ManagedRigctldBackend,
}

_INTERFACE_KEYS = {"name", "backend", "poll_interval_s", "reconnect_delay_s"}


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
        for iface in self._radios.values():
            await iface.connect()
            await iface.start()

    async def stop_all(self) -> None:
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
        cfg = load_radio_config(config_path)
        manager = cls()

        for entry in cfg.get("radios", []):
            name = entry["name"]
            backend_type = entry["backend"]

            backend_cls = _BACKEND_REGISTRY.get(backend_type)
            if backend_cls is None:
                raise ValueError(
                    f"Unknown backend '{backend_type}' for radio '{name}'. "
                    f"Available: {list(_BACKEND_REGISTRY)}"
                )

            backend_kwargs = {k: v for k, v in entry.items() if k not in _INTERFACE_KEYS}
            backend = backend_cls(**backend_kwargs)

            iface = RadioInterface(
                name=name,
                backend=backend,
                poll_interval_s=entry.get("poll_interval_s", 0.5),
                reconnect_delay_s=entry.get("reconnect_delay_s", 5.0),
            )
            manager.add_radio(name, iface)

        return manager
