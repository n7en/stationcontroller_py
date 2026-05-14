"""
LabelRegistry - friendly name mappings for hardware sensor keys.

Maps hardware sensor keys (e.g. "coax_port_1") to user-facing labels
(e.g. "20m Yagi") and back.  Labels are optional: hardware keys always
work whether or not a label exists.

Typical usage::

    lr = LabelRegistry()
    lr.set("coax_port_1", "20m Yagi")
    lr.set("coax_port_2", "40m Dipole")

    lr.resolve("20m Yagi")      # -> "coax_port_1"
    lr.resolve("coax_port_1")   # -> "coax_port_1"  (passthrough)
    lr.label_for("coax_port_1") # -> "20m Yagi"
    lr.label_for("coax_port_3") # -> "coax_port_3"  (no label -> returns key)

Load from / save to YAML::

    lr = LabelRegistry.from_yaml("config/labels.yaml")
    lr.set("coax_port_3", "80m Dipole")
    lr.save("config/labels.yaml")
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml


class LabelRegistry:
    """Bidirectional map between hardware sensor keys and friendly display names."""

    def __init__(self) -> None:
        self._by_key: dict[str, str] = {}    # hardware_key -> label
        self._by_label: dict[str, str] = {}  # label -> hardware_key

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def set(self, hardware_key: str, label: str) -> None:
        """Assign *label* to *hardware_key*, replacing any previous mapping."""
        old_label = self._by_key.get(hardware_key)
        if old_label is not None:
            self._by_label.pop(old_label, None)

        old_key = self._by_label.get(label)
        if old_key is not None:
            self._by_key.pop(old_key, None)

        self._by_key[hardware_key] = label
        self._by_label[label] = hardware_key

    def set_default(self, hardware_key: str, label: str) -> None:
        """Assign *label* to *hardware_key* only if no label is already set."""
        if hardware_key not in self._by_key:
            self.set(hardware_key, label)

    def remove(self, hardware_key: str) -> None:
        """Remove the label for *hardware_key* (no-op if not labelled)."""
        label = self._by_key.pop(hardware_key, None)
        if label is not None:
            self._by_label.pop(label, None)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def resolve(self, name: str) -> str:
        """
        Return the hardware key for *name*.

        If *name* is a known label, return the corresponding hardware key.
        If *name* is already a hardware key (or unknown), return it unchanged.
        """
        return self._by_label.get(name, name)

    def label_for(self, hardware_key: str) -> str:
        """Return the friendly label for *hardware_key*, or the key itself if unlabelled."""
        return self._by_key.get(hardware_key, hardware_key)

    def key_for(self, label: str) -> Optional[str]:
        """Return the hardware key for *label*, or None if the label is not registered."""
        return self._by_label.get(label)

    def all(self) -> dict[str, str]:
        """Return a copy of the full hardware_key -> label mapping."""
        return dict(self._by_key)

    def __len__(self) -> int:
        return len(self._by_key)

    def __contains__(self, hardware_key: str) -> bool:
        """True if *hardware_key* has a registered label."""
        return hardware_key in self._by_key

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        """Write the label mapping to a YAML file."""
        path = Path(path)
        payload = {"labels": dict(sorted(self._by_key.items()))}
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            yaml.dump(payload, fh, default_flow_style=False, allow_unicode=True)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "LabelRegistry":
        """Load a LabelRegistry from a YAML file (key: "labels")."""
        lr = cls()
        path = Path(path)
        if not path.exists():
            return lr
        with open(path, encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
        for key, label in (cfg.get("labels") or {}).items():
            lr.set(str(key), str(label))
        return lr
