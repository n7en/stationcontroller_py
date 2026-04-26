# StationController

A Python-based amateur radio station controller with a live web UI. It manages antenna switching, relay control, radio integration, RF power monitoring, and automation rules — all through a browser dashboard served from the same machine running the hardware.

---

## Features

- **Live dashboard** — configurable cards: power meters, SWR bar, relay toggles, sensor readouts, radio status
- **Radio integration** — frequency, mode, and PTT monitoring via rigctld or direct hamlib
- **DCN hardware** — talks to GPIO modules, coax switches, VHF relays, antenna relay banks, and RF watt meters over RS-485
- **Automation engine** — YAML-defined trigger → condition → action rules (band-change antenna switching, SWR protection, etc.)
- **Telemetry** — SQLite (or MariaDB) logging of all sensor readings and events
- **REST + WebSocket API** — all state accessible from the browser or external tooling

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.11 or later |
| Node.js | 18 LTS or later |
| npm | bundled with Node |

Optional but recommended:
- **rigctld** (from the `hamlib` package) if you want radio integration without Python hamlib bindings
- A physical RS-485 USB adapter for direct hardware control

---

## Installation

### 1. Clone and set up Python environment

```bash
git clone <repo-url>
cd StationController_Py

python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

pip install -r requirements.txt
# For development (adds pytest, httpx, etc.):
pip install -r requirements-dev.txt
```

### 2. Build the frontend

```bash
cd ui
npm install
npm run build
cd ..
```

The build output lands in `ui_dist/` and is served automatically by the Python backend.

---

## Running

### Quick start (recommended)

```bash
# Linux / macOS / Raspberry Pi
chmod +x start.sh
./start.sh

# Windows
start.bat
```

The startup script activates the virtualenv if one is present, builds the frontend if `ui_dist/` is missing, then launches the backend. The app is available at **http://localhost:8080**.

On first run the `data/` directory is created and Alembic applies the database migrations automatically.

### Manual start

```bash
python main.py
```

### Development mode (hot-reload UI)

The `--dev` flag starts both the Python backend and the Vite dev server in one step:

```bash
./start.sh --dev   # Linux/macOS
start.bat --dev    # Windows
```

Open **http://localhost:5173** instead of 8080 — the Vite server proxies `/api` and `/ws` to the backend automatically, so live UI edits reflect instantly without a rebuild.

You can also start them manually in separate terminals:

```bash
# Terminal 1 — Python backend
python main.py

# Terminal 2 — Vite dev server (proxies /api and /ws to port 8080)
cd ui
npm run dev
```

Then open `http://localhost:5173`.

---

## Configuration

All configuration lives in `config/`. The app runs without any config files (hardware sections are simply skipped), so you can start with an empty setup and add sections as you wire up hardware.

### `config/comms_config.yaml` — DCN network transports

Defines how Python talks to the hardware bus. Three transport types are supported:

```yaml
networks:
  # Direct RS-485 USB serial
  - name: control
    type: rs485
    port: /dev/ttyUSB0      # Windows: COM3
    baud_rate: 9600

  # High-speed RS-485 for power meter (separate port)
  - name: power
    type: rs485
    port: /dev/ttyUSB1
    baud_rate: 115200

  # Alternatively, bridge through a Node-RED flow via MQTT
  - name: nodered
    type: nodered_mqtt
    broker: localhost
    port: 1883
    topic_rx: dcn/control/rx
    topic_tx: dcn/control/tx
```

If no config file exists or the file is empty, no hardware is connected and the app runs in a read-only/demo mode.

### `config/radio_config.yaml` — Radio control

```yaml
radios:
  # Recommended: connect to a running rigctld daemon
  # Start it with: rigctld -m 351 -r /dev/ttyUSB0 -s 9600
  - name: ic7300
    backend: rigctld
    host: localhost
    port: 4532
    poll_interval_s: 0.5
    reconnect_delay_s: 5.0

  # Alternative: direct hamlib Python bindings (local serial only)
  # Requires python3-hamlib to be installed
  - name: ft991
    backend: hamlib_direct
    model_id: 135           # 135 = FT-991A; 1 = DUMMY for testing
    port: /dev/ttyUSB1      # Windows: COM3
    baud_rate: 38400
    data_bits: 8
    stop_bits: 1
    parity: N
    poll_interval_s: 1.0
    reconnect_delay_s: 5.0
```

Radio settings can also be changed at runtime from the **Settings** page in the UI without restarting the app.

### `config/telemetry_config.yaml` — Database and logging

```yaml
telemetry:
  enabled: true

  database:
    url: "sqlite+aiosqlite:///data/station.db"
    # MariaDB alternative:
    # url: "mysql+aiomysql://user:pass@localhost/stationdb"

  sensor_recording:
    min_interval_s: 1.0        # minimum seconds between DB writes per sensor
    min_change_threshold: 0.0  # only log if value changed by at least this amount
    exclude: []                # sensor keys to never log

  dcn_logging:
    enabled: false             # raw DCN packet log (high volume, debug only)

  retention:
    sensor_readings_days: 90
    device_events_days: 365
    application_log_days: 30
```

### `config/labels.yaml` — Friendly names

Maps internal sensor/relay keys to human-readable names shown in the UI and available in automation rules:

```yaml
labels:
  coax_port_1: "20m Yagi"
  coax_port_2: "40m Dipole"
  ant_relay_1: "Amp Bypass"
  ant_relay_2: "Low Pass Filter"
  vhf_relay:   "2m/70cm Relay"
```

