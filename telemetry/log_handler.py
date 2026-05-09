"""
TelemetryLogHandler - Python logging.Handler that writes to TelemetryStore.

Install once at startup:

    handler = TelemetryLogHandler(store)
    handler.setLevel(logging.WARNING)
    logging.getLogger().addHandler(handler)
"""
from __future__ import annotations

import asyncio
import logging
import traceback
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .store import TelemetryStore


class TelemetryLogHandler(logging.Handler):
    def __init__(self, store: "TelemetryStore", level: int = logging.WARNING) -> None:
        super().__init__(level)
        self._store = store

    def emit(self, record: logging.LogRecord) -> None:
        try:
            tb = None
            if record.exc_info:
                tb = self.formatException(record.exc_info)
            msg = record.getMessage()
            ts = record.created

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    self._store.record_log(
                        level=record.levelname,
                        logger=record.name,
                        message=msg,
                        traceback=tb,
                        ts=ts,
                    ),
                    name="telemetry.log",
                )
            except RuntimeError:
                pass  # no event loop - drop silently to avoid recursion
        except Exception:
            self.handleError(record)
