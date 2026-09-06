#Requires -Version 5.1
<#
.SYNOPSIS
    Rebuild the Station Controller UI without running a full install.

.DESCRIPTION
    Runs `npm run build` inside the ui/ directory to regenerate ui_dist/.
    Requires that the full install has been run at least once so that
    node_modules/ is already present.

.EXAMPLE
    .\rebuild_ui.ps1
#>

$ErrorActionPreference = 'Stop'

$SCRIPT_DIR = if ($PSScriptRoot) { $PSScriptRoot } else { $PWD.Path }
$UI_DIR     = Join-Path $SCRIPT_DIR 'ui'

function Info { param($msg) Write-Host "==> $msg" -ForegroundColor Green }
function Die  { param($msg) Write-Host "error: $msg" -ForegroundColor Red; exit 1 }

if (-not (Test-Path $UI_DIR)) {
    Die "ui/ directory not found at $UI_DIR"
}

if (-not (Test-Path (Join-Path $UI_DIR 'node_modules'))) {
    Die "ui\node_modules not found — run .\install.ps1 first to install dependencies"
}

Info "Building UI..."
Push-Location $UI_DIR
try {
    npm run build
} finally {
    Pop-Location
}

Info "Done — ui_dist\ is up to date"
