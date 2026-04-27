#Requires -Version 5.1
<#
.SYNOPSIS
    Station Controller - Windows install script

.DESCRIPTION
    Clones the repository (if needed), creates a Python virtual environment,
    installs all dependencies, builds the UI, runs database migrations, and
    prompts you to assign COM ports to each DCN bus.

.PARAMETER Dev
    Also install test/dev dependencies (pytest, etc.)

.EXAMPLE
    .\install.ps1

.EXAMPLE
    .\install.ps1 -Dev

.EXAMPLE
    # Bootstrap directly from GitHub (no prior clone needed):
    irm https://raw.githubusercontent.com/n7en/stationcontroller_py/main/install.ps1 | iex

.EXAMPLE
    # Bootstrap with -Dev flag:
    & ([scriptblock]::Create((irm https://raw.githubusercontent.com/n7en/stationcontroller_py/main/install.ps1))) -Dev
#>

param([switch]$Dev)

$ErrorActionPreference = 'Stop'

$REPO_URL   = "https://github.com/n7en/stationcontroller_py"
$SCRIPT_DIR = if ($PSScriptRoot) { $PSScriptRoot } else { $PWD.Path }

# -- helpers ----------------------------------------------------------------
function Info   { param($msg) Write-Host "==> $msg" -ForegroundColor Green }
function Warn   { param($msg) Write-Host "  ! $msg" -ForegroundColor Yellow }
function Die    { param($msg) Write-Host "error: $msg" -ForegroundColor Red; exit 1 }
function Prompt { param($msg) Write-Host "  ? $msg " -ForegroundColor Cyan -NoNewline }

# -- 0. Bootstrap: clone repo if running via irm | iex ---------------------
if (-not (Test-Path (Join-Path $SCRIPT_DIR "main.py"))) {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Die "git is required. Install from https://git-scm.com/download/win"
    }

    $installDir = if ($env:STATIONCONTROLLER_DIR) {
        $env:STATIONCONTROLLER_DIR
    } else {
        Join-Path $HOME "StationController_Py"
    }

    Info "Cloning StationController_Py into $installDir..."
    if (Test-Path (Join-Path $installDir ".git")) {
        Warn "Directory already exists - pulling latest changes instead."
        git -C $installDir pull --ff-only
    } else {
        git clone $REPO_URL $installDir
    }

    $devArg = if ($Dev) { @('-Dev') } else { @() }
    & (Join-Path $installDir "install.ps1") @devArg
    exit $LASTEXITCODE
}

Set-Location $SCRIPT_DIR

# -- 1. Python --------------------------------------------------------------
Info "Checking Python version..."

$PYTHON = $null
foreach ($candidate in @('python', 'python3', 'py')) {
    try {
        $verLine = (& $candidate --version 2>&1) | ForEach-Object { "$_" } | Where-Object { $_ } | Select-Object -First 1
        if ($LASTEXITCODE -ne 0) { continue }
        if ($verLine -match 'Python\s+(\d+)\.(\d+)') {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 11)) {
                $PYTHON = $candidate
                break
            }
        }
    } catch { }
}

if (-not $PYTHON) {
    Die "Python 3.11+ is required. Download from https://www.python.org/downloads/"
}
$pyVerDisplay = (& $PYTHON --version 2>&1) | ForEach-Object { "$_" } | Select-Object -First 1
Write-Host "  Using: $PYTHON ($pyVerDisplay)"

# -- 2. Virtual environment -------------------------------------------------
$VENV        = Join-Path $SCRIPT_DIR ".venv"
$PIP         = Join-Path $VENV "Scripts\pip.exe"
$PYTHON_VENV = Join-Path $VENV "Scripts\python.exe"

if (-not (Test-Path $VENV)) {
    Info "Creating virtual environment at .venv..."
    & $PYTHON -m venv $VENV
} else {
    Info "Virtual environment already exists - skipping creation."
}

# -- 3. Python dependencies -------------------------------------------------
Info "Installing Python dependencies..."
& $PIP install --upgrade pip --quiet
& $PIP install -r requirements.txt --quiet

if ($Dev) {
    Info "Installing dev dependencies..."
    & $PIP install -r requirements-dev.txt --quiet
}

