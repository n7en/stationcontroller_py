"""
Tests for radio/radio_manager.py and radio/config.py.
"""
import pytest

from radio.backends.base import RadioBackendError
from radio.radio_interface import RadioInterface
from radio.radio_manager import RadioManager
from radio.config import load_radio_config

from tests.test_radio_interface import FakeBackend


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

class TestLoadRadioConfig:

    def test_loads_valid_config(self, tmp_path):
        f = tmp_path / "radio.yaml"
        f.write_text(
            "radios:\n"
            "  - name: ic7300\n"
            "    backend: rigctld\n"
            "    host: localhost\n"
            "    port: 4532\n"
        )
        cfg = load_radio_config(str(f))
        assert len(cfg["radios"]) == 1
        assert cfg["radios"][0]["name"] == "ic7300"

    def test_loads_multiple_radios(self, tmp_path):
        f = tmp_path / "radio.yaml"
        f.write_text(
            "radios:\n"
            "  - name: radio1\n"
            "    backend: rigctld\n"
            "    port: 4532\n"
            "  - name: radio2\n"
            "    backend: rigctld\n"
            "    port: 4533\n"
        )
        cfg = load_radio_config(str(f))
        assert len(cfg["radios"]) == 2

    def test_missing_name_raises(self, tmp_path):
        f = tmp_path / "radio.yaml"
        f.write_text("radios:\n  - backend: rigctld\n")
        with pytest.raises(ValueError, match="name"):
            load_radio_config(str(f))

    def test_missing_backend_raises(self, tmp_path):
        f = tmp_path / "radio.yaml"
        f.write_text("radios:\n  - name: ic7300\n")
        with pytest.raises(ValueError, match="backend"):
            load_radio_config(str(f))

    def test_not_a_mapping_raises(self, tmp_path):
        f = tmp_path / "radio.yaml"
        f.write_text("- just a list\n")
        with pytest.raises(ValueError, match="mapping"):
            load_radio_config(str(f))

    def test_radios_not_a_list_raises(self, tmp_path):
        f = tmp_path / "radio.yaml"
        f.write_text("radios: not_a_list\n")
        with pytest.raises(ValueError, match="list"):
            load_radio_config(str(f))

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_radio_config(str(tmp_path / "nonexistent.yaml"))


# ---------------------------------------------------------------------------
# RadioManager - manual construction
# ---------------------------------------------------------------------------

class TestRadioManagerManual:

    def test_add_and_get(self):
        mgr = RadioManager()
        b = FakeBackend()
        iface = RadioInterface("rig1", b)
        mgr.add_radio("rig1", iface)
        assert mgr.get("rig1") is iface

    def test_getitem(self):
        mgr = RadioManager()
        b = FakeBackend()
        iface = RadioInterface("rig1", b)
        mgr.add_radio("rig1", iface)
        assert mgr["rig1"] is iface

    def test_get_missing_raises(self):
        mgr = RadioManager()
        with pytest.raises(KeyError, match="rig1"):
            mgr.get("rig1")

    def test_names_returns_all(self):
        mgr = RadioManager()
        for name in ("a", "b", "c"):
            mgr.add_radio(name, RadioInterface(name, FakeBackend()))
        assert set(mgr.names()) == {"a", "b", "c"}

    def test_iteration_yields_all_interfaces(self):
        mgr = RadioManager()
        ifaces = [RadioInterface(n, FakeBackend()) for n in ("x", "y")]
        for i in ifaces:
            mgr.add_radio(i.name, i)
        result = list(mgr)
        assert set(result) == set(ifaces)


# ---------------------------------------------------------------------------
# RadioManager.from_config
# ---------------------------------------------------------------------------

class TestFromConfig:

    def test_from_config_creates_rigctld_backend(self, tmp_path):
        from radio.backends.rigctld import RigctldBackend
        f = tmp_path / "radio.yaml"
        f.write_text(
            "radios:\n"
            "  - name: ic7300\n"
            "    backend: rigctld\n"
            "    host: localhost\n"
            "    port: 4532\n"
        )
        mgr = RadioManager.from_config(str(f))
        iface = mgr["ic7300"]
        assert isinstance(iface._backend, RigctldBackend)
        assert iface._backend._host == "localhost"
        assert iface._backend._port == 4532

    def test_from_config_sets_poll_interval(self, tmp_path):
        f = tmp_path / "radio.yaml"
        f.write_text(
            "radios:\n"
            "  - name: rig\n"
            "    backend: rigctld\n"
            "    port: 4532\n"
            "    poll_interval_s: 2.0\n"
        )
        mgr = RadioManager.from_config(str(f))
        assert mgr["rig"]._poll_interval == 2.0

    def test_from_config_default_poll_interval(self, tmp_path):
        f = tmp_path / "radio.yaml"
        f.write_text(
            "radios:\n"
            "  - name: rig\n"
            "    backend: rigctld\n"
            "    port: 4532\n"
        )
        mgr = RadioManager.from_config(str(f))
        assert mgr["rig"]._poll_interval == 0.5

    def test_from_config_unknown_backend_raises(self, tmp_path):
        f = tmp_path / "radio.yaml"
        f.write_text(
            "radios:\n"
            "  - name: rig\n"
            "    backend: nonexistent\n"
        )
        with pytest.raises(ValueError, match="nonexistent"):
            RadioManager.from_config(str(f))

    def test_from_config_multiple_radios(self, tmp_path):
        f = tmp_path / "radio.yaml"
        f.write_text(
            "radios:\n"
            "  - name: hf\n"
            "    backend: rigctld\n"
            "    port: 4532\n"
            "  - name: vhf\n"
            "    backend: rigctld\n"
            "    port: 4533\n"
        )
        mgr = RadioManager.from_config(str(f))
        assert set(mgr.names()) == {"hf", "vhf"}
        assert mgr["hf"]._backend._port == 4532
        assert mgr["vhf"]._backend._port == 4533


# ---------------------------------------------------------------------------
# RadioManager - async lifecycle
# ---------------------------------------------------------------------------

class TestManagerLifecycle:

    async def test_context_manager_connects_all(self):
        mgr = RadioManager()
        backends = [FakeBackend(), FakeBackend()]
        for i, b in enumerate(backends):
            mgr.add_radio(f"r{i}", RadioInterface(f"r{i}", b, poll_interval_s=0.05))

        async with mgr:
            for b in backends:
                assert b.connected

    async def test_context_manager_disconnects_all(self):
        mgr = RadioManager()
        backends = [FakeBackend(), FakeBackend()]
        for i, b in enumerate(backends):
            mgr.add_radio(f"r{i}", RadioInterface(f"r{i}", b, poll_interval_s=0.05))

        async with mgr:
            pass

        for b in backends:
            assert not b.connected
