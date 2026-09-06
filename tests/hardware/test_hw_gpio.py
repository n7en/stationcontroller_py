"""
GPIO Module (#321) hardware tests.

Tests the Sierra Radio Systems GPIO module at its configured DCN address.
Uses the GPIOModule device module - after each STATE query the module's
state is automatically populated from the response packet.

All tests skip automatically if gpio_module.present is false in
config/hardware_test_config.yaml.

CAUTION: Relay toggle tests will briefly energise a physical relay.
         Set  restore_relay_state: true  to return it to its prior state.

Run with:  pytest --hardware -v tests/hardware/test_hw_gpio.py
"""
import asyncio
import pytest

from .conftest import query, parse_gpio_update, relay_char, set_relay_char, require_device

pytestmark = pytest.mark.hardware


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def gpio_cfg(hw_config):
    return require_device(hw_config, "gpio_module")


@pytest.fixture
async def gpio_state(control_net, gpio_cfg, gpio):
    """
    Yield current GPIO state via the module.  Restores relay state on
    teardown if restore_relay_state is true in config.
    """
    addr = gpio_cfg["address"]
    response = await query(control_net, addr, "STATE")
    assert response is not None, (
        f"GPIO module at address {addr} did not respond to STATE command."
    )
    assert response.command == "UPDATE"

    original = parse_gpio_update(response)
    yield gpio, original

    if gpio_cfg.get("restore_relay_state", True) and original["relay_states"]:
        await control_net.send(addr, f"RY,{original['relay_states']}")
        await asyncio.sleep(0.2)


# ---------------------------------------------------------------------------
# Basic communication
# ---------------------------------------------------------------------------

class TestGPIOCommunication:

    async def test_ping_responds(self, control_net, gpio_cfg):
        addr = gpio_cfg["address"]
        response = await query(control_net, addr, "PING")
        assert response is not None, (
            f"GPIO module at address {addr} did not respond to PING."
        )

    async def test_ping_response_has_correct_from_addr(self, control_net, gpio_cfg):
        addr = gpio_cfg["address"]
        response = await query(control_net, addr, "PING")
        assert response is not None
        assert response.from_addr == addr

    async def test_status_responds(self, control_net, gpio_cfg):
        addr = gpio_cfg["address"]
        response = await query(control_net, addr, "STATUS")
        assert response is not None

    async def test_state_returns_update_packet(self, control_net, gpio_cfg):
        addr = gpio_cfg["address"]
        response = await query(control_net, addr, "STATE")
        assert response is not None
        assert response.command == "UPDATE"

    async def test_update_packet_identifies_gpio1(self, control_net, gpio_cfg):
        addr = gpio_cfg["address"]
        response = await query(control_net, addr, "STATE")
        assert response is not None
        data = parse_gpio_update(response)
        assert data["module_type"] == "GPIO1"


# ---------------------------------------------------------------------------
# Module state validation (via GPIOModule)
# ---------------------------------------------------------------------------

class TestGPIOModuleState:

    async def test_module_state_populated_after_query(self, control_net, gpio_cfg, gpio):
        """After a STATE query the GPIOModule state should be populated."""
        await query(control_net, gpio_cfg["address"], "STATE")
        assert gpio.state.relay_states is not None
        assert gpio.state.digital_inputs is not None

    async def test_relay_states_field_is_8_chars(self, control_net, gpio_cfg, gpio):
        await query(control_net, gpio_cfg["address"], "STATE")
        assert len(gpio.state.relay_states) == 8

    async def test_relay_states_only_contains_0_and_1(self, control_net, gpio_cfg, gpio):
        await query(control_net, gpio_cfg["address"], "STATE")
        assert all(c in ("0", "1") for c in gpio.state.relay_states)

    async def test_digital_inputs_field_is_4_chars(self, control_net, gpio_cfg, gpio):
        await query(control_net, gpio_cfg["address"], "STATE")
        assert len(gpio.state.digital_inputs) == 4

    async def test_voltmeter_readings_are_non_negative(self, control_net, gpio_cfg, gpio):
        await query(control_net, gpio_cfg["address"], "STATE")
        for i in range(1, 5):
            v = getattr(gpio.state, f"voltmeter_{i}")
            if v is not None:
                assert v >= 0.0, f"Voltmeter {i} is negative: {v}"

    async def test_voltmeter_readings_in_plausible_range(self, control_net, gpio_cfg, gpio):
        await query(control_net, gpio_cfg["address"], "STATE")
        for i in range(1, 5):
            v = getattr(gpio.state, f"voltmeter_{i}")
            if v is not None and v > 0:
                assert v <= 20.0, f"Voltmeter {i} reading {v:.3f} V exceeds 20 V"

    async def test_temperature_readings_are_plausible(self, control_net, gpio_cfg, gpio):
        await query(control_net, gpio_cfg["address"], "STATE")
        for i, t in [(1, gpio.state.temp_1_f), (2, gpio.state.temp_2_f)]:
            if t is not None and t != 0.0:
                assert 0.0 <= t <= 200.0, (
                    f"Temperature probe {i}: {t:.2f} °F is implausible"
                )

    async def test_registry_populated_with_voltmeters(
        self, control_net, gpio_cfg, gpio, device_registry
    ):
        """Voltmeter readings should appear in the sensor registry."""
        await query(control_net, gpio_cfg["address"], "STATE")
        assert device_registry.get("gpio_voltmeter_1") is not None

    async def test_registry_populated_with_relays(
        self, control_net, gpio_cfg, gpio, device_registry
    ):
        """Individual relay states should appear in the sensor registry."""
        await query(control_net, gpio_cfg["address"], "STATE")
        assert device_registry.get("gpio_relay_1") is not None


