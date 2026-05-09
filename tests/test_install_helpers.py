"""
Tests for the Python logic embedded in install.sh.

Each helper function below is a faithful copy of the corresponding heredoc
snippet in install.sh.  Tests validate the logic directly without shelling
out, so they run on any platform and don't require the venv to exist.

If install.sh changes its embedded Python, update the matching helper here.
"""
import re
import textwrap

import pytest
import yaml


# ---------------------------------------------------------------------------
# Helper: port description building (port-discovery heredoc)
# ---------------------------------------------------------------------------

def describe_port(dev: str, udev_props: dict) -> str:
    """Mirrors the per-port description logic in the port-discovery heredoc."""
    vendor = udev_props.get("ID_VENDOR", "")
    model  = udev_props.get("ID_MODEL", "")
    serial = udev_props.get("ID_SERIAL_SHORT", "")
    parts  = [p for p in [vendor, model] if p]
    desc   = " - " + " ".join(parts) if parts else ""
    if serial:
        desc += f" [{serial}]"
    return f"{dev}{desc}"


class TestDescribePort:

    def test_vendor_and_model(self):
        assert describe_port("/dev/ttyUSB0", {"ID_VENDOR": "FTDI", "ID_MODEL": "FT232R"}) \
            == "/dev/ttyUSB0 - FTDI FT232R"

    def test_vendor_only(self):
        assert describe_port("/dev/ttyUSB0", {"ID_VENDOR": "Silicon_Labs"}) \
            == "/dev/ttyUSB0 - Silicon_Labs"

    def test_model_only(self):
        assert describe_port("/dev/ttyUSB0", {"ID_MODEL": "CP2102"}) \
            == "/dev/ttyUSB0 - CP2102"

    def test_vendor_model_and_serial(self):
        assert describe_port(
            "/dev/ttyUSB0",
            {"ID_VENDOR": "FTDI", "ID_MODEL": "FT232R", "ID_SERIAL_SHORT": "A10KXYZ1"},
        ) == "/dev/ttyUSB0 - FTDI FT232R [A10KXYZ1]"

    def test_no_udev_info_returns_bare_path(self):
        assert describe_port("/dev/ttyAMA0", {}) == "/dev/ttyAMA0"

    def test_serial_without_vendor_or_model(self):
        assert describe_port("/dev/ttyUSB0", {"ID_SERIAL_SHORT": "ABC123"}) \
            == "/dev/ttyUSB0 [ABC123]"

    def test_different_device_paths(self):
        assert describe_port("/dev/ttyACM0", {"ID_VENDOR": "Arduino"}) \
            == "/dev/ttyACM0 - Arduino"
        assert describe_port("/dev/rfcomm0", {}) == "/dev/rfcomm0"


# ---------------------------------------------------------------------------
# Helper: transport extraction (TRANSPORTS heredoc)
# ---------------------------------------------------------------------------

def extract_transports(config_text: str) -> list[tuple[str, str, str, int]]:
    """Mirrors the PYEOF snippet that lists active rs485 transports.

    Returns list of (transport_name, current_port, bus_name, baud_rate).
    """
    cfg = yaml.safe_load(config_text) or {}
    result = []
    for bus in cfg.get("buses", []):
        for t in bus.get("transports", []):
            if t.get("type") == "rs485":
                result.append((
                    t["name"],
                    t.get("port", ""),
                    bus["name"],
                    int(t.get("baud_rate", 9600)),
                ))
    return result


