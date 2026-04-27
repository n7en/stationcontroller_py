"""
Fixtures and helpers shared across all hardware integration tests.

Every test in this package requires physical hardware.  The fixtures here
load config/hardware_test_config.yaml and skip individual tests whose
required network or device is marked as not present/enabled.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import pytest
import yaml

from comms.dcn_network import DCNNetwork
from comms.dcn_packet import DCNPacket
from comms.transport.rs485 import RS485Transport
from devices.gpio_module import parse_gpio_update  # re-exported for test compat
from devices.watt_meter import parse_wm1_update    # re-exported for test compat

CONFIG_PATH = Path(__file__).parents[2] / "config" / "hardware_test_config.yaml"


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def hw_config() -> dict:
    """Load hardware_test_config.yaml once per session.  Skip if missing."""
    if not CONFIG_PATH.exists():
        pytest.skip(
            f"Hardware config not found: {CONFIG_PATH}\n"
            "Copy config/hardware_test_config.yaml and fill in your setup."
        )
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


# ---------------------------------------------------------------------------
# Network fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def control_net(hw_config):
    """
    Connected RS-485 control network (9600 baud).
    Skips if control_network.enabled is not true in hardware_test_config.yaml.
    """
    cfg = hw_config.get("control_network", {})
    if not cfg.get("enabled", False):
        pytest.skip("control_network not enabled in hardware_test_config.yaml")

    transport = RS485Transport("control", {
        "port": cfg["port"],
        "baud_rate": cfg.get("baud_rate", 9600),
    })
    net = DCNNetwork()
    net.add_transport(transport)

    received: list[DCNPacket] = []
    net.on_packet(lambda p, n: received.append(p))
    net._hw_received = received          # attach for test access
    net._hw_timeout = cfg.get("response_timeout", 2.0)

    async with net:
        # Brief settling time for the serial port to stabilise
        await asyncio.sleep(0.1)
        yield net


@pytest.fixture
async def power_net(hw_config):
    """
    Connected RS-485 power meter network (115200 baud).
    Skips if power_network.enabled is not true.
    """
    cfg = hw_config.get("power_network", {})
    if not cfg.get("enabled", False):
        pytest.skip("power_network not enabled in hardware_test_config.yaml")

    transport = RS485Transport("power", {
        "port": cfg["port"],
        "baud_rate": cfg.get("baud_rate", 115200),
    })
    net = DCNNetwork()
    net.add_transport(transport)

    received: list[DCNPacket] = []
    net.on_packet(lambda p, n: received.append(p))
    net._hw_received = received
    net._hw_timeout = cfg.get("response_timeout", 1.0)

    async with net:
        await asyncio.sleep(0.1)
        yield net


# ---------------------------------------------------------------------------
# Device-presence helpers
# ---------------------------------------------------------------------------

def _device(hw_config: dict, key: str) -> dict:
    return hw_config.get("devices", {}).get(key, {})


def require_device(hw_config: dict, key: str) -> dict:
    """Return device config or skip the test if the device is not present."""
    dev = _device(hw_config, key)
    if not dev.get("present", False):
        pytest.skip(f"Device '{key}' not marked present in hardware_test_config.yaml")
    return dev


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

async def query(
    net: DCNNetwork,
    to_addr: str,
    payload: str,
    timeout: Optional[float] = None,
) -> Optional[DCNPacket]:
    """
    Send a command and return the first response packet from to_addr.
    Returns None on timeout.
    """
    t = timeout or net._hw_timeout
    responses: list[DCNPacket] = []
    arrived = asyncio.Event()

    async def capture(pkt: DCNPacket, name: str) -> None:
        if pkt.from_addr == to_addr and not arrived.is_set():
            responses.append(pkt)
            arrived.set()

    net.on_packet(capture)
    await net.send(to_addr, payload)

    try:
        await asyncio.wait_for(arrived.wait(), timeout=t)
    except asyncio.TimeoutError:
        pass

    return responses[0] if responses else None


async def collect_responses(
    net: DCNNetwork,
    to_addr: str,
    payload: str,
    count: int = 1,
    timeout: Optional[float] = None,
) -> list[DCNPacket]:
    """
    Send a command and collect up to `count` response packets from to_addr.
    Useful for burst/streaming tests.
    """
    t = timeout or net._hw_timeout
    responses: list[DCNPacket] = []
    done = asyncio.Event()

    async def capture(pkt: DCNPacket, name: str) -> None:
        if pkt.from_addr == to_addr:
            responses.append(pkt)
            if len(responses) >= count:
                done.set()

    net.on_packet(capture)
    await net.send(to_addr, payload)

    try:
        await asyncio.wait_for(done.wait(), timeout=t)
    except asyncio.TimeoutError:
        pass

    return responses


async def wait_for_any_traffic(net: DCNNetwork, timeout: float = 3.0) -> list[DCNPacket]:
    """
    Wait up to `timeout` seconds and return any packets received.
    Useful to verify the network is live before sending commands.
    """
    start_count = len(net._hw_received)
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if len(net._hw_received) > start_count:
            return net._hw_received[start_count:]
        await asyncio.sleep(0.05)
    return []


# ---------------------------------------------------------------------------
# GPIO / watt meter packet helpers
# (parse_gpio_update and parse_wm1_update are imported from device modules
#  above; the names are re-exported here for backward compatibility)
# ---------------------------------------------------------------------------


def relay_char(relay_states: str, relay_num: int) -> str:
    """Return '1' or '0' for a given relay number (1-indexed)."""
    return relay_states[relay_num - 1]


def set_relay_char(relay_states: str, relay_num: int, value: int) -> str:
    """Return a new relay state string with relay_num set to value (0 or 1)."""
    lst = list(relay_states)
    lst[relay_num - 1] = str(value)
    return "".join(lst)


# ---------------------------------------------------------------------------
# Device module fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def device_registry():
    """A fresh SensorRegistry for each test."""
    from sensors.sensor_registry import SensorRegistry
    return SensorRegistry()


@pytest.fixture
async def watt_meter(hw_config, control_net, device_registry):
    """
    WattMeter module attached to the control network.
    Skips if the watt_meter device is not present in hardware_test_config.yaml.
    """
    from devices.watt_meter import WattMeter
    cfg = require_device(hw_config, "watt_meter")
    meter = WattMeter(
        name="watt_meter",
        address=cfg["address"],
        registry=device_registry,
    )
    meter.attach(control_net)
    return meter


@pytest.fixture
async def watt_meter_hf(hw_config, power_net, device_registry):
    """
    WattMeter module attached to the high-speed power network (115200 baud).
    Skips if the watt_meter device is not present.
    """
    from devices.watt_meter import WattMeter
    wm_cfg = hw_config.get("devices", {}).get("watt_meter", {})
    if not wm_cfg.get("present", False):
        pytest.skip("watt_meter not marked present in hardware_test_config.yaml")
    meter = WattMeter(
        name="watt_meter_hf",
        address=wm_cfg["address"],
        registry=device_registry,
    )
    meter.attach(power_net)
    return meter


@pytest.fixture
async def gpio(hw_config, control_net, device_registry):
    """
    GPIOModule attached to the control network (primary GPIO module).
    Skips if gpio_module is not present.
    """
    from devices.gpio_module import GPIOModule
    cfg = require_device(hw_config, "gpio_module")
    module = GPIOModule(
        name="gpio",
        address=cfg["address"],
        registry=device_registry,
    )
    module.attach(control_net)
    return module


@pytest.fixture
async def gpio2(hw_config, control_net, device_registry):
    """Second GPIO module, if present."""
    from devices.gpio_module import GPIOModule
    cfg = require_device(hw_config, "gpio_module_2")
    module = GPIOModule(
        name="gpio2",
        address=cfg["address"],
        registry=device_registry,
    )
    module.attach(control_net)
    return module


# ---------------------------------------------------------------------------
# Radio fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def radio_hw_config(hw_config: dict) -> dict:
    """
    Return the radio section from hardware_test_config.yaml.
    Skips if the section is absent or enabled is not true.
    """
    cfg = hw_config.get("radio", {})
    if not cfg.get("enabled", False):
        pytest.skip("radio not enabled in hardware_test_config.yaml")
    return cfg


@pytest.fixture
async def radio_interface(radio_hw_config: dict):
    """
    Connected RadioInterface backed by rigctld.
    Skips if the radio section is not enabled.
    """
    from radio.backends.rigctld import RigctldBackend
    from radio.radio_interface import RadioInterface

    host = radio_hw_config.get("rigctld_host", "localhost")
    port = radio_hw_config.get("rigctld_port", 4532)
    timeout = radio_hw_config.get("response_timeout", 5.0)

    backend = RigctldBackend(host=host, port=port, timeout_s=timeout)
    iface = RadioInterface(
        name="hw_radio",
        backend=backend,
        poll_interval_s=radio_hw_config.get("poll_interval_s", 0.5),
    )
    await iface.connect()
    yield iface
    await iface.disconnect()
