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
import logging.handlers
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
LOGGING_CFG    = CFG / "logging_config.yaml"

TLS_CERT = CFG / "certs" / "cert.pem"
TLS_KEY  = CFG / "certs" / "key.pem"

# ---------------------------------------------------------------------------
# First-run config bootstrap
# ---------------------------------------------------------------------------

def _ensure_default_configs() -> None:
    """
    Copy <name>.yaml.example → <name>.yaml for any machine-specific config
    that is missing.  Runs before logging is configured so it uses print().
    """
    import shutil
    for cfg in (COMMS_CFG, RADIO_CFG, LOGGING_CFG):
        if not cfg.exists():
            example = Path(str(cfg) + ".example")
            if example.exists():
                shutil.copy2(example, cfg)
                print(
                    f"[setup] Created {cfg.name} from {example.name}. "
                    f"Edit it for your hardware before restarting.",
                    file=sys.stderr,
                )


_ensure_default_configs()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _configure_logging(cfg_path: Path) -> None:
    """
    Configure the root logger from logging_config.yaml.

    Two handlers are always set up:
      • StreamHandler (stdout) — level controlled by console_level
      • RotatingFileHandler   — level controlled by file.level
                                CRITICAL is always captured (it exceeds any threshold)

    The root logger is set to DEBUG so each handler can filter independently.
    Noisy third-party libraries are capped at WARNING even in DEBUG mode.
    """
    console_level = logging.INFO
    file_enabled  = True
    file_path     = BASE / "logs" / "station.log"
    file_level    = logging.WARNING
    max_bytes     = 10 * 1024 * 1024   # 10 MB
    backup_count  = 5

    if cfg_path.exists():
        try:
            with open(cfg_path, encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
            cfg = raw.get("logging", {})

            console_level = getattr(
                logging,
                str(cfg.get("console_level", "INFO")).upper(),
                logging.INFO,
            )

            fc = cfg.get("file", {})
            file_enabled = fc.get("enabled", True)
            file_level   = getattr(
                logging,
                str(fc.get("level", "WARNING")).upper(),
                logging.WARNING,
            )
            raw_path = fc.get("path", "logs/station.log")
            fp = Path(raw_path)
            file_path = fp if fp.is_absolute() else BASE / fp
            max_bytes    = int(fc.get("max_bytes", max_bytes))
            backup_count = int(fc.get("backup_count", backup_count))
        except Exception as exc:
            print(f"WARNING: Could not read {cfg_path} ({exc}) — using logging defaults",
                  file=sys.stderr)

    # Root logger sees everything; individual handlers filter by level.
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    _console_fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    _file_fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_h = logging.StreamHandler(sys.stdout)
    console_h.setLevel(console_level)
    console_h.setFormatter(_console_fmt)
    root.addHandler(console_h)

    if file_enabled:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_h = logging.handlers.RotatingFileHandler(
            file_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_h.setLevel(file_level)
        file_h.setFormatter(_file_fmt)
        root.addHandler(file_h)

    # Prevent very noisy libraries from flooding DEBUG output.
    for _noisy in ("uvicorn.access", "asyncio", "httpx", "hpack", "h2"):
        logging.getLogger(_noisy).setLevel(logging.WARNING)


_configure_logging(LOGGING_CFG)
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
    with open(TELEMETRY_CFG, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return raw.get("telemetry", {}).get("database", {}).get("url", default)


# ---------------------------------------------------------------------------
# TLS — self-signed certificate
# ---------------------------------------------------------------------------

def _ensure_tls_cert(cert_path: Path, key_path: Path) -> None:
    """Generate a self-signed TLS cert+key if they do not already exist."""
    if cert_path.exists() and key_path.exists():
        return

    import datetime
    import ipaddress
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    cert_path.parent.mkdir(parents=True, exist_ok=True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "StationController"),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
            ]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    log.info("Generated self-signed TLS certificate -> %s", cert_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:

    # ── 0a. Log buffer (captures all startup logs for WS replay) ────────
    import time as _time
    from api.log_buffer import LogBuffer

    log_buffer = LogBuffer(maxlen=500)
    logging.getLogger().addHandler(log_buffer.make_handler())

    # ── 0b. TLS certificate ──────────────────────────────────────────────
    _ensure_tls_cert(TLS_CERT, TLS_KEY)

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
        log.warning("comms_config.yaml not found - running without DCN hardware")

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
        log.warning(
            "radio_config.yaml not found — radio control disabled.  "
            "Copy config/radio_config.yaml.example to config/radio_config.yaml and edit it."
        )

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
    from api.auth import load_auth_config
    from api.deps import AppState

    load_auth_config()

    state                  = AppState()
    state.sensor_registry  = sensor_registry
    state.label_registry   = label_registry
    state.networks         = networks
    state.devices          = devices
    state.device_bus       = addr_bus
    state.radio_state      = radio_state
    state.radio_interface  = radio_interface
    state.radio_manager    = radio_manager
    state.engine           = engine
    state.band_registry    = band_registry
    state.telemetry        = store
    state.log_buffer       = log_buffer

    app    = create_app(state)
    ws_hub = state.ws_hub  # populated by create_app()
    log_buffer.attach_ws_hub(ws_hub)

    # ── 8. Cross-wiring ───────────────────────────────────────────────────

    # Control bus reference used by automation (single-bus for now).
    control_network = state.control_network

    # Radio state changes → WS broadcast + automation engine (primary only)
    if radio_manager is not None:
        for _iface in radio_manager:
            _is_primary = (_iface is radio_interface)

            def _make_radio_handler(_iface=_iface, _is_primary=_is_primary):
                async def _on_radio(rs: RadioState, changed: dict) -> None:
                    await ws_hub.broadcast_radio(_iface.name, rs)
                    if _is_primary and engine and band_registry:
                        ctx = AutomationContext(
                            radio_state=rs,
                            registry=sensor_registry,
                            band_registry=band_registry,
                            radio_interface=_iface,
                            control_network=control_network,
                        )
                        await engine.process(ctx)
                return _on_radio

            _iface.on_state_change(_make_radio_handler())

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

    # DCN packets → live log stream
    def _make_dcn_hooks(buf, bus_name):
        async def _rx(packet, transport):
            buf.append_dcn({
                "type": "dcn_message", "ts": _time.time(), "direction": "rx",
                "bus": bus_name, "from_addr": packet.from_addr,
                "to_addr": packet.to_addr, "payload": packet.payload,
                "raw": packet.raw or str(packet), "broadcast": packet.broadcast,
                "transport": transport,
            })
        async def _tx(packet, transport):
            buf.append_dcn({
                "type": "dcn_message", "ts": _time.time(), "direction": "tx",
                "bus": bus_name, "from_addr": packet.from_addr,
                "to_addr": packet.to_addr, "payload": packet.payload,
                "raw": packet.raw or str(packet), "broadcast": packet.broadcast,
                "transport": transport,
            })
        return _rx, _tx

    for bus_name, net in networks.items():
        _rx, _tx = _make_dcn_hooks(log_buffer, bus_name)
        net.on_packet(_rx)
        net.on_transmit(_tx)

    # ── 9. Connect hardware ──────────────────────────────────────────────
    for bus_name, net in networks.items():
        try:
            await net.connect_all()
        except Exception:
            log.exception("Failed to connect bus '%s'", bus_name)

    if radio_manager is not None:
        for _iface in radio_manager:
            try:
                await _iface.connect()
            except Exception:
                log.warning("Radio '%s' connect failed - poll loop will retry", _iface.name)
            await _iface.start()

    # ── 10. Serve ─────────────────────────────────────────────────────────
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8080,
        log_level="warning",
        access_log=False,
        ssl_certfile=str(TLS_CERT),
        ssl_keyfile=str(TLS_KEY),
    )
    server = uvicorn.Server(config)

    log.info("=" * 55)
    log.info("  Station Controller  →  https://localhost:8080")
    log.info("=" * 55)

    try:
        await server.serve()
    finally:
        log.info("Shutting down…")
        if radio_manager is not None:
            await radio_manager.stop_all()
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
