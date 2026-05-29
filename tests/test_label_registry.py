"""Tests for sensors/label_registry.py and SensorRegistry label integration."""
import io
import pytest
import yaml

from sensors.label_registry import LabelRegistry
from sensors.sensor_registry import SensorRegistry


# ---------------------------------------------------------------------------
# LabelRegistry - basic operations
# ---------------------------------------------------------------------------

class TestLabelRegistryBasics:

    def test_set_and_resolve_by_label(self):
        lr = LabelRegistry()
        lr.set("coax_port_1", "20m Yagi")
        assert lr.resolve("20m Yagi") == "coax_port_1"

    def test_resolve_hardware_key_passthrough(self):
        lr = LabelRegistry()
        lr.set("coax_port_1", "20m Yagi")
        assert lr.resolve("coax_port_1") == "coax_port_1"

    def test_resolve_unknown_name_passthrough(self):
        lr = LabelRegistry()
        assert lr.resolve("some_unknown_sensor") == "some_unknown_sensor"

    def test_label_for_returns_label(self):
        lr = LabelRegistry()
        lr.set("coax_port_1", "20m Yagi")
        assert lr.label_for("coax_port_1") == "20m Yagi"

    def test_label_for_returns_key_when_unlabelled(self):
        lr = LabelRegistry()
        assert lr.label_for("coax_port_3") == "coax_port_3"

    def test_key_for_returns_hardware_key(self):
        lr = LabelRegistry()
        lr.set("coax_port_1", "20m Yagi")
        assert lr.key_for("20m Yagi") == "coax_port_1"

    def test_key_for_returns_none_when_unknown(self):
        lr = LabelRegistry()
        assert lr.key_for("Unknown Label") is None

    def test_contains_true_when_labelled(self):
        lr = LabelRegistry()
        lr.set("coax_port_1", "20m Yagi")
        assert "coax_port_1" in lr

    def test_contains_false_when_not_labelled(self):
        lr = LabelRegistry()
        assert "coax_port_2" not in lr

    def test_len(self):
        lr = LabelRegistry()
        lr.set("coax_port_1", "20m Yagi")
        lr.set("coax_port_2", "40m Dipole")
        assert len(lr) == 2

    def test_all_returns_copy(self):
        lr = LabelRegistry()
        lr.set("coax_port_1", "20m Yagi")
        lr.set("coax_port_2", "40m Dipole")
        d = lr.all()
        assert d == {"coax_port_1": "20m Yagi", "coax_port_2": "40m Dipole"}
        d["coax_port_1"] = "mutated"
        assert lr.label_for("coax_port_1") == "20m Yagi"


# ---------------------------------------------------------------------------
# LabelRegistry - mutation edge cases
# ---------------------------------------------------------------------------

class TestLabelRegistryMutation:

    def test_remove_clears_both_directions(self):
        lr = LabelRegistry()
        lr.set("coax_port_1", "20m Yagi")
        lr.remove("coax_port_1")
        assert lr.resolve("20m Yagi") == "20m Yagi"
        assert lr.label_for("coax_port_1") == "coax_port_1"
        assert "coax_port_1" not in lr

    def test_remove_noop_when_not_labelled(self):
        lr = LabelRegistry()
        lr.remove("nonexistent")  # should not raise

    def test_set_replaces_old_label(self):
        lr = LabelRegistry()
        lr.set("coax_port_1", "20m Yagi")
        lr.set("coax_port_1", "20m Beam")
        assert lr.label_for("coax_port_1") == "20m Beam"
        assert lr.key_for("20m Yagi") is None
        assert lr.key_for("20m Beam") == "coax_port_1"

    def test_set_label_to_different_key_replaces_old_key(self):
        lr = LabelRegistry()
        lr.set("coax_port_1", "20m Yagi")
        lr.set("coax_port_2", "20m Yagi")  # steal the label
        assert lr.key_for("20m Yagi") == "coax_port_2"
        assert lr.label_for("coax_port_1") == "coax_port_1"  # now unlabelled
        assert len(lr) == 1

    def test_multiple_labels(self):
        lr = LabelRegistry()
        lr.set("coax_port_1", "20m Yagi")
        lr.set("coax_port_2", "40m Dipole")
        lr.set("ant_relay_1", "Amp Bypass")
        assert lr.resolve("40m Dipole") == "coax_port_2"
        assert lr.resolve("Amp Bypass") == "ant_relay_1"


# ---------------------------------------------------------------------------
# LabelRegistry - YAML persistence
# ---------------------------------------------------------------------------

