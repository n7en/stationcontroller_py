"""Tests for automation/power_map.py."""
import pytest
from automation.power_map import (
    IdentityPowerMap,
    LinearPowerMap,
    LookupPowerMap,
    power_map_from_config,
)


class TestIdentityPowerMap:

    def test_forward_is_identity(self):
        m = IdentityPowerMap()
        assert m.forward(100.0) == pytest.approx(100.0)

    def test_inverse_is_identity(self):
        m = IdentityPowerMap()
        assert m.inverse(100.0) == pytest.approx(100.0)

    def test_round_trip(self):
        m = IdentityPowerMap()
        assert m.inverse(m.forward(75.0)) == pytest.approx(75.0)


class TestLinearPowerMap:

    def test_positive_gain_amplifies(self):
        m = LinearPowerMap(gain_db=10.0)
        # 10 dB gain → ratio = 10×
        assert m.forward(100.0) == pytest.approx(1000.0)

    def test_negative_gain_attenuates(self):
        m = LinearPowerMap(gain_db=-3.0)
        assert m.forward(100.0) == pytest.approx(50.0, rel=0.01)

    def test_zero_gain_is_identity(self):
        m = LinearPowerMap(gain_db=0.0)
        assert m.forward(100.0) == pytest.approx(100.0)

    def test_inverse_reverses_forward(self):
        m = LinearPowerMap(gain_db=20.0)
        assert m.inverse(m.forward(5.0)) == pytest.approx(5.0, rel=1e-6)

    def test_inverse_drive_from_output(self):
        # 20 dB gain → 100× ratio; want 600 W out, need 6 W drive
        m = LinearPowerMap(gain_db=20.0)
        assert m.inverse(600.0) == pytest.approx(6.0, rel=0.01)


class TestLookupPowerMap:

    @pytest.fixture
    def amp_map(self):
        # User-measured: [(radio_w, antenna_w)]
        return LookupPowerMap([(3, 300), (4, 450), (5, 600)])

    def test_exact_point_returns_value(self, amp_map):
        assert amp_map.forward(5.0) == pytest.approx(600.0)
        assert amp_map.forward(3.0) == pytest.approx(300.0)

    def test_interpolates_between_points(self, amp_map):
        assert amp_map.forward(4.0) == pytest.approx(450.0)
        assert amp_map.forward(3.5) == pytest.approx(375.0)

    def test_extrapolates_below_range(self, amp_map):
        # slope at low end: (450-300)/(4-3) = 150 W/W
        result = amp_map.forward(2.0)
        assert result == pytest.approx(150.0)

    def test_extrapolates_above_range(self, amp_map):
        # slope at top end: (600-450)/(5-4) = 150 W/W
        result = amp_map.forward(6.0)
        assert result == pytest.approx(750.0)

    def test_inverse_exact_point(self, amp_map):
        assert amp_map.inverse(600.0) == pytest.approx(5.0)

    def test_inverse_interpolated(self, amp_map):
        assert amp_map.inverse(375.0) == pytest.approx(3.5)

    def test_unsorted_input_sorted_internally(self):
        m = LookupPowerMap([(5, 600), (3, 300), (4, 450)])
        assert m.forward(4.0) == pytest.approx(450.0)

    def test_requires_at_least_two_points(self):
        with pytest.raises(ValueError):
            LookupPowerMap([(5, 600)])

    def test_round_trip(self, amp_map):
        for w in [3.0, 3.7, 4.0, 4.5, 5.0]:
            assert amp_map.inverse(amp_map.forward(w)) == pytest.approx(w, rel=1e-6)


class TestPowerMapFromConfig:

    def test_identity(self):
        m = power_map_from_config({"type": "identity"})
        assert isinstance(m, IdentityPowerMap)

    def test_linear(self):
        m = power_map_from_config({"type": "linear", "gain_db": 20.0})
        assert isinstance(m, LinearPowerMap)
        assert m.gain_db == 20.0

    def test_lookup(self):
        m = power_map_from_config({
            "type": "lookup",
            "points": [[3, 300], [4, 450], [5, 600]],
        })
        assert isinstance(m, LookupPowerMap)
        assert m.forward(5.0) == pytest.approx(600.0)

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown power_map type"):
            power_map_from_config({"type": "magic"})
