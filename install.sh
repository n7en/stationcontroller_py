#!/usr/bin/env bash
# Station Controller — install script
#
# Usage:
#   ./install.sh          # production install
#   ./install.sh --dev    # also install test/dev dependencies

set -euo pipefail

# BASH_SOURCE[0] is empty or /dev/stdin when piped via curl; fall back to $PWD
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-.}")" 2>/dev/null && pwd || echo "$PWD")"

DEV=0
for arg in "$@"; do
    [[ "$arg" == "--dev" ]] && DEV=1
done

# ── colours ────────────────────────────────────────────────────────────────
bold=$(tput bold 2>/dev/null || true)
green=$(tput setaf 2 2>/dev/null || true)
yellow=$(tput setaf 3 2>/dev/null || true)
cyan=$(tput setaf 6 2>/dev/null || true)
red=$(tput setaf 1 2>/dev/null || true)
reset=$(tput sgr0 2>/dev/null || true)

info()    { echo "${bold}${green}==>${reset} $*"; }
warn()    { echo "${bold}${yellow}  ! ${reset} $*"; }
die()     { echo "${bold}${red}error:${reset} $*" >&2; exit 1; }
prompt()  { printf "${bold}${cyan}  ?${reset} %s " "$*"; }

# ── 0. Bootstrap — clone repo if running via curl pipe ────────────────────
REPO_URL="https://github.com/n7en/stationcontroller_py"

if [[ ! -f "$SCRIPT_DIR/main.py" ]]; then
    INSTALL_DIR="${STATIONCONTROLLER_DIR:-$HOME/StationController_Py}"
    info "Cloning StationController_Py into $INSTALL_DIR…"
    if [[ -d "$INSTALL_DIR/.git" ]]; then
        warn "Directory already exists — pulling latest changes instead."
        git -C "$INSTALL_DIR" pull --ff-only
    else
        git clone "$REPO_URL" "$INSTALL_DIR"
    fi
    exec bash "$INSTALL_DIR/install.sh" "$@"
fi

cd "$SCRIPT_DIR"

# ── 1. Python ──────────────────────────────────────────────────────────────
info "Checking Python version…"

PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$candidate" &>/dev/null; then
        if "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
            PYTHON="$candidate"
            break
        fi
    fi
done

[[ -z "$PYTHON" ]] && die "Python 3.11+ is required. Install it and re-run."
echo "  Using: $PYTHON ($($PYTHON --version))"

# ── 2. Virtual environment ─────────────────────────────────────────────────
VENV="$SCRIPT_DIR/.venv"

if [[ ! -d "$VENV" ]]; then
    info "Creating virtual environment at .venv…"
    "$PYTHON" -m venv "$VENV"
else
    info "Virtual environment already exists — skipping creation."
fi

PIP="$VENV/bin/pip"
PYTHON_VENV="$VENV/bin/python"

# ── 3. Python dependencies ─────────────────────────────────────────────────
info "Installing Python dependencies…"
"$PIP" install --upgrade pip --quiet
"$PIP" install -r requirements.txt --quiet

if [[ "$DEV" -eq 1 ]]; then
    info "Installing dev dependencies…"
    "$PIP" install -r requirements-dev.txt --quiet
fi

# ── 4. Node.js / UI ────────────────────────────────────────────────────────
if [[ -d "$SCRIPT_DIR/ui" ]]; then
    info "Checking Node.js…"

    if ! command -v node &>/dev/null; then
        warn "Node.js not found — skipping UI install."
        warn "Install Node.js LTS (https://nodejs.org) and re-run to build the UI."
    else
        NODE_VER=$(node -e "process.stdout.write(String(process.version.slice(1).split('.')[0]))")
        if [[ "$NODE_VER" -lt 18 ]]; then
            warn "Node.js $NODE_VER detected — version 18+ is recommended."
        else
            echo "  Using: node v$(node --version | tr -d v) / npm $(npm --version)"
        fi

        info "Installing UI dependencies…"
        npm --prefix "$SCRIPT_DIR/ui" ci --silent

        info "Building UI…"
        npm --prefix "$SCRIPT_DIR/ui" run build --silent
        echo "  UI built → ui/dist/"
    fi
