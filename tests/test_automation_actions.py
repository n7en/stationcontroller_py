"""Tests for radio-control actions in automation/action.py."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from automation.action import (
    SetFrequency, SetMode, TuneRadio,
    action_from_config,
)
from automation.bands import BandRegistry
from automation.context import AutomationContext
from radio.radio_state import RadioState
from sensors.sensor_registry import SensorRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(radio=True) -> AutomationContext:
    iface = MagicMock()
    iface.set_frequency = AsyncMock()
    iface.set_mode = AsyncMock()
    return AutomationContext(
        radio_state=RadioState(name="test"),
        registry=SensorRegistry(),
        band_registry=BandRegistry.amateur(),
        radio_interface=iface if radio else None,
    )


# ---------------------------------------------------------------------------
# SetFrequency
# ---------------------------------------------------------------------------

class TestSetFrequency:

    @pytest.mark.asyncio
    async def test_calls_set_frequency(self):
        ctx = _ctx()
        await SetFrequency(14_225_000).execute(ctx)
        ctx.radio_interface.set_frequency.assert_awaited_once_with(14_225_000)

    @pytest.mark.asyncio
    async def test_raises_without_radio_interface(self):
        ctx = _ctx(radio=False)
        with pytest.raises(RuntimeError, match="radio_interface"):
            await SetFrequency(14_225_000).execute(ctx)


# ---------------------------------------------------------------------------
# SetMode
# ---------------------------------------------------------------------------

class TestSetMode:

    @pytest.mark.asyncio
    async def test_calls_set_mode(self):
        ctx = _ctx()
        await SetMode("USB").execute(ctx)
        ctx.radio_interface.set_mode.assert_awaited_once_with("USB", 0)

    @pytest.mark.asyncio
    async def test_passes_bandwidth(self):
        ctx = _ctx()
        await SetMode("CW", bandwidth_hz=500).execute(ctx)
        ctx.radio_interface.set_mode.assert_awaited_once_with("CW", 500)

    @pytest.mark.asyncio
    async def test_raises_without_radio_interface(self):
        ctx = _ctx(radio=False)
        with pytest.raises(RuntimeError, match="radio_interface"):
            await SetMode("USB").execute(ctx)


# ---------------------------------------------------------------------------
# TuneRadio
# ---------------------------------------------------------------------------

class TestTuneRadio:

    @pytest.mark.asyncio
    async def test_sets_frequency_and_mode(self):
        ctx = _ctx()
        await TuneRadio(14_225_000, mode="USB").execute(ctx)
        ctx.radio_interface.set_frequency.assert_awaited_once_with(14_225_000)
        ctx.radio_interface.set_mode.assert_awaited_once_with("USB", 0)

    @pytest.mark.asyncio
    async def test_frequency_only_skips_set_mode(self):
        ctx = _ctx()
        await TuneRadio(14_225_000).execute(ctx)
        ctx.radio_interface.set_frequency.assert_awaited_once_with(14_225_000)
        ctx.radio_interface.set_mode.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_passes_bandwidth_to_set_mode(self):
        ctx = _ctx()
        await TuneRadio(7_200_000, mode="LSB", bandwidth_hz=2700).execute(ctx)
        ctx.radio_interface.set_mode.assert_awaited_once_with("LSB", 2700)

    @pytest.mark.asyncio
    async def test_raises_without_radio_interface(self):
        ctx = _ctx(radio=False)
        with pytest.raises(RuntimeError, match="radio_interface"):
            await TuneRadio(14_225_000, mode="USB").execute(ctx)


# ---------------------------------------------------------------------------
# action_from_config factory
# ---------------------------------------------------------------------------

class TestActionFromConfig:

    def test_set_frequency(self):
        a = action_from_config({"type": "set_frequency", "frequency_hz": 14_225_000})
        assert isinstance(a, SetFrequency)
        assert a.hz == 14_225_000

    def test_set_mode(self):
        a = action_from_config({"type": "set_mode", "mode": "USB"})
        assert isinstance(a, SetMode)
        assert a.mode == "USB"
        assert a.bandwidth_hz == 0

    def test_set_mode_with_bandwidth(self):
        a = action_from_config({"type": "set_mode", "mode": "CW", "bandwidth_hz": 500})
        assert isinstance(a, SetMode)
        assert a.bandwidth_hz == 500

    def test_tune_radio_with_mode(self):
        a = action_from_config({
            "type": "tune_radio",
            "frequency_hz": 14_225_000,
            "mode": "USB",
        })
        assert isinstance(a, TuneRadio)
        assert a.frequency_hz == 14_225_000
        assert a.mode == "USB"
        assert a.bandwidth_hz == 0

    def test_tune_radio_frequency_only(self):
        a = action_from_config({"type": "tune_radio", "frequency_hz": 7_200_000})
        assert isinstance(a, TuneRadio)
        assert a.mode is None

    def test_tune_radio_with_bandwidth(self):
        a = action_from_config({
            "type": "tune_radio",
            "frequency_hz": 7_074_000,
            "mode": "USB",
            "bandwidth_hz": 3000,
        })
        assert isinstance(a, TuneRadio)
        assert a.bandwidth_hz == 3000
