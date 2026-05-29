"""Initial schema - four telemetry tables.

Revision ID: 0001
Revises:
Create Date: 2026-04-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sensor_readings",
        sa.Column("id",          sa.Integer(),    nullable=False),
        sa.Column("ts",          sa.Float(),      nullable=False),
        sa.Column("sensor_name", sa.String(64),   nullable=False),
        sa.Column("value",       sa.Float(),      nullable=False),
        sa.Column("unit",        sa.String(16),   nullable=False, server_default=""),
        sa.Column("source",      sa.String(64),   nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sensor_readings_ts",      "sensor_readings", ["ts"])
    op.create_index("ix_sensor_readings_name_ts", "sensor_readings", ["sensor_name", "ts"])

    op.create_table(
        "device_events",
        sa.Column("id",           sa.Integer(),    nullable=False),
        sa.Column("ts",           sa.Float(),      nullable=False),
        sa.Column("event_type",   sa.String(32),   nullable=False),
        sa.Column("device_key",   sa.String(64),   nullable=False),
        sa.Column("device_name",  sa.String(64),   nullable=False, server_default=""),
        sa.Column("old_value",    sa.String(128),  nullable=True),
        sa.Column("new_value",    sa.String(128),  nullable=True),
        sa.Column("source",       sa.String(64),   nullable=False, server_default=""),
        sa.Column("details_json", sa.Text(),       nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_device_events_ts",      "device_events", ["ts"])
    op.create_index("ix_device_events_key_ts",  "device_events", ["device_key", "ts"])

    op.create_table(
        "automation_events",
        sa.Column("id",           sa.Integer(),    nullable=False),
        sa.Column("ts",           sa.Float(),      nullable=False),
        sa.Column("rule_name",    sa.String(128),  nullable=False),
        sa.Column("tier",         sa.String(32),   nullable=False, server_default=""),
        sa.Column("priority",     sa.Integer(),    nullable=False, server_default="0"),
        sa.Column("fired",        sa.Boolean(),    nullable=False),
        sa.Column("trigger_type", sa.String(32),   nullable=False, server_default=""),
        sa.Column("context_json", sa.Text(),       nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_automation_events_ts",       "automation_events", ["ts"])
    op.create_index("ix_automation_events_rule_ts",  "automation_events", ["rule_name", "ts"])

    op.create_table(
        "application_log",
        sa.Column("id",        sa.Integer(),  nullable=False),
        sa.Column("ts",        sa.Float(),    nullable=False),
        sa.Column("level",     sa.String(16), nullable=False),
        sa.Column("logger",    sa.String(128),nullable=False),
        sa.Column("message",   sa.Text(),     nullable=False),
        sa.Column("traceback", sa.Text(),     nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_application_log_ts", "application_log", ["ts"])


def downgrade() -> None:
    op.drop_table("application_log")
    op.drop_table("automation_events")
    op.drop_table("device_events")
    op.drop_table("sensor_readings")