Labels can also be edited live from the **Labels** tab in the UI.

### `config/automation_config.yaml` — Automation rules

Trigger → Condition → Action rules in YAML. No Python code needed.

```yaml
automations:

  - name: "switch_antenna_on_band_change"
    tier: advisory
    trigger:
      type: band_entered
      band: "40m"
    action:
      type: set_relay
      dcn_address: "02"
      relay_num: 2
      state: 1

  - name: "protect_high_swr"
    tier: protection
    priority: 100
    trigger:
      type: sensor_above
      sensor: watt_meter_swr
      threshold: 3.0
    condition:
      type: ptt_active
    action:
      type: log
      message: "SWR exceeded 3:1 during TX"
      level: warning
```

**Trigger types:** `sensor_above`, `sensor_below`, `sensor_changed`, `band_entered`, `band_exited`, `band_changed`, `ptt_on`, `ptt_off`, `radio_connected`, `radio_disconnected`, `manual`

**Condition types:** `ptt_active`, `radio_connected`, `mode_is`, `frequency_in_band`, `sensor_above`, `sensor_below`, `sensor_between`, `relay_on`, `relay_off`, `and`, `or`, `not`

**Action types:** `log`, `set_relay`, `set_radio_power`, `sequence`, `conditional`

**Execution modes:** `single` (default — skip if already running), `restart`, `queued`, `parallel`

---

## Dashboard configuration

Dashboards are defined in `config/dashboards/<id>.yaml`. The main dashboard is `main.yaml`. Changes take effect the next time you navigate to the Dashboards tab (no restart needed).

```yaml
id: main
title: "Station Monitor"

cards:
  - type: power_meter
    title: "Forward Power"
    sensor: watt_meter_forward_power_w
    max_w: 1500            # full-scale value
    color: "#4ade80"

  - type: power_meter
    title: "Reflected Power"
    sensor: watt_meter_reflected_power_w
    max_w: 1500
    color: "#f87171"

  - type: swr_bar
    title: "SWR"
    sensor: watt_meter_swr
    thresholds:
      good: 1.5
      warning: 2.0
      critical: 3.0

  - type: relay
    title: "Amp Bypass"
    relay_key: ant_relay_1
    device_addr: "06"
    relay_num: 1

  - type: sensor
    title: "PA Temperature"
    sensor: temp_pa
    unit: "°F"
    warn_above: 140
    critical_above: 160

  - type: sensor
    title: "12V Supply"
    sensor: voltage_12v
    unit: "V"
    warn_below: 12.0
    critical_below: 11.5

  - type: radio_status
    title: "Radio"
```

---

## Hardware device addresses

The five built-in DCN devices are wired to these addresses in `main.py`. Update `main.py` if your hardware uses different addresses.

| Device | Default address |
|---|---|
| GPIO module (#321) | `01` |
| HF coax switch (#331) | `02` |
| RF watt meter (#351) | `03` |
| VHF coax relay (#332) | `05` |
| Antenna relay module (#361) | `06` |

Sensor keys follow the pattern `<device_name>_<measurement>`, e.g. `watt_meter_forward_power_w`, `coax_port_1`, `ant_relay_1`.

---

## Running tests

### Python backend

```bash
pytest
```

Tests that require physical hardware are marked `@pytest.mark.hardware` and are skipped by default. To include them:

```bash
pytest -m hardware
```

### Frontend (Svelte / Vitest)

```bash
cd ui
npm test          # single run
npm run test:watch  # interactive watch mode
```

---

## Project structure

```
StationController_Py/
├── main.py                 # Application entry point
├── api/                    # FastAPI app, routers, WebSocket hub
├── automation/             # Trigger → Condition → Action engine
├── comms/                  # DCN network and transport backends
├── devices/                # Hardware modules (GPIO, relays, meters)
├── radio/                  # Radio control and polling
├── sensors/                # Sensor registry and label registry
├── telemetry/              # SQLAlchemy models, recorder, logging
├── ui/                     # Svelte frontend source
├── ui_dist/                # Compiled frontend (served by backend)
├── config/                 # All YAML configuration
│   ├── comms_config.yaml
│   ├── radio_config.yaml
│   ├── automation_config.yaml
│   ├── telemetry_config.yaml
│   ├── labels.yaml
│   └── dashboards/
│       └── main.yaml
├── data/                   # Runtime data (SQLite DB created here)
├── alembic/                # Database migration scripts
└── tests/                  # pytest test suite
```

---

## API

The REST API is available at `http://localhost:8080/api/`. Interactive docs (Swagger UI) are at **http://localhost:8080/docs**.

Key endpoints:

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/sensors` | All current sensor values |
| `GET` | `/api/relays` | All relay states |
| `POST` | `/api/relays/{key}` | Toggle or set a relay |
| `GET` | `/api/radio` | Current radio state |
| `GET` | `/api/radio/config` | Radio configuration |
| `PUT` | `/api/radio/config` | Update and reconnect radio |
| `POST` | `/api/radio/reconnect` | Reconnect existing radio config |
| `GET` | `/api/dashboards/{id}` | Dashboard card definitions |
| `GET` | `/api/labels` | All friendly name labels |
| `PUT` | `/api/labels` | Update labels |
| `WS` | `/ws` | WebSocket stream (sensor, radio, label updates) |
