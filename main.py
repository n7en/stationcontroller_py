"""
Station Controller — application entry point.

Loads config, wires all hardware modules, opens the database,
and starts the FastAPI/Uvicorn server on port 8080.

Usage:
    python main.py

Config files (edit before first run):
    config/comms_config.yaml      — DCN buses, transports, and device instances
    config/radio_config.yaml      — radio backend (rigctld or hamlib)
    config/automation_config.yaml — automation rules
    config/telemetry_config.yaml  — SQLite path and recording settings
    config/labels.yaml            — friendly sensor names (optional)
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import uvicorn
import yaml

# ---------------------------------------------------------------------------
# Paths — resolve relative to this file so the app can be launched from any CWD
# ---------------------------------------------------------------------------

BASE = Path(__file__).parent
CFG  = BASE / "config"
DATA = BASE / "data"

COMMS_CFG      = CFG / "comms_config.yaml"
RADIO_CFG      = CFG / "radio_config.yaml"
AUTOMATION_CFG = CFG / "automation_config.yaml"
TELEMETRY_CFG  = CFG / "telemetry_config.yaml"
LABELS_CFG     = CFG / "labels.yaml"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("main")


# ---------------------------------------------------------------------------
# Database migrations (sync — runs before the async loop)
# ---------------------------------------------------------------------------

def _run_migrations(db_url: str) -> None:
    from alembic.config import Config as AlembicConfig
    from alembic import command as alembic_cmd

    DATA.mkdir(parents=True, exist_ok=True)

    # Alembic needs the sync SQLite URL (strip the aiosqlite driver prefix)
    sync_url = db_url.replace("sqlite+aiosqlite", "sqlite")

    cfg = AlembicConfig(str(BASE / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE / "alembic"))
    cfg.set_main_option("sqlalchemy.url", sync_url)
    log.info("Running database migrations…")
    alembic_cmd.upgrade(cfg, "head")


def _read_db_url() -> str:
    """Pull the DB URL from telemetry config, fall back to the default."""
    default = "sqlite+aiosqlite:///data/station.db"
    if not TELEMETRY_CFG.exists():
        return default
    with open(TELEMETRY_CFG) as fh:
        raw = yaml.safe_load(fh) or {}
    return raw.get("telemetry", {}).get("database", {}).get("url", default)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:

    # ── 1. Migrations ────────────────────────────────────────────────────
    db_url = _read_db_url()
    _run_migrations(db_url)

    # ── 2. Sensor & label registries ────────────────────────────────────
    from sensors.sensor_registry import SensorRegistry
    from sensors.label_registry  import LabelRegistry

    sensor_registry = SensorRegistry()
    label_registry  = LabelRegistry()

    if LABELS_CFG.exists():
        label_registry = LabelRegistry.from_yaml(LABELS_CFG)
        log.info("Loaded %d label(s)", len(label_registry.all()))

    sensor_registry.attach_labels(label_registry)

    # ── 3. DCN buses ─────────────────────────────────────────────────────
    from comms.dcn_network import DCNNetwork
    from devices.loader    import load_devices

    networks: dict[str, DCNNetwork] = {}
    devices:  dict[str, object]     = {}
    addr_bus: dict[str, str]        = {}

    if COMMS_CFG.exists():
        networks = DCNNetwork.buses_from_config(COMMS_CFG)
        for bus_name, net in networks.items():
            log.info("DCN bus '%s': %s", bus_name, net)

        devices, addr_bus = load_devices(COMMS_CFG, sensor_registry, networks)
        log.info(
            "Loaded %d device(s) across %d bus(es): %s",
            len(devices), len(networks), list(devices.keys()),
        )
    else:
        log.warning("comms_config.yaml not found — running without DCN hardware")

    # ── 4. Radio ─────────────────────────────────────────────────────────
    from radio.radio_manager import RadioManager
    from radio.radio_state   import RadioState

    radio_manager   = None
    radio_interface = None
    radio_state     = RadioState(name="primary")

    if RADIO_CFG.exists():
        try:
            radio_manager   = RadioManager.from_config(str(RADIO_CFG))
            primary         = radio_manager.names()[0] if radio_manager.names() else None
            if primary:
                radio_interface = radio_manager[primary]
                radio_state     = radio_interface.state
                log.info("Primary radio: %s", primary)
        except Exception:
            log.exception("Failed to load radio config — radio control disabled")
    else:
        log.warning("radio_config.yaml not found — radio control disabled")

    # ── 5. Automation engine ─────────────────────────────────────────────
    from automation.config  import load_engine as load_automation
    from automation.context import AutomationContext

    engine        = None
    band_registry = None

    if AUTOMATION_CFG.exists():
        try:
            engine, band_registry = load_automation(AUTOMATION_CFG)
            log.info("Automation engine: %d rule(s)", len(engine.automations()))
        except Exception:
            log.exception("Failed to load automation config — automations disabled")

    # ── 6. Telemetry ─────────────────────────────────────────────────────
    from telemetry.config import load_telemetry

    store = recorder = dcn_logger = None

    if TELEMETRY_CFG.exists():
        try:
            store, recorder, dcn_logger = load_telemetry(config_path=TELEMETRY_CFG)
            await store.open()
            recorder.attach(sensor_registry)
            if dcn_logger and networks:
                dcn_logger.attach_all(networks)
            log.info("Telemetry store open")
        except Exception:
            log.exception("Failed to open telemetry store — telemetry disabled")

    # ── 7. AppState + FastAPI app ─────────────────────────────────────────
    from api.app  import create_app
    from api.deps import AppState

    state                  = AppState()
    state.sensor_registry  = sensor_registry
    state.label_registry   = label_registry
    state.networks         = networks
    state.devices          = devices
    state.device_bus       = addr_bus
    state.radio_state      = radio_state
    state.radio_interface  = radio_interface
    state.engine           = engine
    state.band_registry    = band_registry
    state.telemetry        = store

    app    = create_app(state)
    ws_hub = state.ws_hub  # populated by create_app()

    # ── 8. Cross-wiring ───────────────────────────────────────────────────

    # Control bus reference used by automation (single-bus for now).
    control_network = state.control_network

    # Radio state changes → WS broadcast + automation engine
    if radio_interface is not None:
        async def _on_radio(rs: RadioState, changed: dict) -> None:
            await ws_hub.broadcast_radio(rs)
            if engine and band_registry:
                ctx = AutomationContext(
                    radio_state=rs,
                    registry=sensor_registry,
                    band_registry=band_registry,
                    radio_interface=radio_interface,
                    control_network=control_network,
                )
                await engine.process(ctx)

        radio_interface.on_state_change(_on_radio)

    # Sensor changes → automation engine
    if engine and band_registry:
        def _on_sensor(m) -> None:
            try:
                loop = asyncio.get_running_loop()
                ctx = AutomationContext(
                    radio_state=radio_state,
                    registry=sensor_registry,
                    band_registry=band_registry,
                    radio_interface=radio_interface,
                    control_network=control_network,
                )
                loop.create_task(
                    engine.process(ctx),
                    name=f"automation.sensor.{m.name}",
                )
            except RuntimeError:
                pass

        sensor_registry.on_any(_on_sensor)

    # ── 9. Connect hardware ──────────────────────────────────────────────
    for bus_name, net in networks.items():
        try:
            await net.connect_all()
        except Exception:
            log.exception("Failed to connect bus '%s'", bus_name)

    if radio_interface:
        try:
            await radio_interface.connect()
            await radio_interface.start()
        except Exception:
            log.warning("Radio connect failed — will retry in background")

    # ── 10. Serve ─────────────────────────────────────────────────────────
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8080,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)

    log.info("=" * 55)
    log.info("  Station Controller  →  http://localhost:8080")
    log.info("=" * 55)

    try:
        await server.serve()
    finally:
        log.info("Shutting down…")
        if radio_interface:
            await radio_interface.stop()
            await radio_interface.disconnect()
        for bus_name, net in networks.items():
            try:
                await net.disconnect_all()
            except Exception:
                log.exception("Error disconnecting bus '%s'", bus_name)
        if store:
            await store.close()
        log.info("Stopped.")


if __name__ == "__main__":
    asyncio.run(main())