# ---------------------------------------------------------------------------
# Relay control
# ---------------------------------------------------------------------------

class TestGPIORelayControl:

    async def test_relay_on_command_accepted(self, control_net, gpio_cfg, gpio_state):
        gpio_module, original = gpio_state
        addr = gpio_cfg["address"]
        relay_num = gpio_cfg.get("test_relay", 1)

        await control_net.send(addr, f"RY{relay_num},1")
        await asyncio.sleep(0.3)
        response = await query(control_net, addr, "STATE")
        assert response is not None

        assert gpio_module.state.relay(relay_num) is True, (
            f"Relay {relay_num} should be ON after RY{relay_num},1 but "
            f"state is: {gpio_module.state.relay_states!r}"
        )

    async def test_relay_off_command_accepted(self, control_net, gpio_cfg, gpio_state):
        gpio_module, original = gpio_state
        addr = gpio_cfg["address"]
        relay_num = gpio_cfg.get("test_relay", 1)

        await control_net.send(addr, f"RY{relay_num},1")
        await asyncio.sleep(0.3)
        await control_net.send(addr, f"RY{relay_num},0")
        await asyncio.sleep(0.3)
        response = await query(control_net, addr, "STATE")
        assert response is not None

        assert gpio_module.state.relay(relay_num) is False, (
            f"Relay {relay_num} should be OFF after RY{relay_num},0"
        )

    async def test_relay_toggle_on_off_cycle(self, control_net, gpio_cfg, gpio_state):
        gpio_module, original = gpio_state
        addr = gpio_cfg["address"]
        relay_num = gpio_cfg.get("test_relay", 1)

        for value, expected in [(1, True), (0, False)]:
            await control_net.send(addr, f"RY{relay_num},{value}")
            await asyncio.sleep(0.3)
            await query(control_net, addr, "STATE")
            assert gpio_module.state.relay(relay_num) is expected, (
                f"Relay {relay_num} expected {'ON' if expected else 'OFF'}, "
                f"state={gpio_module.state.relay_states!r}"
            )

    async def test_relay_bitmask_command(self, control_net, gpio_cfg, gpio_state):
        gpio_module, original = gpio_state
        addr = gpio_cfg["address"]
        relay_num = gpio_cfg.get("test_relay", 1)

        target_mask = set_relay_char("0" * 8, relay_num, 1)
        await control_net.send(addr, f"RY,{target_mask}")
        await asyncio.sleep(0.3)
        await query(control_net, addr, "STATE")

        assert gpio_module.state.relay_states == target_mask, (
            f"Expected {target_mask!r}, got {gpio_module.state.relay_states!r}"
        )

    async def test_all_relays_off_command(self, control_net, gpio_cfg, gpio_state):
        gpio_module, original = gpio_state
        addr = gpio_cfg["address"]
        relay_num = gpio_cfg.get("test_relay", 1)

        await control_net.send(addr, f"RY{relay_num},1")
        await asyncio.sleep(0.3)
        await control_net.send(addr, "RY")
        await asyncio.sleep(0.3)
        await query(control_net, addr, "STATE")

        assert gpio_module.state.relay_states == "00000000", (
            f"Expected all relays OFF, got {gpio_module.state.relay_states!r}"
        )

    async def test_state_consistent_across_queries(self, control_net, gpio_cfg, gpio):
        addr = gpio_cfg["address"]
        await query(control_net, addr, "STATE")
        relays1 = gpio.state.relay_states
        inputs1 = gpio.state.digital_inputs

        await asyncio.sleep(0.1)
        await query(control_net, addr, "STATE")

        assert gpio.state.relay_states == relays1, (
            f"Relay state changed: {relays1!r} -> {gpio.state.relay_states!r}"
        )
        assert gpio.state.digital_inputs == inputs1, (
            f"Digital input state changed: {inputs1!r} -> {gpio.state.digital_inputs!r}"
        )


# ---------------------------------------------------------------------------
# Second GPIO module (if present)
# ---------------------------------------------------------------------------

class TestGPIOModule2:

    async def test_gpio2_ping(self, control_net, hw_config):
        dev = require_device(hw_config, "gpio_module_2")
        addr = dev["address"]
        response = await query(control_net, addr, "PING")
        assert response is not None

    async def test_gpio2_state_via_module(self, control_net, hw_config, gpio2):
        dev = require_device(hw_config, "gpio_module_2")
        await query(control_net, dev["address"], "STATE")
        assert gpio2.state.relay_states is not None
        assert gpio2.state.relay_states is not None
        assert all(c in ("0", "1") for c in gpio2.state.relay_states)
