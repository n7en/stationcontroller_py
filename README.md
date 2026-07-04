# StationController

A Python-based amateur radio station controller with a live web UI. It manages antenna switching, relay control, radio integration, RF power monitoring, and automation rules -- all through a browser dashboard served from the same machine running the hardware.

---

## Features

- **Live dashboard** -- configurable cards: power meters, SWR bar, relay toggles, sensor readouts, radio status
- **Radio integration** -- frequency, mode, and PTT monitoring via rigctld or direct hamlib
- **DCN hardware** -- talks to GPIO modules, coax switches, VHF relays, antenna relay banks, and RF watt meters over RS-485
- **Automation engine** -- YAML-defined trigger -> condition -> action rules (band-change antenna switching, SWR protection, etc.)
- **Telemetry** -- SQLite (or MariaDB) logging of all sensor readings and events
- **Logbook integration** -- live QSO feed from N1MM+ and N3FJP, a remote push API, and worked-before queries for automations
- **REST + WebSocket API** -- all state accessible from the browser or external tooling

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

### Linux / Raspberry Pi / macOS

```bash
curl -fsSL https://raw.githubusercontent.com/n7en/stationcontroller_py/dev/install.sh | bash
```

This clones the repository into `~/StationController_Py`, creates a Python virtual environment, installs all dependencies, builds the UI, runs the database migrations, scans for serial ports -- prompting you to assign each DCN bus -- and optionally installs a systemd service so the app starts at boot. The script also offers to configure the [DCN simulator](#dcn-simulator).

To include development tools (pytest, etc.) as well:

```bash
curl -fsSL https://raw.githubusercontent.com/n7en/stationcontroller_py/dev/install.sh | bash -s -- --dev
```

To clone to a custom location, set `STATIONCONTROLLER_DIR` before running:

```bash
STATIONCONTROLLER_DIR=/opt/stationcontroller \
  curl -fsSL https://raw.githubusercontent.com/n7en/stationcontroller_py/dev/install.sh | bash
```

### Windows

Open **PowerShell** and run:

```powershell
irm https://raw.githubusercontent.com/n7en/stationcontroller_py/dev/install.ps1 | iex
```

This clones the repository into `~\StationController_Py`, sets up the Python virtual environment, installs all dependencies, builds the UI, runs the database migrations, and scans for COM ports -- prompting you to assign each DCN bus. The script also offers to configure the [DCN simulator](#dcn-simulator).

To include development tools as well:

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/n7en/stationcontroller_py/dev/install.ps1))) -Dev
```

To clone to a custom location, set `STATIONCONTROLLER_DIR` before running:

```powershell
$env:STATIONCONTROLLER_DIR = "C:\station"
irm https://raw.githubusercontent.com/n7en/stationcontroller_py/dev/install.ps1 | iex
```

> **Note:** If PowerShell blocks script execution, run this first:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

### Manual install

If you prefer not to use the one-liner, or need to install in a restricted environment, follow these steps.

#### Linux / macOS

```bash
git clone https://github.com/n7en/stationcontroller_py
cd StationController_Py

# Create virtual environment and install Python dependencies
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Install dev tools (optional)
.venv/bin/pip install -r requirements-dev.txt

# Build the UI
cd ui && npm install && npm run build && cd ..

# Run database migrations
.venv/bin/alembic upgrade head
```

Edit `config/comms_config.yaml` to assign your serial ports and MQTT topics, then start the app:

```bash
.venv/bin/python main.py
```

#### Windows

Open **PowerShell** in the repo directory.

```powershell
git clone https://github.com/n7en/stationcontroller_py
cd StationController_Py

# Create virtual environment and install Python dependencies
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# Install dev tools (optional)
.venv\Scripts\pip install -r requirements-dev.txt

# Build the UI
cd ui; npm install; npm run build; cd ..

