#!/usr/bin/env bats
# Tests for the bash logic in install.sh.
#
# Requires bats-core >= 1.5:
#   sudo apt install bats
#   OR: https://github.com/bats-core/bats-core
#
# Run:
#   bats tests/test_install.bats

INSTALL_SH="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)/install.sh"

# ---------------------------------------------------------------------------
# Syntax
# ---------------------------------------------------------------------------

@test "install.sh passes bash syntax check" {
    run bash -n "$INSTALL_SH"
    [ "$status" -eq 0 ]
}

# ---------------------------------------------------------------------------
# --dev flag parsing  (lines 13-16 of install.sh)
# ---------------------------------------------------------------------------

_parse_dev_flag() {
    bash -c '
        DEV=0
        for arg in "$@"; do [[ "$arg" == "--dev" ]] && DEV=1; done
        echo "$DEV"
    ' -- "$@"
}

@test "--dev flag sets DEV=1" {
    run _parse_dev_flag --dev
    [ "$status" -eq 0 ]
    [ "$output" = "1" ]
}

@test "no --dev flag leaves DEV=0" {
    run _parse_dev_flag
    [ "$status" -eq 0 ]
    [ "$output" = "0" ]
}

@test "other flags do not set DEV=1" {
    run _parse_dev_flag --verbose --quiet
    [ "$output" = "0" ]
}

@test "--dev anywhere in argument list is recognised" {
    run _parse_dev_flag --verbose --dev --quiet
    [ "$output" = "1" ]
}

# ---------------------------------------------------------------------------
# Baud-rate label logic  (while-loop body, lines 232-238)
# ---------------------------------------------------------------------------

_speed_label() {
    # $1 = baud_rate integer
    bash -c '
        baud_rate="$1"
        bold="" yellow="" reset=""
        if [[ "$baud_rate" -eq 115200 ]]; then
            speed_label="High-speed / power meter (115200 baud)"
            speed_note="Use a dedicated USB adapter — do not share with control traffic."
        else
            speed_label="Standard DCN (${baud_rate} baud)"
            speed_note=""
        fi
        echo "label:$speed_label"
        echo "note:$speed_note"
    ' -- "$1"
}

@test "9600 baud shows Standard DCN label" {
    run _speed_label 9600
    [[ "$output" == *"label:Standard DCN (9600 baud)"* ]]
}

@test "115200 baud shows High-speed label" {
    run _speed_label 115200
    [[ "$output" == *"label:High-speed / power meter (115200 baud)"* ]]
}

@test "115200 baud shows dedicated adapter warning" {
    run _speed_label 115200
    [[ "$output" == *"dedicated USB adapter"* ]]
}

@test "9600 baud shows no dedicated adapter warning" {
    run _speed_label 9600
    [[ "$output" != *"dedicated USB adapter"* ]]
}

@test "19200 baud shows Standard DCN with correct rate" {
    run _speed_label 19200
    [[ "$output" == *"Standard DCN (19200 baud)"* ]]
}

@test "19200 baud shows no dedicated adapter warning" {
    run _speed_label 19200
    [[ "$output" != *"dedicated USB adapter"* ]]
}

# ---------------------------------------------------------------------------
# Port list display  (lines 204-211)
# ---------------------------------------------------------------------------

_display_port_list() {
    # $@ = port description lines (one per arg)
    bash -c '
        bold="" reset=""
        PORT_LIST="$(printf "%s\n" "$@")"
        mapfile -t PORTS < <(echo "$PORT_LIST" | awk "{print \$1}")
        mapfile -t DESCS < <(echo "$PORT_LIST")
        for i in "${!DESCS[@]}"; do
            printf "[%d] %s\n" "$((i+1))" "${DESCS[$i]}"
        done
        printf "[0] Skip — keep existing config\n"
    ' -- "$@"
}

@test "port list is numbered starting from 1" {
    run _display_port_list "/dev/ttyUSB0" "/dev/ttyUSB1"
    [[ "$output" == *"[1] /dev/ttyUSB0"* ]]
    [[ "$output" == *"[2] /dev/ttyUSB1"* ]]
}

@test "port list includes [0] Skip option" {
    run _display_port_list "/dev/ttyUSB0"
    [[ "$output" == *"[0] Skip"* ]]
}

@test "single port listed as [1]" {
    run _display_port_list "/dev/ttyAMA0"
    [[ "$output" == *"[1] /dev/ttyAMA0"* ]]
}

@test "port description is shown alongside device path" {
    run _display_port_list "/dev/ttyUSB0 — FTDI FT232R [A1B2C3]"
    [[ "$output" == *"FTDI FT232R [A1B2C3]"* ]]
}

@test "three ports numbered 1 2 3" {
    run _display_port_list "/dev/ttyUSB0" "/dev/ttyUSB1" "/dev/ttyACM0"
    [[ "$output" == *"[1]"* ]]
    [[ "$output" == *"[2]"* ]]
    [[ "$output" == *"[3]"* ]]
}

# ---------------------------------------------------------------------------
# Choice validation  (lines 245-253)
# ---------------------------------------------------------------------------

_validate_choice() {
    # $1 = choice string, $2 = number of available ports
    bash -c '
        choice="$1"
        num_ports="$2"
        PORTS=()
        for ((i=1; i<=num_ports; i++)); do PORTS+=("/dev/ttyUSB$((i-1))"); done
        if [[ "$choice" =~ ^[1-9][0-9]*$ ]] && \
           [[ "$choice" -ge 1 ]] && \
           [[ "$choice" -le "${#PORTS[@]}" ]]; then
            echo "selected:${PORTS[$((choice-1))]}"
        else
            echo "skipped"
        fi
    ' -- "$1" "$2"
}

@test "choice 1 selects first port" {
    run _validate_choice 1 2
    [ "$output" = "selected:/dev/ttyUSB0" ]
}

@test "choice 2 selects second port" {
    run _validate_choice 2 2
    [ "$output" = "selected:/dev/ttyUSB1" ]
}

@test "choice 0 is skipped" {
    run _validate_choice 0 2
    [ "$output" = "skipped" ]
}

@test "choice out of range is skipped" {
    run _validate_choice 5 2
    [ "$output" = "skipped" ]
}

@test "non-numeric choice is skipped" {
    run _validate_choice "abc" 2
    [ "$output" = "skipped" ]
}

@test "empty choice is skipped" {
    run _validate_choice "" 2
    [ "$output" = "skipped" ]
}

@test "negative choice is skipped" {
    run _validate_choice "-1" 2
    [ "$output" = "skipped" ]
}

@test "choice exactly equal to port count is valid" {
    run _validate_choice 3 3
    [ "$output" = "selected:/dev/ttyUSB2" ]
}
