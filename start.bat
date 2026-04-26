@echo off
:: start.bat — start StationController on Windows
::
:: Usage:
::   start.bat          production mode: serve pre-built UI on port 8080
::   start.bat --dev    dev mode: Vite dev server (port 5173) + Python backend
::
setlocal

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: ── Activate virtualenv if present ─────────────────────────────────────────
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

:: ── Check for --dev flag ────────────────────────────────────────────────────
set DEV=false
for %%A in (%*) do (
    if "%%A"=="--dev" set DEV=true
)

:: ── Production mode ─────────────────────────────────────────────────────────
if "%DEV%"=="false" (
    if not exist "ui_dist\index.html" (
        echo ui_dist not found -- building frontend...
        cd ui
        call npm install --silent
        call npm run build
        cd /d "%SCRIPT_DIR%"
    )
    echo Starting StationController on http://localhost:8080
    python main.py
    goto :eof
)

:: ── Development mode ─────────────────────────────────────────────────────────
echo Starting in dev mode -- backend on :8080, Vite on :5173
echo Open http://localhost:5173 in your browser
echo Close this window or press Ctrl+C to stop.
echo.

cd ui
call npm install --silent
cd /d "%SCRIPT_DIR%"

:: Start Vite in a separate window
start "StationController Vite" cmd /c "cd /d "%SCRIPT_DIR%\ui" && npm run dev"

:: Run Python backend in this window (Ctrl+C stops it; Vite window stays open)
python main.py

endlocal
