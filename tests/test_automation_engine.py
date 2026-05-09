"""
Tests for the HA-style automation engine:
  automation/automation.py, automation/engine.py, automation/config.py
"""
import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from automation.automation import Automation, AutomationMode, AutomationTier
from automation.bands import BandRegistry
from automation.condition import Always, Never, SensorAbove, PTTActive
from automation.action import NoOp, Log, SetRadioPower, SetRelay
from automation.context import AutomationContext
from automation.engine import AutomationEngine
from automation.trigger import (
    SensorAboveTrigger, BandEnteredTrigger, ManualTrigger,
    TriggerData,
)
from automation.config import load_engine, load_automations, load_band_registry
from radio.radio_state import RadioState
from sensors.sensor_registry import SensorRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(sensors: dict | None = None, freq: float = 14_200_000, ptt: bool = False) -> AutomationContext:
    state = RadioState(name="test", frequency_hz=freq, ptt=ptt, connected=True)
    registry = SensorRegistry()
    if sensors:
        for k, v in sensors.items():
            registry.publish(k, v)
    return AutomationContext(
        radio_state=state,
        registry=registry,
        band_registry=BandRegistry.amateur(),
    )


def _automation(
    name="test",
    trigger=None,
    action=None,
    conditions=None,
    tier=AutomationTier.ADVISORY,
    mode=AutomationMode.SINGLE,
    priority=0,
    enabled=True,
) -> Automation:
    return Automation(
        name=name,
        tier=tier,
        triggers=[trigger or ManualTrigger()],
        conditions=conditions or [],
        action=action or NoOp(),
        mode=mode,
        priority=priority,
        enabled=enabled,
    )


# ---------------------------------------------------------------------------
# AutomationTier
# ---------------------------------------------------------------------------

class TestAutomationTier:

    def test_protection_runs_before_configuration(self):
        assert AutomationTier.PROTECTION.order < AutomationTier.CONFIGURATION.order

    def test_configuration_runs_before_advisory(self):
        assert AutomationTier.CONFIGURATION.order < AutomationTier.ADVISORY.order


# ---------------------------------------------------------------------------
# Engine management
# ---------------------------------------------------------------------------

class TestEngineManagement:

    def test_add_automation(self):
        engine = AutomationEngine()
        engine.add_automation(_automation("a"))
        assert len(engine.automations()) == 1

    def test_add_duplicate_raises(self):
        engine = AutomationEngine()
        engine.add_automation(_automation("a"))
        with pytest.raises(ValueError, match="already exists"):
            engine.add_automation(_automation("a"))

    def test_remove_automation(self):
        engine = AutomationEngine()
        engine.add_automation(_automation("a"))
        engine.remove_automation("a")
        assert len(engine.automations()) == 0

    def test_remove_missing_raises(self):
        engine = AutomationEngine()
        with pytest.raises(KeyError):
            engine.remove_automation("nope")

    def test_get_automation_found(self):
        engine = AutomationEngine()
        a = _automation("a")
        engine.add_automation(a)
        assert engine.get_automation("a") is a

    def test_get_automation_not_found(self):
        engine = AutomationEngine()
        assert engine.get_automation("nope") is None

    def test_filter_by_tier(self):
        engine = AutomationEngine()
        engine.add_automation(_automation("p", tier=AutomationTier.PROTECTION))
        engine.add_automation(_automation("c", tier=AutomationTier.CONFIGURATION))
        assert len(engine.automations(AutomationTier.PROTECTION)) == 1

    def test_execution_order_tier_then_priority(self):
        engine = AutomationEngine()
        engine.add_automation(_automation("adv", tier=AutomationTier.ADVISORY, priority=100))
        engine.add_automation(_automation("prot", tier=AutomationTier.PROTECTION, priority=0))
        names = [a.name for a in engine.automations()]
        assert names.index("prot") < names.index("adv")

    def test_higher_priority_first_within_tier(self):
        engine = AutomationEngine()
        engine.add_automation(_automation("low", tier=AutomationTier.ADVISORY, priority=10))
        engine.add_automation(_automation("high", tier=AutomationTier.ADVISORY, priority=50))
        names = [a.name for a in engine.automations()]
        assert names.index("high") < names.index("low")