class TestExtractTransports:

    def test_single_rs485_transport(self):
        cfg = textwrap.dedent("""\
            buses:
              - name: control
                transports:
                  - name: ctrl_serial
                    type: rs485
                    port: /dev/ttyUSB0
                    baud_rate: 9600
        """)
        assert extract_transports(cfg) == [("ctrl_serial", "/dev/ttyUSB0", "control", 9600)]

    def test_skips_nodered_mqtt_transport(self):
        cfg = textwrap.dedent("""\
            buses:
              - name: control
                transports:
                  - name: mqtt_t
                    type: nodered_mqtt
                    broker: localhost
        """)
        assert extract_transports(cfg) == []

    def test_skips_nodered_tcp_transport(self):
        cfg = textwrap.dedent("""\
            buses:
              - name: control
                transports:
                  - name: tcp_t
                    type: nodered_tcp
                    host: 0.0.0.0
                    port: 4880
        """)
        assert extract_transports(cfg) == []

    def test_defaults_baud_rate_to_9600(self):
        cfg = textwrap.dedent("""\
            buses:
              - name: control
                transports:
                  - name: ctrl_serial
                    type: rs485
                    port: /dev/ttyUSB0
        """)
        result = extract_transports(cfg)
        assert result[0][3] == 9600

    def test_preserves_115200_baud_rate(self):
        cfg = textwrap.dedent("""\
            buses:
              - name: power
                transports:
                  - name: pwr_serial
                    type: rs485
                    port: /dev/ttyUSB1
                    baud_rate: 115200
        """)
        result = extract_transports(cfg)
        assert result[0][3] == 115200

    def test_multiple_buses_all_extracted(self):
        cfg = textwrap.dedent("""\
            buses:
              - name: control
                transports:
                  - name: ctrl_serial
                    type: rs485
                    port: /dev/ttyUSB0
                    baud_rate: 9600
              - name: power
                transports:
                  - name: pwr_serial
                    type: rs485
                    port: /dev/ttyUSB1
                    baud_rate: 115200
        """)
        result = extract_transports(cfg)
        assert len(result) == 2
        names = [r[0] for r in result]
        assert "ctrl_serial" in names
        assert "pwr_serial" in names

    def test_three_buses_all_extracted(self):
        cfg = textwrap.dedent("""\
            buses:
              - name: control
                transports:
                  - name: ctrl
                    type: rs485
                    port: /dev/ttyUSB0
                    baud_rate: 9600
              - name: power
                transports:
                  - name: pwr
                    type: rs485
                    port: /dev/ttyUSB1
                    baud_rate: 115200
              - name: shack2
                transports:
                  - name: shack2_serial
                    type: rs485
                    port: /dev/ttyUSB2
                    baud_rate: 9600
        """)
        result = extract_transports(cfg)
        assert len(result) == 3

    def test_mixed_types_only_rs485_extracted(self):
        cfg = textwrap.dedent("""\
            buses:
              - name: control
                transports:
                  - name: ctrl_serial
                    type: rs485
                    port: /dev/ttyUSB0
                    baud_rate: 9600
                  - name: ctrl_tcp
                    type: nodered_tcp
                    host: 0.0.0.0
                    port: 4880
        """)
        result = extract_transports(cfg)
        assert len(result) == 1
        assert result[0][0] == "ctrl_serial"

    def test_empty_buses_list_returns_empty(self):
        assert extract_transports("buses: []") == []

    def test_no_buses_key_returns_empty(self):
        assert extract_transports("networks: []") == []

    def test_bus_name_and_port_captured_correctly(self):
        cfg = textwrap.dedent("""\
            buses:
              - name: power
                transports:
                  - name: pwr_serial
                    type: rs485
                    port: /dev/ttyUSB3
                    baud_rate: 115200
        """)
        name, port, bus, baud = extract_transports(cfg)[0]
        assert name == "pwr_serial"
        assert port == "/dev/ttyUSB3"
        assert bus  == "power"
        assert baud == 115200


# ---------------------------------------------------------------------------
# Helper: YAML config patching (patch heredoc)
# ---------------------------------------------------------------------------

def patch_ports(config_text: str, assignments: dict[str, str]) -> str:
    """Mirrors the PYEOF patch heredoc in install.sh."""
    lines = config_text.splitlines(keepends=True)
    result = []
    current_transport = None
    in_transport = False

    for line in lines:
        m_name = re.match(r'^(\s*)-\s+name:\s+(\S+)', line)
        if m_name:
            current_transport = m_name.group(2)
            in_transport = True
            result.append(line)
            continue

        if in_transport:
            m_key = re.match(r'^(\s+)\w', line)
            if not line.strip() or (
                m_key and len(m_key.group(1)) <= 2
                and not line.lstrip().startswith('-')
            ):
                in_transport = False
                current_transport = None

        if in_transport and current_transport in assignments:
            m_port = re.match(r'^(\s+port:\s*)(\S+)(.*)', line)
            if m_port:
                new_port = assignments[current_transport]
                line = f"{m_port.group(1)}{new_port}\n"

        result.append(line)

    return "".join(result)


_SINGLE_BUS_CONFIG = textwrap.dedent("""\
    # Station config - comments must survive patching
    buses:
      - name: control
        transports:
          - name: ctrl_serial
            type: rs485
            port: /dev/ttyUSB0      # Linux. Windows example: COM3
            baud_rate: 9600
            description: "Main control DCN"
""")

_MULTI_BUS_CONFIG = textwrap.dedent("""\
    buses:
      - name: control
        transports:
          - name: ctrl_serial
            type: rs485
            port: /dev/ttyUSB0
            baud_rate: 9600
      - name: power
        transports:
          - name: pwr_serial
            type: rs485
            port: /dev/ttyUSB1
            baud_rate: 115200
""")


