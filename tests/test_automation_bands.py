"""Tests for automation/bands.py."""
import pytest
from automation.bands import Band, BandRegistry


class TestBand:

    def test_contains_freq_in_range(self):
        b = Band("20m", 14_000_000, 14_350_000)
        assert b.contains(14_200_000) is True

    def test_contains_lower_edge(self):
        b = Band("20m", 14_000_000, 14_350_000)
        assert b.contains(14_000_000) is True

    def test_contains_upper_edge(self):
        b = Band("20m", 14_000_000, 14_350_000)
        assert b.contains(14_350_000) is True

    def test_does_not_contain_freq_below(self):
        b = Band("20m", 14_000_000, 14_350_000)
        assert b.contains(7_000_000) is False

    def test_does_not_contain_freq_above(self):
        b = Band("20m", 14_000_000, 14_350_000)
        assert b.contains(21_000_000) is False

    def test_band_is_hashable(self):
        b = Band("20m", 14_000_000, 14_350_000)
        s = {b}
        assert b in s


class TestBandRegistry:

    def test_band_for_freq_returns_correct_band(self):
        reg = BandRegistry([
            Band("40m", 7_000_000, 7_300_000),
            Band("20m", 14_000_000, 14_350_000),
        ])
        assert reg.band_for_freq(14_200_000).name == "20m"
        assert reg.band_for_freq(7_100_000).name == "40m"

    def test_band_for_freq_returns_none_out_of_band(self):
        reg = BandRegistry([Band("20m", 14_000_000, 14_350_000)])
        assert reg.band_for_freq(10_000_000) is None

    def test_band_by_name_found(self):
        reg = BandRegistry([Band("40m", 7_000_000, 7_300_000)])
        assert reg.band("40m") is not None
        assert reg.band("40m").name == "40m"

    def test_band_by_name_not_found(self):
        reg = BandRegistry([Band("40m", 7_000_000, 7_300_000)])
        assert reg.band("160m") is None

    def test_names_returns_all(self):
        reg = BandRegistry([
            Band("40m", 7_000_000, 7_300_000),
            Band("20m", 14_000_000, 14_350_000),
        ])
        assert reg.names() == ["40m", "20m"]

    def test_len(self):
        reg = BandRegistry([Band("40m", 7_000_000, 7_300_000)])
        assert len(reg) == 1

    def test_empty_registry(self):
        reg = BandRegistry([])
        assert reg.band_for_freq(14_200_000) is None
        assert reg.names() == []


class TestAmateurRegistry:

    @pytest.fixture
    def reg(self):
        return BandRegistry.amateur()

    def test_has_standard_hf_bands(self, reg):
        for name in ["160m", "80m", "40m", "20m", "17m", "15m", "10m"]:
            assert reg.band(name) is not None, f"Missing band {name}"

    def test_has_vhf_uhf_bands(self, reg):
        assert reg.band("6m") is not None
        assert reg.band("2m") is not None
        assert reg.band("70cm") is not None

    def test_40m_range(self, reg):
        b = reg.band("40m")
        assert b.start_hz == 7_000_000
        assert b.end_hz == 7_300_000

    def test_20m_midpoint(self, reg):
        assert reg.band_for_freq(14_225_000).name == "20m"

    def test_out_of_band_returns_none(self, reg):
        assert reg.band_for_freq(11_000_000) is None  # between 40m and 30m

    def test_vhf_2m(self, reg):
        assert reg.band_for_freq(146_520_000).name == "2m"
