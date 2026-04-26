#!/usr/bin/env bash
# start.sh — start StationController
#
# Usage:
#   ./start.sh          # production: serve pre-built UI on port 8080
#   ./start.sh --dev    # development: Vite dev server (port 5173) + Python backend
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

DEV=false
for arg in "$@"; do
  [[ "$arg" == "--dev" ]] && DEV=true
done

# ── Activate virtualenv if present ──────────────────────────────────────────
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# ── Production mode ──────────────────────────────────────────────────────────
if [[ "$DEV" == false ]]; then
  # Build the frontend if it hasn't been built yet
  if [[ ! -f "ui_dist/index.html" ]]; then
    echo "ui_dist not found — building frontend..."
    cd ui
    npm install --silent
    npm run build
    cd "$SCRIPT_DIR"
  fi

  echo "Starting StationController on http://0.0.0.0:8080"
  exec python main.py
fi

# ── Development mode ─────────────────────────────────────────────────────────
echo "Starting in dev mode — backend on :8080, Vite on :5173"
echo "Open http://localhost:5173 in your browser"
echo "Press Ctrl+C to stop both processes."
echo ""

# Start Python backend in the background
python main.py &
BACKEND_PID=$!

# Start Vite dev server in the foreground (inside ui/)
cd ui
npm install --silent
npm run dev &
VITE_PID=$!
cd "$SCRIPT_DIR"

# Trap Ctrl+C and clean up both processes
cleanup() {
  echo ""
  echo "Shutting down..."
  kill "$VITE_PID"  2>/dev/null || true
  kill "$BACKEND_PID" 2>/dev/null || true
  wait "$VITE_PID"    2>/dev/null || true
  wait "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup INT TERM

# Wait for either process to exit
wait "$BACKEND_PID" "$VITE_PID"
