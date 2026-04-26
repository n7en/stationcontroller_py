"""Tests for main.py startup utilities and the full startup sequence."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

import main as m
from main import _read_db_url, _run_migrations


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_api_state():
    """Reset the module-level AppState singleton between tests."""
    from api.deps import _state
    yield
    for attr in vars(_state):
        setattr(_state, attr, None)


@pytest.fixture
def cfg_dir(tmp_path):
    """Temporary config directory with the five config paths redirected."""
    for attr in ("COMMS_CFG", "RADIO_CFG", "AUTOMATION_CFG", "TELEMETRY_CFG", "LABELS_CFG"):
        monkeypatch_attr(m, attr, tmp_path / f"{attr}.yaml")
    m_DATA_orig = m.DATA
    m.DATA = tmp_path / "data"
    yield tmp_path
    m.DATA = m_DATA_orig
    # restore config paths
    for attr in ("COMMS_CFG", "RADIO_CFG", "AUTOMATION_CFG", "TELEMETRY_CFG", "LABELS_CFG"):
        setattr(m, attr, Path("config") / {
            "COMMS_CFG": "comms_config.yaml",
            "RADIO_CFG": "radio_config.yaml",
            "AUTOMATION_CFG": "automation_config.yaml",
            "TELEMETRY_CFG": "telemetry_config.yaml",
            "LABELS_CFG": "labels.yaml",
        }[attr])


def monkeypatch_attr(obj, attr, value):
    setattr(obj, attr, value)


# ---------------------------------------------------------------------------
# _read_db_url
# ---------------------------------------------------------------------------

class TestReadDbUrl:

    def test_returns_default_when_file_missing(self, tmp_path):
        m.TELEMETRY_CFG = tmp_path / "nonexistent.yaml"
        assert _read_db_url() == "sqlite+aiosqlite:///data/station.db"

    def test_reads_url_from_config(self, tmp_path):
        cfg = tmp_path / "telemetry_config.yaml"
        cfg.write_text(
            "telemetry:\n  database:\n    url: sqlite+aiosqlite:///custom/path.db\n",
            encoding="utf-8",
        )
        m.TELEMETRY_CFG = cfg
        assert _read_db_url() == "sqlite+aiosqlite:///custom/path.db"

    def test_falls_back_to_default_when_url_key_absent(self, tmp_path):
        cfg = tmp_path / "telemetry_config.yaml"
        cfg.write_text("telemetry:\n  enabled: true\n", encoding="utf-8")
        m.TELEMETRY_CFG = cfg
        assert _read_db_url() == "sqlite+aiosqlite:///data/station.db"

    def test_falls_back_when_telemetry_section_absent(self, tmp_path):
        cfg = tmp_path / "telemetry_config.yaml"
        cfg.write_text("other_section:\n  key: value\n", encoding="utf-8")
        m.TELEMETRY_CFG = cfg
        assert _read_db_url() == "sqlite+aiosqlite:///data/station.db"


# ---------------------------------------------------------------------------
# _run_migrations
# ---------------------------------------------------------------------------

class TestRunMigrations:

    def test_creates_data_directory(self, tmp_path):
        data_dir = tmp_path / "data"
        m.DATA = data_dir
        assert not data_dir.exists()

        with patch("alembic.command.upgrade"), \
             patch("alembic.config.Config"):
            _run_migrations("sqlite:///data/station.db")

        assert data_dir.exists()

    def test_calls_alembic_upgrade_head(self, tmp_path):
        m.DATA = tmp_path / "data"
        with patch("alembic.command.upgrade") as mock_upgrade, \
             patch("alembic.config.Config") as MockCfg:
            instance = MockCfg.return_value
            _run_migrations("sqlite:///data/station.db")

        mock_upgrade.assert_called_once_with(instance, "head")

    def test_strips_aiosqlite_prefix_from_url(self, tmp_path):
        m.DATA = tmp_path / "data"
        captured = {}

        with patch("alembic.command.upgrade"), \
             patch("alembic.config.Config") as MockCfg:
            instance = MockCfg.return_value
            instance.set_main_option = MagicMock(side_effect=lambda k, v: captured.update({k: v}))
            _run_migrations("sqlite+aiosqlite:///data/station.db")

        assert "sqlalchemy.url" in captured
        assert "aiosqlite" not in captured["sqlalchemy.url"]
        assert captured["sqlalchemy.url"] == "sqlite:///data/station.db"


# ---------------------------------------------------------------------------
# main() startup
# ---------------------------------------------------------------------------

class TestMainStartup:

    @pytest.fixture
    def no_config(self, tmp_path):
        """All config paths point to nonexistent tmp files — no hardware."""
        originals = {}
        for attr in ("COMMS_CFG", "RADIO_CFG", "AUTOMATION_CFG", "TELEMETRY_CFG", "LABELS_CFG"):
            originals[attr] = getattr(m, attr)
            setattr(m, attr, tmp_path / f"{attr}.yaml")
        orig_data = m.DATA
        m.DATA = tmp_path / "data"
        yield tmp_path
        for attr, val in originals.items():
            setattr(m, attr, val)
        m.DATA = orig_data

    async def test_completes_gracefully_with_no_config_files(self, no_config):
        with patch("uvicorn.Server.serve", AsyncMock()), \
             patch("main._run_migrations"):
            await m.main()   # must not raise

    async def test_sensor_registry_is_populated_in_app_state(self, no_config):
        from api.deps import _state
        with patch("uvicorn.Server.serve", AsyncMock()), \
             patch("main._run_migrations"):
            await m.main()
        assert _state.sensor_registry is not None

    async def test_label_registry_is_populated_in_app_state(self, no_config):
        from api.deps import _state
        with patch("uvicorn.Server.serve", AsyncMock()), \
             patch("main._run_migrations"):
            await m.main()
        assert _state.label_registry is not None

    async def test_labels_yaml_loaded_when_present(self, tmp_path, no_config):
        labels_path = tmp_path / "LABELS_CFG.yaml"
        labels_path.write_text(
            "labels:\n  coax_port_1: '20m Yagi'\n  coax_port_2: '40m Dipole'\n",
            encoding="utf-8",
        )
        m.LABELS_CFG = labels_path

        from api.deps import _state
        with patch("uvicorn.Server.serve", AsyncMock()), \
             patch("main._run_migrations"):
            await m.main()

        assert _state.label_registry.label_for("coax_port_1") == "20m Yagi"
        assert _state.label_registry.label_for("coax_port_2") == "40m Dipole"

    async def test_control_network_is_none_without_comms_config(self, no_config):
        from api.deps import _state
        with patch("uvicorn.Server.serve", AsyncMock()), \
             patch("main._run_migrations"):
            await m.main()
        assert _state.control_network is None

    async def test_radio_interface_is_none_without_radio_config(self, no_config):
        from api.deps import _state
        with patch("uvicorn.Server.serve", AsyncMock()), \
             patch("main._run_migrations"):
            await m.main()
        assert _state.radio_interface is None

    async def test_automation_engine_is_none_without_automation_config(self, no_config):
        from api.deps import _state
        with patch("uvicorn.Server.serve", AsyncMock()), \
             patch("main._run_migrations"):
            await m.main()
        assert _state.engine is None

    async def test_telemetry_is_none_without_telemetry_config(self, no_config):
        from api.deps import _state
        with patch("uvicorn.Server.serve", AsyncMock()), \
             patch("main._run_migrations"):
            await m.main()
        assert _state.telemetry is None

    async def test_uvicorn_serve_is_called(self, no_config):
        mock_serve = AsyncMock()
        with patch("uvicorn.Server.serve", mock_serve), \
             patch("main._run_migrations"):
            await m.main()
        mock_serve.assert_called_once()

    async def test_telemetry_opened_when_config_present(self, tmp_path, no_config):
        telemetry_cfg = tmp_path / "TELEMETRY_CFG.yaml"
        telemetry_cfg.write_text(
            "telemetry:\n  enabled: true\n"
            "  database:\n    url: 'sqlite+aiosqlite:///:memory:'\n",
            encoding="utf-8",
        )
        m.TELEMETRY_CFG = telemetry_cfg

        from api.deps import _state
        with patch("uvicorn.Server.serve", AsyncMock()), \
             patch("main._run_migrations"):
            await m.main()

        assert _state.telemetry is not None

    async def test_automation_engine_loaded_when_config_present(self, tmp_path, no_config):
        auto_cfg = tmp_path / "AUTOMATION_CFG.yaml"
        auto_cfg.write_text(
            "automations:\n"
            "  - name: test_rule\n"
            "    tier: advisory\n"
            "    trigger:\n"
            "      type: manual\n"
            "    action:\n"
            "      type: log\n"
            "      message: hello\n",
            encoding="utf-8",
        )
        m.AUTOMATION_CFG = auto_cfg

        from api.deps import _state
        with patch("uvicorn.Server.serve", AsyncMock()), \
             patch("main._run_migrations"):
            await m.main()

        assert _state.engine is not None
        assert len(_state.engine.automations()) == 1


# ---------------------------------------------------------------------------
# Radio config API helpers (_clean_radio_entry)
# ---------------------------------------------------------------------------

class TestCleanRadioEntry:

    def test_rigctld_entry_keeps_relevant_keys(self):
        from api.routers.radio import _clean_radio_entry
        entry = {
            "name": "ic7300", "backend": "rigctld",
            "host": "192.168.1.10", "port": 4532,
            "poll_interval_s": 0.5, "reconnect_delay_s": 5.0,
            "model_id": 351,       # irrelevant for rigctld
            "baud_rate": 9600,     # irrelevant for rigctld
        }
        result = _clean_radio_entry(entry)
        assert "host" in result
        assert "port" in result
        assert "model_id" not in result
        assert "baud_rate" not in result

    def test_hamlib_entry_keeps_relevant_keys(self):
        from api.routers.radio import _clean_radio_entry
        entry = {
            "name": "ft991", "backend": "hamlib_direct",
            "model_id": 135, "port": "COM3", "baud_rate": 38400,
            "data_bits": 8, "stop_bits": 1, "parity": "N",
            "poll_interval_s": 1.0, "reconnect_delay_s": 5.0,
            "host": "localhost",   # irrelevant for hamlib_direct
        }
        result = _clean_radio_entry(entry)
        assert "model_id" in result
        assert "baud_rate" in result
        assert "host" not in result

    def test_fills_in_rigctld_defaults(self):
        from api.routers.radio import _clean_radio_entry
        result = _clean_radio_entry({"name": "r", "backend": "rigctld"})
        assert result["host"] == "localhost"
        assert result["port"] == 4532
        assert result["poll_interval_s"] == 0.5

    def test_fills_in_hamlib_defaults(self):
        from api.routers.radio import _clean_radio_entry
        result = _clean_radio_entry({"name": "r", "backend": "hamlib_direct"})
        assert result["parity"] == "N"
        assert result["data_bits"] == 8
        assert result["baud_rate"] == 9600

    def test_explicit_values_are_not_overridden_by_defaults(self):
        from api.routers.radio import _clean_radio_entry
        result = _clean_radio_entry({
            "name": "r", "backend": "rigctld",
            "host": "10.0.0.5", "port": 9999,
        })
        assert result["host"] == "10.0.0.5"
        assert result["port"] == 9999