# -- 4. Node.js / UI --------------------------------------------------------
if (Test-Path (Join-Path $SCRIPT_DIR "ui")) {
    Info "Checking Node.js..."

    $nodeOk     = $false
    $nodeVerInt = 0
    $nodeVerStr = ""
    try {
        $nodeVerStr = (node -e "process.stdout.write(String(process.version.slice(1).split('.')[0]))" 2>&1) |
                      ForEach-Object { "$_" } | Select-Object -First 1
        if ($LASTEXITCODE -eq 0) {
            $nodeVerInt = [int]$nodeVerStr
            $nodeOk     = $true
        }
    } catch { }

    if (-not $nodeOk) {
        Warn "Node.js not found - skipping UI install."
        Warn "Install Node.js LTS from https://nodejs.org and re-run."
    } else {
        if ($nodeVerInt -lt 18) {
            Warn "Node.js $nodeVerStr detected - version 18+ is recommended."
        } else {
            Write-Host "  Using: node v$nodeVerStr / npm $(npm --version)"
        }

        Info "Installing UI dependencies..."
        npm --prefix (Join-Path $SCRIPT_DIR "ui") ci --silent

        Info "Building UI..."
        npm --prefix (Join-Path $SCRIPT_DIR "ui") run build --silent
        Write-Host "  UI built -> ui\dist\"
    }
}

# -- 5. Data directory ------------------------------------------------------
Info "Creating data directory..."
New-Item -ItemType Directory -Force -Path (Join-Path $SCRIPT_DIR "data") | Out-Null

# -- 6. Database migrations -------------------------------------------------
Info "Running database migrations..."

@'
import pathlib, yaml
cfg_path = pathlib.Path("config/telemetry_config.yaml")
default_url = "sqlite+aiosqlite:///data/station.db"
if cfg_path.exists():
    raw = yaml.safe_load(cfg_path.read_text()) or {}
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
'@ | & $PYTHON_VENV -

# -- 7. COM port configuration ----------------------------------------------
$COMMS_CFG = Join-Path $SCRIPT_DIR "config" "comms_config.yaml"

if (Test-Path $COMMS_CFG) {
    Info "Scanning for serial (COM) ports..."

    $comPorts = @(
        Get-PnpDevice -Class Ports -Status OK -ErrorAction SilentlyContinue |
            Where-Object { $_.FriendlyName -match 'COM\d+' } |
            ForEach-Object {
                if ($_.FriendlyName -match '\(COM(\d+)\)') {
                    [PSCustomObject]@{
                        Port        = "COM$($Matches[1])"
                        Description = $_.FriendlyName
                    }
                }
            } |
            Sort-Object { [int]($_.Port -replace 'COM', '') }
    )

    if ($comPorts.Count -eq 0) {
        Warn "No COM ports detected - skipping port configuration."
        Warn "Plug in your USB adapter and re-run, or edit config\comms_config.yaml manually."
    } else {
        Write-Host ""
        Write-Host "  Available COM ports:"
        Write-Host ""
        for ($i = 0; $i -lt $comPorts.Count; $i++) {
            Write-Host ("    [{0}] {1}" -f ($i + 1), $comPorts[$i].Description)
        }
        Write-Host "    [0] Skip - keep existing config"
        Write-Host ""

        # Find active rs485 transports
        $transports = @(
            @'
import sys, yaml, pathlib
cfg = yaml.safe_load(pathlib.Path(sys.argv[1]).read_text()) or {}
for bus in cfg.get("buses", []):
    for t in bus.get("transports", []):
        if t.get("type") == "rs485":
            print(f"{t['name']}|{t.get('port','')}|{bus['name']}|{t.get('baud_rate', 9600)}")
'@ | & $PYTHON_VENV - $COMMS_CFG
        ) | Where-Object { $_ -match '\|' }

        if ($transports.Count -eq 0) {
            Warn "No active rs485 transports found in comms_config.yaml."
        } else {
            $choices = @{}

            foreach ($line in $transports) {
                $parts       = $line -split '\|'
                $tName       = $parts[0]
                $currentPort = $parts[1]
                $busName     = $parts[2]
                $baudRate    = [int]$parts[3]

                if ($baudRate -eq 115200) {
                    $speedLabel = "High-speed / power meter (115200 baud)"
                    $speedColor = 'Yellow'
                    $speedNote  = "Use a dedicated USB adapter - do not share with control traffic."
                } else {
                    $speedLabel = "Standard DCN ($baudRate baud)"
                    $speedColor = 'White'
                    $speedNote  = ""
                }

                Write-Host "  Bus " -NoNewline
                Write-Host $busName -ForegroundColor Cyan -NoNewline
                Write-Host " - transport " -NoNewline
                Write-Host $tName -ForegroundColor Cyan -NoNewline
                Write-Host " - " -NoNewline
                Write-Host $speedLabel -ForegroundColor $speedColor
                if ($speedNote) { Warn $speedNote }
                Write-Host "  Currently: $currentPort"

                Prompt "Select port number (0 to skip):"
                $choice = Read-Host

                if ($choice -match '^\d+$') {
                    $idx = [int]$choice
                    if ($idx -ge 1 -and $idx -le $comPorts.Count) {
                        $chosen          = $comPorts[$idx - 1].Port
                        $choices[$tName] = $chosen
                        Write-Host "    -> $chosen"
                    } else {
                        Write-Host "    -> skipped"
                    }
                } else {
                    Write-Host "    -> skipped"
                }
                Write-Host ""
            }

            # Patch comms_config.yaml with chosen ports
            if ($choices.Count -gt 0) {
                $patchArgs = @($COMMS_CFG) + @(
                    $choices.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }
                )

                @'
import sys, re, pathlib
cfg_path = pathlib.Path(sys.argv[1])
assignments = {}
for arg in sys.argv[2:]:
    name, _, port = arg.partition("=")
    assignments[name] = port
text = cfg_path.read_text()
lines = text.splitlines(keepends=True)
result = []
current_transport = None
in_transport = False
for line in lines:
    m_name = re.match(r"^(\s*)-\s+name:\s+(\S+)", line)
    if m_name:
        current_transport = m_name.group(2)
        in_transport = True
        result.append(line)
        continue
    if in_transport:
        m_key = re.match(r"^(\s+)\w", line)
        if not line.strip() or (m_key and len(m_key.group(1)) <= 2 and not line.lstrip().startswith("-")):
            in_transport = False
            current_transport = None
    if in_transport and current_transport in assignments:
        m_port = re.match(r"^(\s+port:\s*)(\S+)(.*)", line)
        if m_port:
            new_port = assignments[current_transport]
            line = f"{m_port.group(1)}{new_port}\n"
    result.append(line)
cfg_path.write_text("".join(result))
print(f"  Updated {cfg_path}")
'@ | & $PYTHON_VENV - @patchArgs
            }
        }
    }
}

