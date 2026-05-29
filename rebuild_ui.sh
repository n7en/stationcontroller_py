#!/usr/bin/env bash
# Rebuild the Station Controller UI without running a full install.
# Requires that `npm install` has already been run in the ui/ directory.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-.}")" 2>/dev/null && pwd || echo "$PWD")"
UI_DIR="$SCRIPT_DIR/ui"

bold=$(tput bold 2>/dev/null || true)
green=$(tput setaf 2 2>/dev/null || true)
yellow=$(tput setaf 3 2>/dev/null || true)
red=$(tput setaf 1 2>/dev/null || true)
reset=$(tput sgr0 2>/dev/null || true)

info() { echo "${bold}${green}==>${reset} $*"; }
warn() { echo "${bold}${yellow}  ! ${reset} $*"; }
die()  { echo "${bold}${red}error:${reset} $*" >&2; exit 1; }

[[ -d "$UI_DIR" ]] || die "ui/ directory not found at $UI_DIR"

if [[ ! -d "$UI_DIR/node_modules" ]]; then
    die "ui/node_modules not found -- run ./install.sh first to install dependencies"
fi

info "Building UI..."
npm --prefix "$UI_DIR" run build

info "Done -- ui_dist/ is up to date"
