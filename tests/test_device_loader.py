"""
Tests for devices/loader.py — config-driven device instantiation.
Uses real device classes with in-memory DCNNetwork buses.
"""
import pytest
from pathlib import Path

from comms.dcn_network import DCNNetwork
from devices.loader import load_devices
from sensors.sensor_registry import SensorRegistry


def _yaml(content: str, tmp_path: Path) -> Path:
    p = tmp_path / "cfg.yaml"
    p.write_text(content)
    return p


@pytest.fixture
def registry():
    return SensorRegistry()


# ---------------------------------------------------------------------------
# Happy-path loading
# ---------------------------------------------------------------------------

class TestLoadDevicesHappyPath:

    def test_returns_device_keyed_by_name(self, tmp_path, registry):
        path = _yaml(
            "devices:\n"
            "  - type: gpio\n"
            "    name: gpio\n"
            "    address: '01'\n"
            "    bus: control\n",
            tmp_path,
        )
        networks = {"control": DCNNetwork()}
        devices, _ = load_devices(path, registry, networks)
        assert "gpio" in devices

    def test_addr_bus_map_populated(self, tmp_path, registry):
        path = _yaml(
            "devices:\n"
            "  - type: gpio\n"
            "    name: gpio\n"
            "    address: '01'\n"
            "    bus: control\n",
            tmp_path,
        )
        networks = {"control": DCNNetwork()}
        _, addr_bus = load_devices(path, registry, networks)
        assert addr_bus["01"] == "control"

    def test_multiple_devices_on_same_bus(self, tmp_path, registry):
        path = _yaml(
            "devices:\n"
            "  - type: gpio\n"
            "    name: gpio\n"
            "    address: '01'\n"
            "    bus: control\n"
            "  - type: watt_meter\n"
            "    name: watt_01\n"
            "    address: '02'\n"
            "    bus: control\n",
            tmp_path,
        )
        networks = {"control": DCNNetwork()}
        devices, addr_bus = load_devices(path, registry, networks)
        assert len(devices) == 2
        assert addr_bus["01"] == "control"
        assert addr_bus["02"] == "control"

    def test_devices_on_separate_buses(self, tmp_path, registry):
        path = _yaml(
            "devices:\n"
            "  - type: gpio\n"
            "    name: gpio\n"
            "    address: '01'\n"
            "    bus: control\n"
            "  - type: watt_meter\n"
            "    name: power_01\n"
            "    address: '03'\n"
            "    bus: power\n",
            tmp_path,
        )
        networks = {"control": DCNNetwork(), "power": DCNNetwork()}
        devices, addr_bus = load_devices(path, registry, networks)
        assert addr_bus["01"] == "control"
        assert addr_bus["03"] == "power"

    def test_same_address_on_two_buses_first_wins(self, tmp_path, registry):
        """When address '03' appears on both buses, the first entry in the
        devices list wins the addr_bus slot — backward-compat routing."""
        path = _yaml(
            "devices:\n"
            "  - type: watt_meter\n"
            "    name: watt_power1\n"
            "    address: '03'\n"
            "    bus: power1\n"
            "  - type: watt_meter\n"
            "    name: watt_power2\n"
            "    address: '03'\n"
            "    bus: power2\n",
            tmp_path,
        )
        networks = {"power1": DCNNetwork(), "power2": DCNNetwork()}
        devices, addr_bus = load_devices(path, registry, networks)
        assert len(devices) == 2
        assert addr_bus["03"] == "power1"

    def test_empty_devices_list(self, tmp_path, registry):
        path = _yaml("devices: []\n", tmp_path)
        networks = {"control": DCNNetwork()}
        devices, addr_bus = load_devices(path, registry, networks)
        assert devices == {}
        assert addr_bus == {}

    def test_no_devices_key(self, tmp_path, registry):
        path = _yaml("buses: []\n", tmp_path)
        networks = {}
        devices, addr_bus = load_devices(path, registry, networks)
        assert devices == {}
        assert addr_bus == {}


# ---------------------------------------------------------------------------
# Error / edge cases
# ---------------------------------------------------------------------------

class TestLoadDevicesEdgeCases:

    def test_unknown_device_type_skipped(self, tmp_path, registry):
        path = _yaml(
            "devices:\n"
            "  - type: laser_cannon\n"
            "    name: zap\n"
            "    address: '09'\n"
            "    bus: control\n",
            tmp_path,
        )
        networks = {"control": DCNNetwork()}
        devices, addr_bus = load_devices(path, registry, networks)
        assert devices == {}
        assert addr_bus == {}

    def test_missing_bus_device_still_created(self, tmp_path, registry):
        """Device is created even when its bus is absent; it just has no network."""
        path = _yaml(
            "devices:\n"
            "  - type: gpio\n"
            "    name: gpio\n"
            "    address: '01'\n"
            "    bus: nonexistent\n",
            tmp_path,
        )
        networks = {}
        devices, addr_bus = load_devices(path, registry, networks)
        assert "gpio" in devices
        assert addr_bus["01"] == "nonexistent"

    def test_duplicate_device_name_second_skipped(self, tmp_path, registry):
        path = _yaml(
            "devices:\n"
            "  - type: gpio\n"
            "    name: gpio\n"
            "    address: '01'\n"
            "    bus: control\n"
            "  - type: gpio\n"
            "    name: gpio\n"
            "    address: '02'\n"
            "    bus: control\n",
            tmp_path,
        )
        networks = {"control": DCNNetwork()}
        devices, addr_bus = load_devices(path, registry, networks)
        assert len(devices) == 1
        assert "02" not in addr_bus  # second entry was skipped

    def test_mixed_valid_and_invalid_types(self, tmp_path, registry):
        path = _yaml(
            "devices:\n"
            "  - type: gpio\n"
            "    name: gpio\n"
            "    address: '01'\n"
            "    bus: control\n"
            "  - type: unknown_device\n"
            "    name: bad\n"
            "    address: '99'\n"
            "    bus: control\n",
            tmp_path,
        )
        networks = {"control": DCNNetwork()}
        devices, addr_bus = load_devices(path, registry, networks)
        assert "gpio" in devices
        assert "bad" not in devices