# -- 8. Simulator setup (dev branches only) ---------------------------------
$SimReady = $false
$simDir = Join-Path $SCRIPT_DIR "simulator"
if (Test-Path $simDir) {
    $branch = (git -C $SCRIPT_DIR branch --show-current 2>&1 |
               ForEach-Object { "$_" } | Where-Object { $_ } | Select-Object -First 1)
    if (-not $branch) {
        $branch = (git -C $SCRIPT_DIR rev-parse --abbrev-ref HEAD 2>&1 |
                   ForEach-Object { "$_" } | Where-Object { $_ } | Select-Object -First 1)
    }
    if ($branch -and $branch -ne 'main') {
        $simCfg = Join-Path $simDir "sim_config.yaml"
        Write-Host ""
        Info "DCN simulator available (branch: $branch)"
        Prompt "Set up simulator for testing? [y/N]:"
        $simChoice = Read-Host
        if ($simChoice -match '^[Yy]$') {

@'
import sys, yaml, pathlib

comms_path = pathlib.Path(sys.argv[1])
sim_path   = pathlib.Path(sys.argv[2])

sim = yaml.safe_load(sim_path.read_text()) or {}

if not comms_path.exists():
    print("  comms_config.yaml not found — simulator will use defaults")
    sys.exit(0)

comms = yaml.safe_load(comms_path.read_text()) or {}

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
    print("  No nodered_mqtt transport found — using defaults (localhost:1883)")

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

sim_path.write_text(yaml.dump(sim, default_flow_style=False, sort_keys=False))
print(f"  Written -> {sim_path}")
'@ | & $PYTHON_VENV - $COMMS_CFG $simCfg

            $SimReady = $true
        } else {
            Write-Host "    -> skipped"
        }
    }
}

# -- Done -------------------------------------------------------------------
Write-Host ""
Write-Host "Installation complete." -ForegroundColor Green
Write-Host ""
Write-Host "  Start the server:  .venv\Scripts\python main.py"
if (Test-Path (Join-Path $SCRIPT_DIR "ui\dist")) {
    Write-Host "  UI available at:   http://localhost:8080"
}
if ($SimReady) {
    Write-Host "  Run simulator:     .venv\Scripts\python -m simulator"
}
Write-Host ""
if ($Dev) {
    Write-Host "  Run tests:         .venv\Scripts\pytest"
    Write-Host "  UI tests:          npm --prefix ui test"
    Write-Host ""
}
