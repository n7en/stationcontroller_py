"""
SQLAlchemy ORM models for the telemetry database.

Four tables:
  sensor_readings   — continuous sensor history
  device_events     — relay toggles, radio state changes, device online/offline
  automation_events — rule fire/clear transitions (not every eval cycle)
  application_log   — Python logging sink
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger, Boolean, Float, Index, Integer,
    String, Text, text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id:          Mapped[int]   = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts:          Mapped[float] = mapped_column(Float,  nullable=False, index=True)
    sensor_name: Mapped[str]   = mapped_column(String(64), nullable=False)
    value:       Mapped[float] = mapped_column(Float,  nullable=False)
    unit:        Mapped[str]   = mapped_column(String(16), nullable=False, default="")
    source:      Mapped[str]   = mapped_column(String(64), nullable=False, default="")

    __table_args__ = (
        Index("ix_sensor_readings_name_ts", "sensor_name", "ts"),
    )


class DeviceEvent(Base):
    __tablename__ = "device_events"

    id:           Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts:           Mapped[float]         = mapped_column(Float,  nullable=False, index=True)
    event_type:   Mapped[str]           = mapped_column(String(32), nullable=False)
    device_key:   Mapped[str]           = mapped_column(String(64), nullable=False)
    device_name:  Mapped[str]           = mapped_column(String(64), nullable=False, default="")
    old_value:    Mapped[str | None]    = mapped_column(String(128), nullable=True)
    new_value:    Mapped[str | None]    = mapped_column(String(128), nullable=True)
    source:       Mapped[str]           = mapped_column(String(64), nullable=False, default="")
    details_json: Mapped[str | None]    = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_device_events_key_ts", "device_key", "ts"),
    )


class AutomationEvent(Base):
    __tablename__ = "automation_events"

    id:           Mapped[int]        = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts:           Mapped[float]      = mapped_column(Float,  nullable=False, index=True)
    rule_name:    Mapped[str]        = mapped_column(String(128), nullable=False)
    tier:         Mapped[str]        = mapped_column(String(32), nullable=False, default="")
    priority:     Mapped[int]        = mapped_column(Integer, nullable=False, default=0)
    fired:        Mapped[bool]       = mapped_column(Boolean, nullable=False)
    trigger_type: Mapped[str]        = mapped_column(String(32), nullable=False, default="")
    context_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_automation_events_rule_ts", "rule_name", "ts"),
    )


class DcnMessageLog(Base):
    __tablename__ = "dcn_message_log"

    id:        Mapped[int]        = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts:        Mapped[float]      = mapped_column(Float,  nullable=False, index=True)
    direction: Mapped[str]        = mapped_column(String(2),  nullable=False)   # "rx" | "tx"
    transport: Mapped[str]        = mapped_column(String(64), nullable=False, default="")
    from_addr: Mapped[str]        = mapped_column(String(4),  nullable=False, default="")
    to_addr:   Mapped[str]        = mapped_column(String(4),  nullable=False, default="")
    broadcast: Mapped[bool]       = mapped_column(Boolean, nullable=False, default=False)
    payload:   Mapped[str]        = mapped_column(Text, nullable=False)
    raw:       Mapped[str | None] = mapped_column(Text, nullable=True)


class ApplicationLog(Base):
    __tablename__ = "application_log"

    id:        Mapped[int]        = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts:        Mapped[float]      = mapped_column(Float,  nullable=False, index=True)
    level:     Mapped[str]        = mapped_column(String(16), nullable=False)
    logger:    Mapped[str]        = mapped_column(String(128), nullable=False)
    message:   Mapped[str]        = mapped_column(Text, nullable=False)
    traceback: Mapped[str | None] = mapped_column(Text, nullable=True)