fi

# ── 5. Data directory ──────────────────────────────────────────────────────
info "Creating data directory…"
mkdir -p "$SCRIPT_DIR/data"

# ── 6. Database migrations ─────────────────────────────────────────────────
info "Running database migrations…"
"$PYTHON_VENV" - <<'PYEOF'
import pathlib, yaml
cfg_path = pathlib.Path("config/telemetry_config.yaml")
default_url = "sqlite+aiosqlite:///data/station.db"
if cfg_path.exists():
    raw = yaml.safe_load(cfg_path.read_text(encoding='utf-8')) or {}
    url = raw.get("telemetry", {}).get("database", {}).get("url", default_url)
else:
    url = default_url
sync_url = url.replace("sqlite+aiosqlite", "sqlite").replace("+aiomysql", "")
from alembic.config import Config as AlembicConfig
from alembic import command as alembic_cmd
cfg = AlembicConfig("alembic.ini")
cfg.set_main_option("script_location", "alembic")
cfg.set_main_option("sqlalchemy.url", sync_url)
alembic_cmd.upgrade(cfg, "head")
print(f"  DB: {sync_url}")
PYEOF

# ── 7. Serial port configuration (Linux only) ─────────────────────────────
if [[ "$(uname -s)" == "Linux" ]]; then

    # Check dialout membership
    if ! groups | grep -qE '\bdialout\b'; then
        warn "Your user is not in the 'dialout' group."
        warn "Run: sudo usermod -aG dialout \$USER  (then log out and back in)"
    fi

    COMMS_CFG="$SCRIPT_DIR/config/comms_config.yaml"

    if [[ -f "$COMMS_CFG" ]]; then
        info "Scanning for serial ports…"

        # Collect candidate ports with descriptions via Python
        PORT_LIST=$("$PYTHON_VENV" - <<'PYEOF'
import os, pathlib, subprocess, sys

def udev_attr(dev, key):
    try:
        out = subprocess.check_output(
            ["udevadm", "info", "--query=property", f"--name={dev}"],
            stderr=subprocess.DEVNULL, text=True,
        )
        for line in out.splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""

def sys_attr(dev_name, *parts):
    p = pathlib.Path(f"/sys/class/tty/{dev_name}").joinpath(*parts)
    try:
        return p.read_text().strip()
    except Exception:
        return ""

globs = [
    "/dev/ttyUSB*",   # USB-to-serial (FTDI, CP210x, CH340, PL2303, …)
    "/dev/ttyACM*",   # USB CDC ACM
    "/dev/ttyXRUSB*", # EXAR USB
    "/dev/ttyAMA*",   # Raspberry Pi hardware UART
    "/dev/ttyS*",     # built-in UARTs
    "/dev/rfcomm*",   # Bluetooth serial
]

import glob as _glob
found = []
for pattern in globs:
    for dev in sorted(_glob.glob(pattern)):
        name = os.path.basename(dev)

        # Skip built-in ttyS ports that have no physical device behind them
        if name.startswith("ttyS"):
            driver = sys_attr(name, "device", "driver", "module")
            if not driver and not pathlib.Path(f"/sys/class/tty/{name}/device").exists():
                continue

        vendor  = udev_attr(dev, "ID_VENDOR")
        model   = udev_attr(dev, "ID_MODEL")
        serial  = udev_attr(dev, "ID_SERIAL_SHORT")
        subsys  = udev_attr(dev, "ID_BUS")

        parts = [p for p in [vendor, model] if p]
        desc  = " - " + " ".join(parts) if parts else ""
        if serial:
            desc += f" [{serial}]"

        print(f"{dev}{desc}")
        found.append(dev)

if not found:
    sys.exit(1)
PYEOF
        ) || true

        if [[ -z "$PORT_LIST" ]]; then
            warn "No serial ports detected — skipping port configuration."
            warn "Plug in your USB adapter and re-run, or edit config/comms_config.yaml manually."
        else
            echo ""
            echo "  Available serial ports:"
            echo ""

            # Build indexed array of ports
            mapfile -t PORTS < <(echo "$PORT_LIST" | awk '{print $1}')
            mapfile -t DESCS < <(echo "$PORT_LIST")

            for i in "${!DESCS[@]}"; do
                printf "    ${bold}[%d]${reset} %s\n" "$((i+1))" "${DESCS[$i]}"
            done
            printf "    ${bold}[0]${reset} Skip — keep existing config\n"
            echo ""

            # Find active rs485 transports in the config
            TRANSPORTS=$("$PYTHON_VENV" - "$COMMS_CFG" <<'PYEOF'
import sys, yaml, pathlib
cfg = yaml.safe_load(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8')) or {}
for bus in cfg.get("buses", []):
    for t in bus.get("transports", []):
        if t.get("type") == "rs485":
            print(f"{t['name']}|{t.get('port','')}|{bus['name']}|{t.get('baud_rate', 9600)}")
PYEOF
            )

            if [[ -z "$TRANSPORTS" ]]; then
                warn "No active rs485 transports found in comms_config.yaml."
            else
                # Collect (transport, chosen_port) pairs then patch the file once
                declare -A PORT_CHOICES

                while IFS='|' read -r t_name current_port bus_name baud_rate; do
                    if [[ "$baud_rate" -eq 115200 ]]; then
                        speed_label="${bold}${yellow}High-speed / power meter (115200 baud)${reset}"
                        speed_note="  Use a dedicated USB adapter — do not share with control traffic."
                    else
                        speed_label="${bold}Standard DCN (${baud_rate} baud)${reset}"
                        speed_note=""
                    fi
                    echo "  Bus ${bold}${bus_name}${reset} · transport ${bold}${t_name}${reset} · ${speed_label}"
                    [[ -n "$speed_note" ]] && echo "  ${yellow}${speed_note}${reset}"
                    echo "  Currently: ${current_port}"
                    prompt "Select port number (0 to skip):"
                    read -r choice </dev/tty

                    if [[ "$choice" =~ ^[1-9][0-9]*$ ]] && \
                       [[ "$choice" -ge 1 ]] && \
                       [[ "$choice" -le "${#PORTS[@]}" ]]; then
                        PORT_CHOICES["$t_name"]="${PORTS[$((choice-1))]}"
                        echo "    → ${PORTS[$((choice-1))]}"
                    else
                        echo "    → skipped"
                    fi
                    echo ""
                done <<< "$TRANSPORTS"

                # Apply all choices with a single Python patch pass
                if [[ "${#PORT_CHOICES[@]}" -gt 0 ]]; then
                    PATCH_ARGS=()
                    for t_name in "${!PORT_CHOICES[@]}"; do
                        PATCH_ARGS+=("${t_name}=${PORT_CHOICES[$t_name]}")
                    done

                    "$PYTHON_VENV" - "$COMMS_CFG" "${PATCH_ARGS[@]}" <<'PYEOF'
import sys, re, pathlib

cfg_path = pathlib.Path(sys.argv[1])
# Build map of transport_name -> new_port from remaining args
assignments = {}
for arg in sys.argv[2:]:
    name, _, port = arg.partition("=")
    assignments[name] = port

text = cfg_path.read_text(encoding='utf-8')
lines = text.splitlines(keepends=True)
result = []

# State machine: track which transport block we are inside
current_transport = None
in_transport = False

for line in lines:
    # Detect start of a transport entry (list item with 'name:')
    m_name = re.match(r'^(\s*)-\s+name:\s+(\S+)', line)
    if m_name:
        current_transport = m_name.group(2)
        in_transport = True
        result.append(line)
        continue

    # Detect a new top-level key that ends the transport block
    # (indented less or equal to bus level, or a new list item)
    if in_transport:
        m_key = re.match(r'^(\s+)\w', line)
        if not line.strip() or (m_key and len(m_key.group(1)) <= 2 and not line.lstrip().startswith('-')):
            in_transport = False
            current_transport = None

    # Patch the port line if we are inside a targeted transport
    if in_transport and current_transport in assignments:
        m_port = re.match(r'^(\s+port:\s*)(\S+)(.*)', line)
        if m_port:
            new_port = assignments[current_transport]
            line = f"{m_port.group(1)}{new_port}\n"

    result.append(line)

cfg_path.write_text("".join(result), encoding='utf-8')
print(f"  Updated {cfg_path}")
PYEOF
                fi
            fi
        fi
    fi
fi

# ── 8. Simulator setup (dev branches only) ────────────────────────────────
_SIM_READY=0
if [[ -d "$SCRIPT_DIR/simulator" ]]; then
    _BRANCH=$(git -C "$SCRIPT_DIR" branch --show-current 2>/dev/null || \
              git -C "$SCRIPT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || \
              echo "")
    if [[ -n "$_BRANCH" && "$_BRANCH" != "main" ]]; then
        SIM_CFG="$SCRIPT_DIR/simulator/sim_config.yaml"
        echo ""
        info "DCN simulator available (branch: $_BRANCH)"
        prompt "Set up simulator for testing? [y/N]:"
        read -r _sim_choice </dev/tty
        if [[ "$_sim_choice" =~ ^[Yy]$ ]]; then
            "$PYTHON_VENV" - "$SCRIPT_DIR/config/comms_config.yaml" "$SIM_CFG" <<'PYEOF'
import sys, yaml, pathlib

comms_path = pathlib.Path(sys.argv[1])
sim_path   = pathlib.Path(sys.argv[2])

sim = yaml.safe_load(sim_path.read_text(encoding='utf-8')) or {}

if not comms_path.exists():
    print("  comms_config.yaml not found - simulator will use defaults")
    sys.exit(0)

comms = yaml.safe_load(comms_path.read_text(encoding='utf-8')) or {}

# Pull settings from the first nodered_mqtt transport found
mqtt_t = None
for bus in comms.get('buses', []):
    for t in bus.get('transports', []):
        if t.get('type') == 'nodered_mqtt':
            mqtt_t = t
            break
    if mqtt_t:
        break

if mqtt_t:
    sim.setdefault('mqtt', {}).update({
        'broker':   mqtt_t.get('broker', 'localhost'),
        'port':     int(mqtt_t.get('port', 1883)),
        'username': mqtt_t.get('username', '') or '',
        'password': mqtt_t.get('password', '') or '',
    })
    sim['topic_rx'] = mqtt_t.get('topic_rx', 'dcn/control/rx')
    sim['topic_tx'] = mqtt_t.get('topic_tx', 'dcn/control/tx')
    print(f"  MQTT broker: {sim['mqtt']['broker']}:{sim['mqtt']['port']}")
    print(f"  RX topic:    {sim['topic_rx']}")
    print(f"  TX topic:    {sim['topic_tx']}")
else:
    print("  No nodered_mqtt transport found - using defaults (localhost:1883)")

# Sync device list; preserve per-device settings (intervals, initial states)
TYPE_MAP = {
    'gpio': 'gpio', 'coax_switch': 'coax_switch', 'watt_meter': 'watt_meter',
    'vhf_relay': 'vhf_relay', 'antenna_relay': 'antenna_relay',
}
comms_devs = [d for d in comms.get('devices', []) if d.get('type') in TYPE_MAP]
if comms_devs:
    by_addr = {d['address']: d for d in sim.get('devices', [])}
    sim['devices'] = []
    for d in comms_devs:
        entry = dict(by_addr.get(d['address'], {}))
        entry.update({'type': TYPE_MAP[d['type']], 'address': d['address'],
                      'name': d.get('name', d['address'])})
        sim['devices'].append(entry)
        print(f"  device: {entry['type']:15s}  addr={entry['address']}")

sim_path.write_text(yaml.dump(sim, default_flow_style=False, sort_keys=False, allow_unicode=False), encoding='utf-8')
print(f"  Written -> {sim_path}")
PYEOF
            _SIM_READY=1
        else
            echo "    -> skipped"
        fi
    fi
fi

# ── 9. Systemd service (Linux only) ──────────────────────────────────────
_SERVICE_READY=0
if [[ "$(uname -s)" == "Linux" ]] && command -v systemctl &>/dev/null; then
    # Determine how to run privileged commands
    if [[ "$EUID" -eq 0 ]]; then
        _PRIV=""                          # already root
        _SVC_USER="${SUDO_USER:-${USER}}" # real user if invoked via sudo
    elif command -v sudo &>/dev/null; then
        _PRIV="sudo"
        _SVC_USER="$USER"
    else
        _PRIV=""
        _SVC_USER="$USER"
        warn "Not root and sudo not found — service installation will be skipped."
    fi

    SERVICE_NAME="stationcontroller"
    SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
    echo ""
    info "Systemd service setup"

    SERVICE_CONTENT="[Unit]
Description=StationController
After=network.target

[Service]
Type=simple
User=${_SVC_USER}
WorkingDirectory=${SCRIPT_DIR}
ExecStart=${SCRIPT_DIR}/.venv/bin/python main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target"

    prompt "Install and enable a systemd service to start at boot? [y/N]:"
    read -r _svc_choice </dev/tty
    if [[ "$_svc_choice" =~ ^[Yy]$ ]]; then
        if [[ "$EUID" -eq 0 ]] || command -v sudo &>/dev/null; then
            # Write directly to systemd and enable
            echo "$SERVICE_CONTENT" | ${_PRIV} tee "$SERVICE_FILE" > /dev/null
            ${_PRIV} systemctl daemon-reload
            ${_PRIV} systemctl enable --now "$SERVICE_NAME"
            echo "  Service enabled: ${SERVICE_NAME}"
            _SERVICE_READY=1
        else
            # No privilege escalation — write the unit file locally for the user to install
            LOCAL_UNIT="$HOME/${SERVICE_NAME}.service"
            echo "$SERVICE_CONTENT" > "$LOCAL_UNIT"
            warn "No root or sudo available. Service file written to:"
            warn "  $LOCAL_UNIT"
            warn "To install it, copy it as root and enable:"
            warn "  cp $LOCAL_UNIT $SERVICE_FILE"
            warn "  systemctl daemon-reload"
            warn "  systemctl enable --now ${SERVICE_NAME}"
        fi
    else
        echo "    -> skipped"
    fi
fi

# ── Done ───────────────────────────────────────────────────────────────────
echo ""
echo "${bold}${green}Installation complete.${reset}"
echo ""
if [[ "$_SERVICE_READY" -eq 1 ]]; then
    echo "  Service status:    sudo systemctl status stationcontroller"
    echo "  Stop/start:        sudo systemctl stop|start stationcontroller"
    echo "  View logs:         journalctl -u stationcontroller -f"
else
    echo "  Start the server:  .venv/bin/python main.py"
fi
[[ -d "$SCRIPT_DIR/ui/dist" ]] && echo "  UI available at:   http://localhost:8080"
[[ "$_SIM_READY" -eq 1 ]] && echo "  Run simulator:     .venv/bin/python -m simulator"
echo ""
if [[ "$DEV" -eq 1 ]]; then
    echo "  Run tests:         .venv/bin/pytest"
    echo "  UI tests:          npm --prefix ui test"
    echo ""
fi