class TestLabelRegistryYaml:

    def test_save_and_reload(self, tmp_path):
        lr = LabelRegistry()
        lr.set("coax_port_1", "20m Yagi")
        lr.set("coax_port_2", "40m Dipole")
        p = tmp_path / "labels.yaml"
        lr.save(p)
        lr2 = LabelRegistry.from_yaml(p)
        assert lr2.label_for("coax_port_1") == "20m Yagi"
        assert lr2.label_for("coax_port_2") == "40m Dipole"
        assert lr2.resolve("20m Yagi") == "coax_port_1"

    def test_from_yaml_missing_file_returns_empty(self, tmp_path):
        lr = LabelRegistry.from_yaml(tmp_path / "does_not_exist.yaml")
        assert len(lr) == 0

    def test_from_yaml_empty_file_returns_empty(self, tmp_path):
        p = tmp_path / "labels.yaml"
        p.write_text("")
        lr = LabelRegistry.from_yaml(p)
        assert len(lr) == 0

    def test_save_is_sorted(self, tmp_path):
        lr = LabelRegistry()
        lr.set("coax_port_2", "40m Dipole")
        lr.set("coax_port_1", "20m Yagi")
        p = tmp_path / "labels.yaml"
        lr.save(p)
        raw = yaml.safe_load(p.read_text())
        keys = list(raw["labels"].keys())
        assert keys == sorted(keys)

    def test_roundtrip_unicode_label(self, tmp_path):
        lr = LabelRegistry()
        lr.set("coax_port_1", "Yağı Anteni")
        p = tmp_path / "labels.yaml"
        lr.save(p)
        lr2 = LabelRegistry.from_yaml(p)
        assert lr2.label_for("coax_port_1") == "Yağı Anteni"

    def test_loads_bundled_config(self):
        """Smoke-test that config/labels.yaml parses cleanly."""
        from pathlib import Path
        config_path = Path(__file__).parent.parent / "config" / "labels.yaml"
        lr = LabelRegistry.from_yaml(config_path)
        assert len(lr) > 0
        assert lr.resolve("20m Yagi") == "coax_port_0"


# ---------------------------------------------------------------------------
# SensorRegistry - label integration
# ---------------------------------------------------------------------------

class TestSensorRegistryLabelIntegration:

    def _make_reg(self) -> tuple[SensorRegistry, LabelRegistry]:
        lr = LabelRegistry()
        lr.set("coax_port_1", "20m Yagi")
        lr.set("coax_port_2", "40m Dipole")
        reg = SensorRegistry()
        reg.attach_labels(lr)
        reg.publish("coax_port_1", 1.0, source="test")
        reg.publish("coax_port_2", 0.0, source="test")
        return reg, lr

    def test_get_by_label(self):
        reg, _ = self._make_reg()
        m = reg.get("20m Yagi")
        assert m is not None
        assert m.value == pytest.approx(1.0)

    def test_get_by_hardware_key(self):
        reg, _ = self._make_reg()
        m = reg.get("coax_port_1")
        assert m is not None
        assert m.value == pytest.approx(1.0)

    def test_value_by_label(self):
        reg, _ = self._make_reg()
        assert reg.value("20m Yagi") == pytest.approx(1.0)
        assert reg.value("40m Dipole") == pytest.approx(0.0)

    def test_value_by_hardware_key(self):
        reg, _ = self._make_reg()
        assert reg.value("coax_port_1") == pytest.approx(1.0)

    def test_is_stale_by_label(self):
        reg, _ = self._make_reg()
        assert reg.is_stale("20m Yagi", max_age_s=999) is False

    def test_is_stale_unknown_label(self):
        reg, _ = self._make_reg()
        assert reg.is_stale("Does Not Exist", max_age_s=999) is True

    def test_snapshot_uses_hardware_keys(self):
        reg, _ = self._make_reg()
        s = reg.snapshot()
        assert "coax_port_1" in s
        assert "20m Yagi" not in s

    def test_snapshot_labeled_uses_friendly_names(self):
        reg, _ = self._make_reg()
        s = reg.snapshot_labeled()
        assert "20m Yagi" in s
        assert "40m Dipole" in s
        assert "coax_port_1" not in s
        assert "coax_port_2" not in s

    def test_snapshot_labeled_keeps_unlabelled_key(self):
        reg, _ = self._make_reg()
        reg.publish("watt_meter_swr", 1.5, source="test")
        s = reg.snapshot_labeled()
        assert "watt_meter_swr" in s  # no label -> key unchanged

    def test_snapshot_labeled_without_labels_matches_snapshot(self):
        reg = SensorRegistry()
        reg.publish("coax_port_1", 1.0)
        assert reg.snapshot_labeled() == reg.snapshot()

    def test_no_labels_attached_passthrough(self):
        reg = SensorRegistry()
        reg.publish("coax_port_1", 1.0)
        assert reg.value("coax_port_1") == pytest.approx(1.0)
        assert reg.value("20m Yagi") == pytest.approx(0.0)  # unknown -> default

    def test_detached_label_resolves_to_itself(self):
        reg, lr = self._make_reg()
        lr.remove("coax_port_1")
        assert reg.value("20m Yagi") == pytest.approx(0.0)  # label gone
        assert reg.value("coax_port_1") == pytest.approx(1.0)  # key still works

    def test_update_label_and_resolve_new_name(self):
        reg, lr = self._make_reg()
        lr.set("coax_port_1", "20m Beam")  # rename label
        assert reg.value("20m Beam") == pytest.approx(1.0)
        assert reg.value("20m Yagi") == pytest.approx(0.0)  # old label gone
