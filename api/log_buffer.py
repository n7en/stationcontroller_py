"""
LogBuffer - in-memory circular buffer for log entries and DCN packets.

Entries are broadcast live to connected WebSocket clients and kept for
snapshot delivery to clients that connect after startup.
"""
from __future__ import annotations

import asyncio
import collections
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .ws_hub import WSHub


class LogBuffer:
    def __init__(self, maxlen: int = 500) -> None:
        self._general: collections.deque = collections.deque(maxlen=maxlen)
        self._dcn:     collections.deque = collections.deque(maxlen=maxlen)
        self._ws_hub:  "WSHub | None"   = None
        self._loop:    Optional[asyncio.AbstractEventLoop] = None

    def attach_ws_hub(self, hub: "WSHub") -> None:
        self._ws_hub = hub
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

    def _push(self, msg: dict) -> None:
        if self._ws_hub is None or self._loop is None:
            return
        try:
            # run_coroutine_threadsafe works whether called from the event-loop
            # thread or any other thread (RS-485 reader, paho network thread, etc.)
            asyncio.run_coroutine_threadsafe(
                self._ws_hub.broadcast(msg), self._loop
            )
        except Exception:
            pass

    def append_log(self, entry: dict) -> None:
        self._general.append(entry)
        self._push(entry)

    def append_dcn(self, entry: dict) -> None:
        self._dcn.append(entry)
        self._push(entry)

    def recent_general(self) -> list:
        return list(self._general)

    def recent_dcn(self) -> list:
        return list(self._dcn)

    def make_handler(self) -> logging.Handler:
        return _WsLogHandler(self)


class _WsLogHandler(logging.Handler):
    """Logging handler that feeds records into LogBuffer (and via it to WS clients)."""

    def __init__(self, buf: LogBuffer) -> None:
        super().__init__(level=logging.INFO)
        self._buf = buf

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry: dict = {
                "type":   "log_entry",
                "ts":     record.created,
                "level":  record.levelname,
                "logger": record.name,
                "msg":    record.getMessage(),
            }
            if record.exc_info:
                entry["exc"] = self.formatException(record.exc_info)
            self._buf.append_log(entry)
        except Exception:
            self.handleError(record)
