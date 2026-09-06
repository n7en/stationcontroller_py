"""
TelemetryStore - async write and query API for the telemetry database.

All public methods are async and safe to call from asyncio coroutines.
The store manages its own engine and session factory; call open() / close()
(or use it as an async context manager) before issuing any queries.
"""
from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from typing import Optional

from sqlalchemy import delete, distinct, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .models import ApplicationLog, AutomationEvent, Base, DeviceEvent, DcnMessageLog, SensorReading


class TelemetryStore:
    def __init__(self, url: str = "sqlite+aiosqlite:///data/station.db") -> None:
        self._url = url
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker[AsyncSession]] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def open(self) -> None:
        self._engine = create_async_engine(self._url, echo=False)
        self._session_factory = async_sessionmaker(
            self._engine, expire_on_commit=False
        )
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None

    async def __aenter__(self) -> "TelemetryStore":
        await self.open()
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()

    @asynccontextmanager
    async def _session(self):
        async with self._session_factory() as s:
            async with s.begin():
                yield s

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def record_sensor(
        self,
        sensor_name: str,
        value: float,
        unit: str = "",
        source: str = "",
        ts: Optional[float] = None,
    ) -> None:
        async with self._session() as s:
            s.add(SensorReading(
                ts=ts or time.time(),
                sensor_name=sensor_name,
                value=value,
                unit=unit,
                source=source,
            ))

    async def record_device_event(
        self,
        event_type: str,
        device_key: str,
        device_name: str = "",
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        source: str = "",
        details: Optional[dict] = None,
        ts: Optional[float] = None,
    ) -> None:
        async with self._session() as s:
            s.add(DeviceEvent(
                ts=ts or time.time(),
                event_type=event_type,
                device_key=device_key,
                device_name=device_name,
                old_value=old_value,
                new_value=new_value,
                source=source,
                details_json=json.dumps(details) if details else None,
            ))

    async def record_automation_event(
        self,
        rule_name: str,
        fired: bool,
        tier: str = "",
        priority: int = 0,
        trigger_type: str = "",
        context: Optional[dict] = None,
        ts: Optional[float] = None,
    ) -> None:
        async with self._session() as s:
            s.add(AutomationEvent(
                ts=ts or time.time(),
                rule_name=rule_name,
                tier=tier,
                priority=priority,
                fired=fired,
                trigger_type=trigger_type,
                context_json=json.dumps(context) if context else None,
            ))

    async def record_dcn_message(
        self,
        direction: str,
        payload: str,
        from_addr: str = "",
        to_addr: str = "",
        broadcast: bool = False,
        transport: str = "",
        raw: str | None = None,
        ts: float | None = None,
    ) -> None:
        async with self._session() as s:
            s.add(DcnMessageLog(
                ts=ts or time.time(),
                direction=direction,
                transport=transport,
                from_addr=from_addr,
                to_addr=to_addr,
                broadcast=broadcast,
                payload=payload,
                raw=raw,
            ))

    async def record_log(
        self,
        level: str,
        logger: str,
        message: str,
        traceback: Optional[str] = None,
        ts: Optional[float] = None,
    ) -> None:
        async with self._session() as s:
            s.add(ApplicationLog(
                ts=ts or time.time(),
                level=level,
                logger=logger,
                message=message,
                traceback=traceback,
            ))

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get_sensor_names(self) -> list[str]:
        async with self._session() as s:
            result = await s.execute(
                select(distinct(SensorReading.sensor_name))
                .order_by(SensorReading.sensor_name)
            )
            return list(result.scalars())

    async def get_sensor_history(
        self,
        sensor_name: str,
        since: float,
        until: Optional[float] = None,
        limit: int = 1000,
    ) -> list[SensorReading]:
        until = until or time.time()
        async with self._session() as s:
            result = await s.execute(
                select(SensorReading)
                .where(
                    SensorReading.sensor_name == sensor_name,
                    SensorReading.ts >= since,
                    SensorReading.ts <= until,
                )
                .order_by(SensorReading.ts)
                .limit(limit)
            )
            return list(result.scalars())

    async def get_automation_events(
        self,
        rule_name: Optional[str] = None,
        since: Optional[float] = None,
        limit: int = 200,
    ) -> list[AutomationEvent]:
        since = since or 0.0
        stmt = select(AutomationEvent).where(AutomationEvent.ts >= since)
        if rule_name:
            stmt = stmt.where(AutomationEvent.rule_name == rule_name)
        stmt = stmt.order_by(AutomationEvent.ts.desc()).limit(limit)
        async with self._session() as s:
            result = await s.execute(stmt)
            return list(result.scalars())

    async def get_device_events(
        self,
        device_key: Optional[str] = None,
        since: Optional[float] = None,
        limit: int = 200,
    ) -> list[DeviceEvent]:
        since = since or 0.0
        stmt = select(DeviceEvent).where(DeviceEvent.ts >= since)
        if device_key:
            stmt = stmt.where(DeviceEvent.device_key == device_key)
        stmt = stmt.order_by(DeviceEvent.ts.desc()).limit(limit)
        async with self._session() as s:
            result = await s.execute(stmt)
            return list(result.scalars())

    # ------------------------------------------------------------------
    # Retention / pruning
    # ------------------------------------------------------------------

    async def prune(
        self,
        sensor_readings_days: int = 90,
        device_events_days: int = 365,
        automation_events_days: int = 365,
        application_log_days: int = 30,
        dcn_message_log_hours: int = 24,
    ) -> None:
        now = time.time()
        day = 86400.0
        async with self._session() as s:
            await s.execute(
                delete(SensorReading).where(
                    SensorReading.ts < now - sensor_readings_days * day
                )
            )
            await s.execute(
                delete(DeviceEvent).where(
                    DeviceEvent.ts < now - device_events_days * day
                )
            )
            await s.execute(
                delete(AutomationEvent).where(
                    AutomationEvent.ts < now - automation_events_days * day
                )
            )
            await s.execute(
                delete(ApplicationLog).where(
                    ApplicationLog.ts < now - application_log_days * day
                )
            )
            await s.execute(
                delete(DcnMessageLog).where(
                    DcnMessageLog.ts < now - dcn_message_log_hours * 3600.0
                )
            )