# ---------------------------------------------------------------------------
# process() - trigger-driven execution
# ---------------------------------------------------------------------------

class TestEngineProcess:

    async def test_trigger_fires_automation(self):
        called = []
        action = MagicMock(); action.execute = AsyncMock(side_effect=lambda ctx: called.append(1))

        engine = AutomationEngine()
        t = SensorAboveTrigger("swr", 3.0)
        engine.add_automation(_automation("a", trigger=t, action=action))

        ctx = _ctx(sensors={"swr": 2.0})
        await engine.process(ctx)   # baseline
        assert called == []

        ctx2 = _ctx(sensors={"swr": 4.0})
        fired = await engine.process(ctx2)
        assert "a" in fired
        assert called == [1]

    async def test_trigger_does_not_refire_without_transition(self):
        called = []
        action = MagicMock(); action.execute = AsyncMock(side_effect=lambda ctx: called.append(1))

        engine = AutomationEngine()
        t = SensorAboveTrigger("swr", 3.0)
        engine.add_automation(_automation("a", trigger=t, action=action))

        ctx_low = _ctx(sensors={"swr": 2.0})
        ctx_high = _ctx(sensors={"swr": 4.0})

        await engine.process(ctx_low)
        await engine.process(ctx_high)   # fires
        await engine.process(ctx_high)   # stays high - should NOT fire again
        assert len(called) == 1

    async def test_conditions_block_action(self):
        called = []
        action = MagicMock(); action.execute = AsyncMock(side_effect=lambda ctx: called.append(1))

        engine = AutomationEngine()
        t = SensorAboveTrigger("swr", 3.0)
        engine.add_automation(_automation(
            "a", trigger=t, action=action,
            conditions=[Never()],   # always blocked
        ))

        ctx_low = _ctx(sensors={"swr": 2.0})
        ctx_high = _ctx(sensors={"swr": 4.0})
        await engine.process(ctx_low)
        fired = await engine.process(ctx_high)

        assert "a" not in fired
        assert called == []

    async def test_conditions_pass_allows_action(self):
        called = []
        action = MagicMock(); action.execute = AsyncMock(side_effect=lambda ctx: called.append(1))

        engine = AutomationEngine()
        t = SensorAboveTrigger("swr", 3.0)
        engine.add_automation(_automation(
            "a", trigger=t, action=action,
            conditions=[Always()],
        ))

        await engine.process(_ctx(sensors={"swr": 2.0}))
        await engine.process(_ctx(sensors={"swr": 4.0}))
        assert called == [1]

    async def test_disabled_automation_not_fired(self):
        called = []
        action = MagicMock(); action.execute = AsyncMock(side_effect=lambda ctx: called.append(1))

        engine = AutomationEngine()
        t = SensorAboveTrigger("swr", 3.0)
        engine.add_automation(_automation("a", trigger=t, action=action, enabled=False))

        await engine.process(_ctx(sensors={"swr": 2.0}))
        fired = await engine.process(_ctx(sensors={"swr": 4.0}))
        assert "a" not in fired
        assert called == []

    async def test_multiple_triggers_either_fires(self):
        called = []
        action = MagicMock(); action.execute = AsyncMock(side_effect=lambda ctx: called.append(1))

        engine = AutomationEngine()
        auto = Automation(
            name="a",
            tier=AutomationTier.ADVISORY,
            triggers=[
                SensorAboveTrigger("swr", 3.0),
                BandEnteredTrigger("40m"),
            ],
            action=action,
        )
        engine.add_automation(auto)

        ctx_baseline = _ctx(sensors={"swr": 2.0}, freq=14_200_000)
        await engine.process(ctx_baseline)

        # Trigger via band change (not SWR)
        ctx_40m = _ctx(sensors={"swr": 2.0}, freq=7_100_000)
        fired = await engine.process(ctx_40m)
        assert "a" in fired

    async def test_action_exception_does_not_crash_engine(self):
        async def bad(_ctx):
            raise RuntimeError("boom")

        bad_action = MagicMock(); bad_action.execute = AsyncMock(side_effect=RuntimeError("boom"))
        good_called = []
        good_action = MagicMock(); good_action.execute = AsyncMock(
            side_effect=lambda ctx: good_called.append(1)
        )

        engine = AutomationEngine()
        t1 = SensorAboveTrigger("swr", 3.0)
        t2 = SensorAboveTrigger("swr", 3.0)
        engine.add_automation(_automation("bad", trigger=t1, action=bad_action, priority=10))
        engine.add_automation(_automation("good", trigger=t2, action=good_action, priority=5))

        await engine.process(_ctx(sensors={"swr": 2.0}))
        await engine.process(_ctx(sensors={"swr": 4.0}))
        assert good_called == [1]


