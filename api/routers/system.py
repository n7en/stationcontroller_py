"""
System control endpoints - restart, backup, restore.

Backup format: a zip archive containing
    manifest.json               - version, timestamp, hostname
    config/<name>.yaml          - all runtime YAML config files
    config/dashboards/<n>.yaml  - dashboard layouts
    data/station.db             - optional SQLite snapshot (?include_db=true)

Restore accepts the same archive as the raw request body.  Config files are
applied immediately (a pre-restore snapshot of the current config is saved
to data/backups/ first).  A database in the archive is staged as
data/station.db.restore and swapped in by main.py on the next restart.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import socket
import sqlite3
import sys
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Optional

import yaml
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from ..paths import BASE_DIR, CONFIG_DIR

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/system", tags=["system"])

DATA_DIR    = BASE_DIR / "data"
BACKUPS_DIR = DATA_DIR / "backups"

# Never include these in a backup: certs are machine-local and regenerated,
# examples ship with the repo.
_EXCLUDE_DIRS  = {"certs"}
_EXCLUDE_SUFFX = (".example",)

_MAX_RESTORE_BYTES = 200 * 1024 * 1024   # 200 MB archive cap


@router.post("/restart")
async def restart_app() -> dict:
    """Schedule a full process restart after the response is sent."""
    async def _restart() -> None:
        await asyncio.sleep(0.5)   # give the HTTP response time to leave
        log.info("Restarting application: %s %s", sys.executable, sys.argv)
        os.execv(sys.executable, [sys.executable] + sys.argv)

    asyncio.create_task(_restart(), name="app_restart")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------

def _config_files(config_dir: Path) -> list[Path]:
    """All backup-worthy YAML files under config/ (recursive)."""
    out: list[Path] = []
    for p in sorted(config_dir.rglob("*.y*ml")):
        rel = p.relative_to(config_dir)
        if rel.parts and rel.parts[0] in _EXCLUDE_DIRS:
            continue
        if p.name.endswith(_EXCLUDE_SUFFX):
            continue
        out.append(p)
    return out


def _sqlite_db_path() -> Optional[Path]:
    """Resolve the SQLite database file from telemetry config, or None."""
    cfg_path = CONFIG_DIR / "telemetry_config.yaml"
    url = "sqlite+aiosqlite:///data/station.db"
    if cfg_path.exists():
        try:
            with open(cfg_path, encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
            url = raw.get("telemetry", {}).get("database", {}).get("url", url)
        except Exception:
            pass
    if not url.startswith("sqlite"):
        return None   # MariaDB etc. - use that database's own backup tooling
    path = Path(url.split("///", 1)[-1])
    return path if path.is_absolute() else BASE_DIR / path


def _snapshot_sqlite(db_path: Path) -> bytes:
    """Consistent online snapshot of a live SQLite database (blocking)."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        src = sqlite3.connect(str(db_path))
        try:
            dst = sqlite3.connect(str(tmp_path))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        return tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)


def build_backup_zip(include_db: bool = False, config_dir: Optional[Path] = None) -> bytes:
    """Build the backup archive in memory and return its bytes (blocking)."""
    cfg_dir = config_dir or CONFIG_DIR
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest = {
            "app": "StationController",
            "created": time.time(),
            "hostname": socket.gethostname(),
            "include_db": bool(include_db),
        }
        version_file = BASE_DIR / "VERSION"
        if version_file.exists():
            manifest["version"] = version_file.read_text(encoding="utf-8").strip()
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

        for p in _config_files(cfg_dir):
            arcname = "config/" + p.relative_to(cfg_dir).as_posix()
            zf.write(p, arcname)

        if include_db:
            db_path = _sqlite_db_path()
            if db_path is not None and db_path.exists():
                zf.writestr("data/station.db", _snapshot_sqlite(db_path))
    return buf.getvalue()


@router.get("/backup")
async def download_backup(
    include_db: bool = Query(default=False, description="Include a SQLite database snapshot"),
) -> Response:
    data = await asyncio.to_thread(build_backup_zip, include_db)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log.info("Backup downloaded (%d bytes, include_db=%s)", len(data), include_db)
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition":
                f'attachment; filename="stationcontroller_backup_{stamp}.zip"',
        },
    )


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------

def _classify_entry(name: str) -> Optional[str]:
    """Return 'config', 'db', or 'manifest' for an allowed archive entry.

    Rejects (returns None for) anything else - including absolute paths and
    path traversal.
    """
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts or not p.parts:
        return None
    if name == "manifest.json":
        return "manifest"
    if name == "data/station.db":
        return "db"
    if (
        p.parts[0] == "config"
        and p.suffix in (".yaml", ".yml")
        and len(p.parts) in (2, 3)
        and (len(p.parts) == 2 or p.parts[1] == "dashboards")
    ):
        return "config"
    return None


def apply_restore_zip(data: bytes, config_dir: Optional[Path] = None,
                      data_dir: Optional[Path] = None) -> dict:
    """Validate and apply a backup archive (blocking).

    Config files are written immediately; a database is staged as
    data/station.db.restore for the next startup.
    """
    cfg_dir = config_dir or CONFIG_DIR
    dat_dir = data_dir or DATA_DIR

    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=422, detail="Not a valid backup zip archive")

    entries = [(info, _classify_entry(info.filename)) for info in zf.infolist()
               if not info.is_dir()]
    rejected = [info.filename for info, kind in entries if kind is None]
    if rejected:
        raise HTTPException(
            status_code=422,
            detail=f"Archive contains unexpected entries: {rejected[:5]}",
        )
    if not any(kind in ("config", "db") for _, kind in entries):
        raise HTTPException(status_code=422, detail="Archive contains nothing to restore")

    # Safety snapshot of the current config before overwriting anything
    backups_dir = dat_dir / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    snapshot_path = backups_dir / f"pre_restore_{stamp}.zip"
    snapshot_path.write_bytes(build_backup_zip(include_db=False, config_dir=cfg_dir))

    restored: list[str] = []
    db_staged = False
    for info, kind in entries:
        if kind == "config":
            rel = PurePosixPath(info.filename).relative_to("config")
            target = cfg_dir / Path(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(info))
            restored.append(info.filename)
        elif kind == "db":
            dat_dir.mkdir(parents=True, exist_ok=True)
            (dat_dir / "station.db.restore").write_bytes(zf.read(info))
            db_staged = True

    log.info("Restore applied: %d config file(s)%s (pre-restore snapshot: %s)",
             len(restored), ", database staged" if db_staged else "", snapshot_path.name)
    return {
        "ok": True,
        "restored_files": restored,
        "db_staged": db_staged,
        "pre_restore_snapshot": snapshot_path.name,
        "restart_required": True,
    }


@router.post("/restore")
async def restore_backup(request: Request) -> dict:
    """Restore from a backup archive sent as the raw request body."""
    data = await request.body()
    if not data:
        raise HTTPException(status_code=422, detail="Empty request body")
    if len(data) > _MAX_RESTORE_BYTES:
        raise HTTPException(status_code=413, detail="Archive too large")
    return await asyncio.to_thread(apply_restore_zip, data)