class TestPatchPorts:

    def test_updates_port_value(self):
        out = patch_ports(_SINGLE_BUS_CONFIG, {"ctrl_serial": "/dev/ttyUSB2"})
        assert "port: /dev/ttyUSB2" in out

    def test_old_port_no_longer_present(self):
        out = patch_ports(_SINGLE_BUS_CONFIG, {"ctrl_serial": "/dev/ttyUSB2"})
        assert "/dev/ttyUSB0" not in out

    def test_preserves_header_comment(self):
        out = patch_ports(_SINGLE_BUS_CONFIG, {"ctrl_serial": "/dev/ttyUSB2"})
        assert "# Station config" in out

    def test_preserves_baud_rate_field(self):
        out = patch_ports(_SINGLE_BUS_CONFIG, {"ctrl_serial": "/dev/ttyUSB2"})
        assert "baud_rate: 9600" in out

    def test_preserves_description_field(self):
        out = patch_ports(_SINGLE_BUS_CONFIG, {"ctrl_serial": "/dev/ttyUSB2"})
        assert 'description: "Main control DCN"' in out

    def test_inline_comment_on_port_line_is_dropped(self):
        # The patcher intentionally drops the trailing comment on the port line
        # when replacing the value - all other lines are untouched.
        out = patch_ports(_SINGLE_BUS_CONFIG, {"ctrl_serial": "/dev/ttyUSB2"})
        assert "Windows example" not in out

    def test_unknown_transport_name_is_noop(self):
        out = patch_ports(_SINGLE_BUS_CONFIG, {"nonexistent": "/dev/ttyUSB9"})
        assert "/dev/ttyUSB0" in out
        assert "/dev/ttyUSB9" not in out

    def test_empty_assignments_leaves_config_unchanged(self):
        assert patch_ports(_SINGLE_BUS_CONFIG, {}) == _SINGLE_BUS_CONFIG

    def test_patches_only_the_named_transport(self):
        out = patch_ports(_MULTI_BUS_CONFIG, {"ctrl_serial": "/dev/ttyUSB5"})
        assert "port: /dev/ttyUSB5" in out    # ctrl updated
        assert "port: /dev/ttyUSB1" in out    # power unchanged

    def test_patches_both_transports_in_one_pass(self):
        out = patch_ports(_MULTI_BUS_CONFIG, {
            "ctrl_serial": "/dev/ttyUSB5",
            "pwr_serial":  "/dev/ttyUSB6",
        })
        assert "port: /dev/ttyUSB5" in out
        assert "port: /dev/ttyUSB6" in out

    def test_patched_output_is_valid_yaml(self):
        out = patch_ports(_SINGLE_BUS_CONFIG, {"ctrl_serial": "/dev/ttyUSB3"})
        parsed = yaml.safe_load(out)
        port = parsed["buses"][0]["transports"][0]["port"]
        assert port == "/dev/ttyUSB3"

    def test_multi_bus_patch_yields_valid_yaml(self):
        out = patch_ports(_MULTI_BUS_CONFIG, {
            "ctrl_serial": "/dev/ttyUSB5",
            "pwr_serial":  "/dev/ttyUSB6",
        })
        parsed = yaml.safe_load(out)
        ports = [
            t["port"]
            for bus in parsed["buses"]
            for t in bus["transports"]
        ]
        assert "/dev/ttyUSB5" in ports
        assert "/dev/ttyUSB6" in ports

    def test_windows_com_port(self):
        out = patch_ports(_SINGLE_BUS_CONFIG, {"ctrl_serial": "COM5"})
        assert "port: COM5" in out
        assert yaml.safe_load(out)["buses"][0]["transports"][0]["port"] == "COM5"

    def test_three_buses_each_patched_independently(self):
        cfg = textwrap.dedent("""\
            buses:
              - name: control
                transports:
                  - name: ctrl
                    type: rs485
                    port: /dev/ttyUSB0
                    baud_rate: 9600
              - name: power
                transports:
                  - name: pwr
                    type: rs485
                    port: /dev/ttyUSB1
                    baud_rate: 115200
              - name: shack2
                transports:
                  - name: shack2
                    type: rs485
                    port: /dev/ttyUSB2
                    baud_rate: 9600
        """)
        out = patch_ports(cfg, {"ctrl": "/dev/ttyUSB7", "pwr": "/dev/ttyUSB8"})
        parsed = yaml.safe_load(out)
        ports = {
            t["name"]: t["port"]
            for bus in parsed["buses"]
            for t in bus["transports"]
        }
        assert ports["ctrl"]   == "/dev/ttyUSB7"
        assert ports["pwr"]    == "/dev/ttyUSB8"
        assert ports["shack2"] == "/dev/ttyUSB2"  # untouched