# Run database migrations
.venv\Scripts\alembic upgrade head
```

If your system Python is not on `PATH`, use the full path from `py -3 -c "import sys; print(sys.executable)"`.

If PowerShell blocks script execution:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Edit `config\comms_config.yaml` to assign your COM ports and MQTT topics, then start the app:

```powershell
.venv\Scripts\python main.py
```

Re-running the install scripts at any time is safe -- they skip steps already done and apply any new migrations.

---

## Running

### Quick start

```bash
# Linux / macOS
.venv/bin/python main.py
```

```powershell
# Windows
.venv\Scripts\python main.py
```

The app is available at **https://localhost:8080**. On first run the `data/` directory is created, Alembic applies the database migrations automatically, and a self-signed TLS certificate is generated in `config/certs/`. Your browser will show a security warning the first time -- accept the exception to proceed. The certificate is local-only and is regenerated each install.

### Navigating the UI

| Tab | What's there |
|---|---|
| **Dashboard** | Configurable cards -- power meters, SWR bar, relay toggles, sensor readouts, radio status, DX spots, logbook. Defined in `config/dashboards/main.yaml`. |
| **DX Spots** | Full-page DX cluster spot browser with band/continent/mode filters and one-click QSY. |
| **Relays** | All relay outputs in one place -- toggle individually or by group. Labels are editable inline. |
| **Labels** | Edit friendly names for any sensor or relay key. Changes apply immediately across the whole UI. |
| **History** | Time-series charts for temperature, voltage, and any recorded sensor. |
| **Logs** | Live log stream from the backend (general app log and raw DCN packet log on separate tabs). |
| **Config** | Comms & devices, Stream Deck, radio connection, raw YAML editor, appearance, and system controls in one tabbed page. |
| **Band Plan** | View and edit the band plan used for band detection and the frequency display. |
| **Setup** | First-run wizard for buses, devices, and the radio. |

The **Dashboard** tab is the main operating view. Open `config/dashboards/main.yaml` to add, remove, or rearrange cards -- the changes are picked up the next time you switch to the Dashboards tab, no restart required.

### Network access

The server binds to `0.0.0.0:8080`, so any device on the same network can reach the UI at `https://<machine-ip>:8080` -- useful for phones, tablets, or a second computer in the shack. Each browser connecting for the first time will need to accept the self-signed certificate warning.

**Windows:** the firewall may block port 8080 the first time Python tries to bind to it. To open it:

```powershell
netsh advfirewall firewall add rule name="StationController" dir=in action=allow protocol=TCP localport=8080
```

Or via the GUI: **Windows Defender Firewall -> Advanced Settings -> Inbound Rules -> New Rule -> Port -> TCP 8080**.

**Linux / Raspberry Pi:** no firewall blocks the port by default -- other devices can connect immediately.

### Manual start

```bash
.venv/bin/python main.py
```

### Systemd service (Linux)

If you answered **y** to the service prompt during install, the app runs as a systemd service named `stationcontroller` and starts automatically at boot.

```bash
# Status
sudo systemctl status stationcontroller

# Stop / start / restart
sudo systemctl stop stationcontroller
sudo systemctl start stationcontroller
sudo systemctl restart stationcontroller

# Follow logs
journalctl -u stationcontroller -f

# Disable autostart
sudo systemctl disable stationcontroller
```

To install the service manually after the fact, run as root (or prefix with `sudo` if available):

```bash
cat > /etc/systemd/system/stationcontroller.service <<EOF
[Unit]
Description=StationController
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME/StationController_Py
ExecStart=$HOME/StationController_Py/.venv/bin/python main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now stationcontroller
```

### Development mode (hot-reload UI)

Start both servers in separate terminals:

```bash
# Terminal 1 -- Python backend
python main.py

# Terminal 2 -- Vite dev server (proxies /api and /ws to port 8080)
cd ui
npm run dev
```

Then open `https://localhost:5173`.

---

## Configuration

All configuration lives in `config/`. The app runs without any config files (hardware sections are simply skipped), so you can start with an empty setup and add sections as you wire up hardware.

