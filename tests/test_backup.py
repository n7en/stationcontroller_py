"""
Tests for the backup/restore endpoints in api/routers/system.py.
"""
from __future__ import annotations

import io
import json
import zipfile

import pytest
from httpx import ASGITransport, AsyncClient

import api.routers.system as system_mod
from api.app import create_app
from api.deps import AppState, _state
from api.routers.system import _classify_entry, apply_restore_zip, build_backup_zip


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cfg_dir(tmp_path, monkeypatch):
    """Temp config/data dirs patched into the system router."""
    cfg = tmp_path / "config"
    (cfg / "dashboards").mkdir(parents=True)
    (cfg / "certs").mkdir()
    (cfg / "comms_config.yaml").write_text("buses: []\n", encoding="utf-8")
    (cfg / "radio_config.yaml").write_text("radios: []\n", encoding="utf-8")
    (cfg / "radio_config.yaml.example").write_text("example\n", encoding="utf-8")
    (cfg / "dashboards" / "main.yaml").write_text("cards: []\n", encoding="utf-8")
    (cfg / "certs" / "cert.pem").write_text("NOT A REAL CERT", encoding="utf-8")

    data = tmp_path / "data"
    data.mkdir()

    monkeypatch.setattr(system_mod, "CONFIG_DIR", cfg)
    monkeypatch.setattr(system_mod, "DATA_DIR", data)
    return cfg, data


@pytest.fixture
async def client(cfg_dir):
    fresh = AppState()
    for attr in vars(fresh):
        setattr(_state, attr, getattr(fresh, attr))
    app = create_app(AppState())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _make_backup(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Entry classification (path safety)
# ---------------------------------------------------------------------------

class TestClassifyEntry:

    def test_allowed_entries(self):
        assert _classify_entry("manifest.json") == "manifest"
        assert _classify_entry("config/comms_config.yaml") == "config"
        assert _classify_entry("config/dashboards/main.yaml") == "config"
        assert _classify_entry("data/station.db") == "db"

    def test_rejected_entries(self):
        assert _classify_entry("../evil.yaml") is None
        assert _classify_entry("config/../../evil.yaml") is None
        assert _classify_entry("/etc/passwd") is None
        assert _classify_entry("config/certs/cert.pem") is None
        assert _classify_entry("config/nested/deep/file.yaml") is None
        assert _classify_entry("config/script.py") is None
        assert _classify_entry("data/other.db") is None


# ---------------------------------------------------------------------------
# Backup building
# ---------------------------------------------------------------------------

class TestBuildBackup:

    def test_contains_config_and_manifest(self, cfg_dir):
        cfg, _data = cfg_dir
        data = build_backup_zip(config_dir=cfg)
        zf = zipfile.ZipFile(io.BytesIO(data))
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "config/comms_config.yaml" in names
        assert "config/radio_config.yaml" in names
        assert "config/dashboards/main.yaml" in names

    def test_excludes_certs_and_examples(self, cfg_dir):
        cfg, _data = cfg_dir
        zf = zipfile.ZipFile(io.BytesIO(build_backup_zip(config_dir=cfg)))
        names = zf.namelist()
        assert not any("certs" in n for n in names)
        assert not any(n.endswith(".example") for n in names)

    def test_manifest_fields(self, cfg_dir):
        cfg, _data = cfg_dir
        zf = zipfile.ZipFile(io.BytesIO(build_backup_zip(config_dir=cfg)))
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["app"] == "StationController"
        assert manifest["include_db"] is False
        assert "created" in manifest


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------

class TestRestore:

    def test_applies_config_files(self, cfg_dir):
        cfg, data = cfg_dir
        archive = _make_backup({
            "manifest.json": b"{}",
            "config/comms_config.yaml": b"buses: [restored]\n",
            "config/dashboards/main.yaml": b"cards: [restored]\n",
        })
        result = apply_restore_zip(archive, config_dir=cfg, data_dir=data)
        assert result["ok"] is True
        assert len(result["restored_files"]) == 2
        assert result["db_staged"] is False
        assert "restored" in (cfg / "comms_config.yaml").read_text()
        assert "restored" in (cfg / "dashboards" / "main.yaml").read_text()

    def test_makes_pre_restore_snapshot(self, cfg_dir):
        cfg, data = cfg_dir
        original = (cfg / "comms_config.yaml").read_bytes()
        archive = _make_backup({"config/comms_config.yaml": b"buses: [new]\n"})
        result = apply_restore_zip(archive, config_dir=cfg, data_dir=data)

        snap = data / "backups" / result["pre_restore_snapshot"]
        assert snap.exists()
        zf = zipfile.ZipFile(snap)
        assert zf.read("config/comms_config.yaml") == original

    def test_stages_database(self, cfg_dir):
        cfg, data = cfg_dir
        archive = _make_backup({"data/station.db": b"SQLITE FAKE"})
        result = apply_restore_zip(archive, config_dir=cfg, data_dir=data)
        assert result["db_staged"] is True
        assert (data / "station.db.restore").read_bytes() == b"SQLITE FAKE"

    def test_rejects_traversal(self, cfg_dir):
        cfg, data = cfg_dir
        archive = _make_backup({"config/../evil.yaml": b"bad"})
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            apply_restore_zip(archive, config_dir=cfg, data_dir=data)
        assert exc.value.status_code == 422

    def test_rejects_non_zip(self, cfg_dir):
        cfg, data = cfg_dir
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            apply_restore_zip(b"definitely not a zip", config_dir=cfg, data_dir=data)

    def test_rejects_empty_archive(self, cfg_dir):
        cfg, data = cfg_dir
        archive = _make_backup({"manifest.json": b"{}"})
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            apply_restore_zip(archive, config_dir=cfg, data_dir=data)


# ---------------------------------------------------------------------------
# HTTP round trip
# ---------------------------------------------------------------------------

class TestBackupApi:

    async def test_download_backup(self, client):
        r = await client.get("/api/system/backup")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
        assert "stationcontroller_backup_" in r.headers["content-disposition"]
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        assert "manifest.json" in zf.namelist()

    async def test_roundtrip_backup_then_restore(self, client, cfg_dir):
        cfg, _data = cfg_dir
        r = await client.get("/api/system/backup")
        (cfg / "comms_config.yaml").write_text("buses: [changed]\n", encoding="utf-8")

        r2 = await client.post(
            "/api/system/restore",
            content=r.content,
            headers={"Content-Type": "application/zip"},
        )
        assert r2.status_code == 200
        d = r2.json()
        assert d["ok"] is True
        assert d["restart_required"] is True
        # Round trip restored the original content
        assert (cfg / "comms_config.yaml").read_text() == "buses: []\n"

    async def test_restore_empty_body_rejected(self, client):
        r = await client.post("/api/system/restore", content=b"")
        assert r.status_code == 422