# ---------------------------------------------------------------------------
# engine.trigger() - manual testing
# ---------------------------------------------------------------------------

class TestManualTrigger:

    async def test_manual_trigger_fires_action(self):
        called = []
        action = MagicMock(); action.execute = AsyncMock(side_effect=lambda ctx: called.append(1))
        engine = AutomationEngine()
        engine.add_automation(_automation("a", action=action))

        ran = await engine.trigger("a", _ctx())
        assert ran is True
        assert called == [1]

    async def test_manual_trigger_evaluates_conditions(self):
        called = []
        action = MagicMock(); action.execute = AsyncMock(side_effect=lambda ctx: called.append(1))
        engine = AutomationEngine()
        engine.add_automation(_automation("a", action=action, conditions=[Never()]))

        ran = await engine.trigger("a", _ctx())
        assert ran is False
        assert called == []

    async def test_manual_trigger_bypass_conditions(self):
        called = []
        action = MagicMock(); action.execute = AsyncMock(side_effect=lambda ctx: called.append(1))
        engine = AutomationEngine()
        engine.add_automation(_automation("a", action=action, conditions=[Never()]))

        ran = await engine.trigger("a", _ctx(), bypass_conditions=True)
        assert ran is True
        assert called == [1]

    async def test_manual_trigger_condition_with_real_state(self):
        """Conditions check live context - ptt_active blocks when PTT is off."""
        called = []
        action = MagicMock(); action.execute = AsyncMock(side_effect=lambda ctx: called.append(1))
        engine = AutomationEngine()
        engine.add_automation(_automation("a", action=action, conditions=[PTTActive()]))

        ran = await engine.trigger("a", _ctx(ptt=False))
        assert ran is False
        ran2 = await engine.trigger("a", _ctx(ptt=True))
        assert ran2 is True

    async def test_manual_trigger_missing_automation_raises(self):
        engine = AutomationEngine()
        with pytest.raises(KeyError):
            await engine.trigger("nope", _ctx())

    async def test_manual_trigger_disabled_automation_returns_false(self):
        engine = AutomationEngine()
        engine.add_automation(_automation("a", enabled=False))
        ran = await engine.trigger("a", _ctx())
        assert ran is False

    async def test_manual_trigger_does_not_affect_real_trigger_state(self):
        """Manually triggering should not reset trigger baseline state."""
        called = []
        action = MagicMock(); action.execute = AsyncMock(side_effect=lambda ctx: called.append(1))
        engine = AutomationEngine()
        t = SensorAboveTrigger("swr", 3.0)
        engine.add_automation(_automation("a", trigger=t, action=action))

        # Establish baseline
        await engine.process(_ctx(sensors={"swr": 2.0}))

        # Manual trigger fires independently
        await engine.trigger("a", _ctx(sensors={"swr": 4.0}))
        assert len(called) == 1

        # Real trigger should still fire when SWR crosses
        await engine.process(_ctx(sensors={"swr": 4.0}))
        assert len(called) == 2


# ---------------------------------------------------------------------------
# Execution modes
# ---------------------------------------------------------------------------