### `config/comms_config.yaml` -- DCN network transports

Defines how Python talks to the hardware bus. Three transport types are supported:

```yaml
buses:
  # Standard 9600-baud control bus (GPIO, relays, coax switches)
  - name: control
    transports:
      - name: control_serial
        type: rs485
        port: /dev/ttyUSB0      # Windows: COM3
        baud_rate: 9600

  # High-speed 115200-baud bus for RF watt meter in streaming mode
  # Keep on a dedicated USB adapter -- do not share with control traffic
  - name: power
    transports:
      - name: power_serial
        type: rs485
        port: /dev/ttyUSB1      # Windows: COM4
        baud_rate: 115200

  # Optional: Node-RED MQTT bridge instead of direct serial
  # Import nodered/dcn_mqtt_bridge_flow.json into Node-RED
  - name: control
    transports:
      - name: control_mqtt
        type: nodered_mqtt
        broker: localhost
        port: 1883
        topic_rx: dcn/control/rx
        topic_tx: dcn/control/tx
```

If no config file exists or the file is empty, no hardware is connected and the app runs in a read-only/demo mode.

### `config/radio_config.yaml` -- Radio control

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

### `config/telemetry_config.yaml` -- Database and logging

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
    automation_events_days: 365
    application_log_days: 30
    dcn_message_log_hours: 24
```

Old records are pruned automatically at startup and then hourly.

### `config/labels.yaml` -- Friendly names

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

### `config/automation_config.yaml` -- Automation rules

Trigger -> Condition -> Action rules in YAML. No Python code needed.

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

**Execution modes:** `single` (default -- skip if already running), `restart`, `queued`, `parallel`

---

### `config/logbook_config.yaml` -- Logbook integration

StationController can maintain a live in-memory copy of your log by listening
to popular logging software. The **Logbook** dashboard card shows backend
status and recent contacts, and automations can ask whether a station has
already been worked. Copy `config/logbook_config.yaml.example` to
`logbook_config.yaml` and enable one or both backends:

```yaml
logbook:
  n1mm:
    enabled: true
    host: "0.0.0.0"
    port: 12060        # UDP port N1MM+ broadcasts to

  n3fjp:
    enabled: true
    host: "localhost"  # machine running N3FJP
    port: 1100         # N3FJP TCP API port
    poll_interval_s: 5.0
```

**N1MM+ Logger Plus** -- passive UDP listener. In N1MM+: Config ->
Configure Ports... -> Broadcast Data tab -> enable **Contacts** and point it
at the StationController machine's IP, port 12060.

**N3FJP** (Amateur Contact Log, etc.) -- TCP polling client. In N3FJP:
Settings -> Application Program Interface -> enable the TCP API (port 1100).
The full existing log is loaded on connect, then new QSOs are picked up as
they are logged.

Query endpoints:

```
GET /api/logbook/status                        # backend connection status
GET /api/logbook/contacts?limit=100            # recent QSOs (newest first)
GET /api/logbook/worked?call=JA1XYZ&band=20m   # worked-before check
```

The log is held in memory (capped at 10,000 QSOs) and rebuilt from the
backends on restart.

#### Remote log push API

Modules on other machines can push QSOs directly over HTTPS -- no config
file needed:

```
POST /api/logbook/qso    # single QSO as it is logged
POST /api/logbook/qsos   # JSON array batch, max 10000 (initial sync)
```

```json
{"callsign": "JA1XYZ", "frequency_hz": 14025000, "mode": "CW", "source": "shack_pc"}
```

Only `callsign` is required. `band` is derived from `frequency_hz` when
omitted, `timestamp` (epoch seconds) defaults to now, and `source` labels
where the QSO came from. If auth is enabled, log in via
`POST /api/auth/login` first and carry the session cookie.

#### Remote log pusher (`tools/log_pusher.py`)

For setups where the logging PC cannot reach StationController with UDP
broadcasts or an open TCP port, run the bundled pusher **on the logging
machine**. It is a single file with no dependencies beyond Python 3.9+ --
copy just `tools/log_pusher.py` to the shack PC:

```bash
# Forward local N1MM+ broadcasts (point N1MM+ contacts broadcast at 127.0.0.1:12060)
python log_pusher.py --server https://192.168.1.50:8080

# Also poll a local N3FJP instance, with auth
python log_pusher.py --server https://station:8080 \
    --username admin --password secret \
    --n3fjp-host localhost --source shack_pc
```

QSOs are queued and retried with backoff while the server is unreachable,
the N3FJP log is batch-synced on connect, and TLS verification is off by
default to match the self-signed certificate (pass `--verify` if you have
installed a real one). Run `python log_pusher.py --help` for all options.

---

## Backup and restore

**Config -> System -> Backup & Restore** in the UI, or directly via the API:

```
GET  /api/system/backup                  # download config as a zip
GET  /api/system/backup?include_db=true  # also include a SQLite snapshot
POST /api/system/restore                 # upload a backup zip (raw body)
```

The backup contains every runtime YAML config file (buses, devices, radio,
automations, dashboards, labels, band plan, logbook, Stream Deck) plus a
manifest. TLS certificates are excluded -- they are machine-local and
regenerated on install. With `include_db=true` a consistent snapshot of the
live SQLite telemetry database is taken using SQLite's online backup API.

Restoring applies config files immediately and requires a restart to take
effect. Before anything is overwritten, the current config is snapshotted to
`data/backups/pre_restore_<timestamp>.zip`. A database included in the
archive is staged as `data/station.db.restore` and swapped in on the next
startup (the previous database is kept alongside as
`station.db.pre_restore_<timestamp>`).

Command-line equivalent from another machine:

```bash
curl -k -o backup.zip "https://station:8080/api/system/backup?include_db=true"
curl -k -X POST --data-binary @backup.zip https://station:8080/api/system/restore
```

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
    unit: "F"
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

  - type: dx_spots
    title: "20m DX"
    band: "20m"            # optional pre-filters: band, continent, mode
    span: 2
    row_span: 3

  - type: logbook
    title: "Logbook"
    limit: 50              # recent contacts to show
    span: 2
    row_span: 3
```

**Card types:** `power_meter`, `swr_bar`, `relay`, `sensor`, `radio_status`,
`dx_spots`, `logbook`, `solar`, `blank`. Cards can also be added and edited
directly in the UI via the dashboard's edit mode.

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

## DCN Simulator

The `simulator/` directory contains a software DCN hardware simulator for development and integration testing -- no physical RS-485 adapters or hardware required.

The simulator connects to an MQTT broker and publishes realistic device `UPDATE` packets on the same topics used by the Node-RED MQTT bridge transport. It also subscribes for commands from the app (relay set, coax select, position select, etc.) and updates its internal state accordingly, so the app behaves exactly as it would with real hardware.

### Prerequisites