class TestExecutionModes:

    async def test_single_mode_skips_while_running(self):
        """SINGLE: second trigger while first is awaiting should be skipped.

        The engine adds the name to _executing synchronously before awaiting
        the action, so any concurrent call that checks before the first yield
        sees it and returns False.
        """
        run_count = [0]
        barrier = asyncio.Event()

        async def slow_action(ctx):
            run_count[0] += 1
            await barrier.wait()

        action = MagicMock(); action.execute = AsyncMock(side_effect=slow_action)
        engine = AutomationEngine()
        engine.add_automation(_automation("a", action=action, mode=AutomationMode.SINGLE))

        # Start first execution via a task so it runs concurrently with us.
        task1 = asyncio.create_task(engine.trigger("a", _ctx()))
        # One yield lets task1 run: it adds "a" to _executing, then suspends
        # on slow_action's barrier.wait().
        await asyncio.sleep(0)

        assert run_count[0] == 1  # first execution started

        # Second trigger - "a" is in _executing, mode=SINGLE -> skip.
        ran2 = await engine.trigger("a", _ctx())
        assert ran2 is False

        barrier.set()
        await task1

    async def test_parallel_mode_allows_concurrent_runs(self):
        """PARALLEL: two concurrent callers both run their actions."""
        run_count = [0]

        async def counting_action(ctx):
            run_count[0] += 1

        action = MagicMock(); action.execute = AsyncMock(side_effect=counting_action)
        engine = AutomationEngine()
        engine.add_automation(_automation("a", action=action, mode=AutomationMode.PARALLEL))

        # gather runs both concurrently; neither is blocked by _executing
        await asyncio.gather(
            engine.trigger("a", _ctx()),
            engine.trigger("a", _ctx()),
        )
        assert run_count[0] == 2


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

SAMPLE_CONFIG = """\
automations:
  - name: "test_auto"
    tier: advisory
    priority: 5
    description: "A test automation"
    trigger:
      - type: manual
    action:
      type: noop
"""


class TestConfigLoading:

    def test_load_automations_from_dict(self):
        import yaml
        cfg = yaml.safe_load(SAMPLE_CONFIG)
        autos = load_automations(cfg)
        assert len(autos) == 1
        assert autos[0].name == "test_auto"
        assert autos[0].tier == AutomationTier.ADVISORY
        assert autos[0].priority == 5

    def test_load_band_registry_defaults_to_amateur(self):
        reg = load_band_registry({})
        assert reg.band("20m") is not None

    def test_load_band_registry_custom(self):
        cfg = {"bands": [{"name": "custom", "start_hz": 1000, "end_hz": 2000}]}
        reg = load_band_registry(cfg)
        assert reg.band("custom") is not None
        assert reg.band("20m") is None

    def test_unknown_tier_raises(self):
        import yaml
        cfg = yaml.safe_load("""\
automations:
  - name: r
    tier: unknown_tier
    trigger:
      - type: manual
    action: {type: noop}
""")
        with pytest.raises(ValueError, match="Unknown tier"):
            load_automations(cfg)

    def test_unknown_mode_raises(self):
        import yaml
        cfg = yaml.safe_load("""\
automations:
  - name: r
    tier: advisory
    mode: warp_speed
    trigger:
      - type: manual
    action: {type: noop}
""")
        with pytest.raises(ValueError, match="Unknown mode"):
            load_automations(cfg)

    def test_condition_list_parsed(self):
        import yaml
        cfg = yaml.safe_load("""\
automations:
  - name: r
    tier: advisory
    trigger:
      - type: manual
    condition:
      - type: always
      - type: always
    action: {type: noop}
""")
        autos = load_automations(cfg)
        assert len(autos[0].conditions) == 2

    def test_single_trigger_dict_accepted(self):
        import yaml
        cfg = yaml.safe_load("""\
automations:
  - name: r
    tier: advisory
    trigger:
      type: manual
    action: {type: noop}
""")
        autos = load_automations(cfg)
        assert len(autos[0].triggers) == 1

    def test_load_engine_from_file(self, tmp_path):
        config_file = tmp_path / "auto.yaml"
        config_file.write_text(SAMPLE_CONFIG)
        engine, band_registry = load_engine(config_file)
        assert len(engine.automations()) == 1
        assert band_registry.band("20m") is not None

    async def test_loaded_automation_fires_via_manual_trigger(self, tmp_path):
        config_file = tmp_path / "auto.yaml"
        config_file.write_text(SAMPLE_CONFIG)
        engine, band_registry = load_engine(config_file)
        ctx = AutomationContext(RadioState(name="test"), SensorRegistry(), band_registry)
        ran = await engine.trigger("test_auto", ctx)
        assert ran is True

    def test_load_example_config_yaml(self):
        config_path = Path(__file__).parents[1] / "config" / "automation_config.yaml"
        engine, band_registry = load_engine(config_path)
        assert len(engine.automations()) > 0