An MQTT broker reachable from both the app and the simulator. [Mosquitto](https://mosquitto.org/) is the simplest option:

```bash
# Linux / Raspberry Pi
sudo apt install mosquitto mosquitto-clients
sudo systemctl enable --now mosquitto

# macOS
brew install mosquitto
brew services start mosquitto

# Windows
winget install EclipseFoundation.Mosquitto
```

### Setup

The install script configures the simulator automatically when you answer **y** to the simulator prompt. It reads `config/comms_config.yaml`, copies the `nodered_mqtt` transport settings (broker, port, topics, credentials) into `simulator/sim_config.yaml`, and syncs the device list to match your comms config.

To configure manually, edit `simulator/sim_config.yaml`:

```yaml
mqtt:
  broker: localhost       # MQTT broker hostname or IP
  port: 1883
  username: ""
  password: ""

# Must match the nodered_mqtt transport in config/comms_config.yaml
topic_rx: dcn/control/rx  # simulator publishes here  (app receives)
topic_tx: dcn/control/tx  # simulator subscribes here (app sends commands)

master_addr: "00"

devices:
  - type: gpio
    address: "01"
    name: gpio
    update_interval_s: 1.0
    relay_states: "00000000"   # initial state (8 chars, 0=off 1=on)
    voltage_min: 11.5          # V -- lower bound for all voltmeter channels
    voltage_max: 14.5          # V -- upper bound
    voltage_drift: 0.05        # max V change per update tick
    temp_min: 75.0             # F -- lower bound for both temp probes
    temp_max: 80.0             # F -- upper bound
    temp_steps: [0.1, 0.2]    # step sizes applied randomly up or down
    temp_tick_min: 3           # min ticks between temp changes
    temp_tick_max: 6           # max ticks between temp changes

  - type: watt_meter
    address: "03"
    name: watt_meter
    update_interval_s: 0.1    # 10 Hz -- matches streaming-mode firmware
    forward_power_w: 100.0    # nominal forward power (W) during TX
    tx_duration_min: 10.0     # s -- minimum TX-on duration per cycle
    tx_duration_max: 15.0     # s -- maximum TX-on duration per cycle
    off_duration_min: 5.0     # s -- minimum TX-off duration per cycle
    off_duration_max: 10.0    # s -- maximum TX-off duration per cycle
    reflected_min: 1.0        # W -- minimum reflected power target during TX
    reflected_max: 5.0        # W -- maximum reflected power target during TX

  # coax_switch   address "02"  -- selects antenna port 1-4
  # vhf_relay     address "05"  -- single SPDT relay
  # antenna_relay address "06"  -- 8-relay bank with POS / pulse / mask support
```

The app must have a `nodered_mqtt` transport configured in `config/comms_config.yaml` with matching topics -- the simulator acts as the hardware side of that bridge.

### Running

```bash
# Linux / macOS -- from repo root
.venv/bin/python -m simulator

# Windows
.venv\Scripts\python -m simulator

# Custom config file
python -m simulator path/to/sim_config.yaml

# Verbose (shows every packet sent and command received)
python -m simulator -v
```

Start the simulator before or after the main app -- it reconnects automatically if the broker restarts.

### Simulated devices

| Type | DCN module | Default addr | Notes |
|---|---|---|---|
| `gpio` | #321 | `01` | 8 relays, 4 digital inputs, 4 voltmeters, 2 temp sensors |
| `coax_switch` | #331 CX-1 | `02` | Selects one of 4 antenna ports |
| `watt_meter` | #351 | `03` | Forward/reflected power; runs at 10 Hz in streaming mode |
| `vhf_relay` | #332 CX-2 | `05` | Single SPDT relay |
| `antenna_relay` | #361 | `06` | 8-relay bank; supports POS, pulse, mask commands |

**Voltages** drift slowly within `voltage_min`-`voltage_max` each tick. **Temperatures** step by one of the `temp_steps` values (randomly up or down) every `temp_tick_min`-`temp_tick_max` ticks, staying within `temp_min`-`temp_max`. **RF power** auto-cycles: TX on for `tx_duration_min`-`tx_duration_max` seconds at `forward_power_w` with randomly varying reflected power, then off for `off_duration_min`-`off_duration_max` seconds. **Relay commands** from the UI are applied immediately and an updated packet is published back straight away -- no waiting for the next periodic tick.

### Radio simulation

The simulator includes two ways to simulate a radio transceiver without physical hardware.

#### rigctld TCP server

`SimRigctld` is an async TCP server that speaks the rigctld extended (`\`-prefix) protocol. Point the app's `rigctld` backend at it and it connects as if talking to a real `rigctld` daemon -- no changes to your radio config needed beyond host and port.

Enable it in `simulator/sim_config.yaml`:

```yaml
radio:
  rigctld:
    enabled: true
    host: "127.0.0.1"
    port: 4532          # must match radio_config.yaml
    initial:
      frequency_hz: 14200000
      mode: USB
      bandwidth_hz: 2400
      rf_power: 1.0
      signal_strength: -10.0   # S-meter dBm, adds small noise each read
```

Then in `config/radio_config.yaml`:

```yaml
radios:
  - name: sim_radio
    backend: rigctld
    host: 127.0.0.1
    port: 4532
    poll_interval_s: 0.5
```

#### Hamlib Python shim

`simulator/Hamlib.py` is a drop-in replacement for the real `Hamlib` Python bindings. It exposes the same API surface (`Rig`, `rig_strrmode`, `rig_strvfo`, all constants) so the `hamlib_direct` backend runs without any hardware or native library install.

Activate by prepending `simulator/` to `PYTHONPATH` before starting the app:

```bash
# Linux / macOS
PYTHONPATH=simulator .venv/bin/python main.py

# Windows (PowerShell)
$env:PYTHONPATH = "simulator"; .venv\Scripts\python main.py
```

The shim is self-contained -- it does not require the MQTT broker or any other part of the simulator stack.

---

## Testing automations with the simulator

The simulator lets you develop and verify automation rules end-to-end without any physical hardware. Sensor values update continuously, commands from the app are applied immediately, and the full automation engine runs against the simulated readings exactly as it would in the shack.

### 1 -- Add a simulator bus to `config/comms_config.yaml`

The simulator speaks the MQTT bridge protocol, so add a `nodered_mqtt` transport on a dedicated bus:

```yaml
buses:
  - name: simulator
    transports:
      - name: sim_mqtt
        type: nodered_mqtt
        broker: localhost
        port: 1883
        topic_rx: dcn/sim/rx    # app reads packets from here
        topic_tx: dcn/sim/tx    # app sends commands here
```

You can run a simulator bus alongside a real `control` bus -- they are independent, so hardware commands still go to the real RS-485 network.

### 2 -- Configure `simulator/sim_config.yaml` to match

```yaml
mqtt:
  broker: localhost
  port: 1883

topic_rx: dcn/sim/rx   # must match topic_rx above
topic_tx: dcn/sim/tx   # must match topic_tx above

master_addr: "00"

devices:
  - type: gpio
    address: "01"
    name: gpio
    update_interval_s: 1.0
    relay_states: "00000000"

  - type: watt_meter
    address: "03"
    name: watt_meter
    update_interval_s: 0.1
    forward_power_w: 100.0
    tx_duration_min: 10.0
    tx_duration_max: 15.0
    off_duration_min: 5.0
    off_duration_max: 10.0
    reflected_min: 1.0
    reflected_max: 5.0

  - type: antenna_relay
    address: "06"
    name: ant
    update_interval_s: 1.0
```

### 3 -- Point devices at the simulator bus

In `config/comms_config.yaml`, add or duplicate devices under the `simulator` bus:

```yaml
devices:
  - type: gpio
    name: gpio
    address: "01"
    bus: simulator

  - type: watt_meter
    name: watt_meter
    address: "03"
    bus: simulator

  - type: antenna_relay
    name: ant
    address: "06"
    bus: simulator
    persona: cc_8a
```

If you have real hardware on a `control` bus at the same addresses, give the simulated devices unique names (`name: sim_gpio`, etc.) -- the bus field routes each device's commands to the right network.

### 4 -- Write the automation rule

Create or edit `config/automation_config.yaml`. This example switches the antenna relay when band changes and protects against high SWR:

```yaml
automations:

  - name: "switch_antenna_40m"
    trigger:
      type: band_entered
      band: "40m"
    action:
      type: set_relay
      dcn_address: "06"
      relay_num: 2
      state: 1

  - name: "protect_high_swr"
    tier: protection
    trigger:
      type: sensor_above
      sensor: watt_meter_port_0_swr
      threshold: 2.5
    condition:
      type: ptt_active
    action:
      type: log
      message: "High SWR during TX -- check antenna"
      level: warning
```

Sensor keys follow the pattern `<device_name>_<measurement>` -- `watt_meter_port_0_swr`, `ant_relay_1`, `gpio_relay_1`, etc. The exact keys for your device names appear in the **Relays** page and the sensor list at `/api/sensors`.

### 5 -- Start the simulator alongside the app

```bash
# Terminal 1 -- main app
.venv/bin/python main.py

# Terminal 2 -- simulator
.venv/bin/python -m simulator

# Add -v to see every packet
.venv/bin/python -m simulator -v
```

The app and simulator connect to the MQTT broker independently. Either one can be restarted without affecting the other -- they will reconnect automatically.

### 6 -- Watch automations fire

Open the **Log** page and switch to the **DCN** tab. Use the bus filter dropdown (appears when more than one bus is active) to show only the `simulator` bus. Every UPDATE packet the simulator sends and every command the app sends back is visible here in real time.

For automation log output, check the **General** tab -- log-action rules write there with the configured level.

### Adjusting simulated values for specific scenarios

Edit `simulator/sim_config.yaml` and restart the simulator (no app restart needed) to change what the simulated hardware reports:

| Goal | Config key to change |
|---|---|
| Force high SWR | Increase `reflected_max` or reduce `reflected_min` |
| Keep transmitter on continuously | Set `off_duration_min` and `off_duration_max` to `0` |
| Slow down power meter updates | Increase `update_interval_s` on the watt_meter |
| Start with a relay pre-set on | Set that character to `1` in `relay_states` |
| Simulate a hot PA | Set `temp_min` and `temp_max` above your `warn_above` threshold |

### Simulating band changes without a radio

To test band-triggered rules without a real radio, enable the rigctld simulator and configure the app to connect to it:

`simulator/sim_config.yaml`:
```yaml
radio:
  rigctld:
    enabled: true
    host: "127.0.0.1"
    port: 4532
    initial:
      frequency_hz: 14200000   # start on 20m
      mode: USB
```

`config/radio_config.yaml`:
```yaml
radios:
  - name: sim_radio
    backend: rigctld
    host: 127.0.0.1
    port: 4532
    poll_interval_s: 0.5
```

With both running, use the radio frequency control in the UI to tune to a different band -- band-triggered automations will fire exactly as they would with real hardware.

---

## Project structure

```
StationController_Py/
+-- main.py                 # Application entry point
+-- api/                    # FastAPI app, routers, WebSocket hub
+-- automation/             # Trigger -> Condition -> Action engine
+-- comms/                  # DCN network and transport backends
+-- devices/                # Hardware modules (GPIO, relays, meters)
+-- radio/                  # Radio control and polling
+-- sensors/                # Sensor registry and label registry
+-- telemetry/              # SQLAlchemy models, recorder, logging
+-- logging_integration/    # Logbook backends (N1MM+, N3FJP) and manager
+-- tools/                  # Standalone helpers (remote log pusher)
+-- ui/                     # Svelte frontend source
+-- ui_dist/                # Compiled frontend (served by backend)
+-- config/                 # All YAML configuration
|   +-- comms_config.yaml
|   +-- radio_config.yaml
|   +-- automation_config.yaml
|   +-- telemetry_config.yaml
|   +-- logbook_config.yaml
|   +-- labels.yaml
|   +-- dashboards/
|       +-- main.yaml
+-- data/                   # Runtime data (SQLite DB created here)
+-- alembic/                # Database migration scripts
+-- tests/                  # pytest test suite
+-- simulator/              # DCN hardware simulator
    +-- dcn_sim.py          # Simulator logic and device models
    +-- sim_config.yaml     # MQTT and device configuration
```

---

## API

The REST API is available at `https://localhost:8080/api/`. Interactive docs (Swagger UI) are at **https://localhost:8080/docs**.

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
