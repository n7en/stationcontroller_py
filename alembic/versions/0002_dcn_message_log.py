"""Add dcn_message_log table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dcn_message_log",
        sa.Column("id",        sa.Integer(),   nullable=False),
        sa.Column("ts",        sa.Float(),     nullable=False),
        sa.Column("direction", sa.String(2),   nullable=False),
        sa.Column("transport", sa.String(64),  nullable=False, server_default=""),
        sa.Column("from_addr", sa.String(4),   nullable=False, server_default=""),
        sa.Column("to_addr",   sa.String(4),   nullable=False, server_default=""),
        sa.Column("broadcast", sa.Boolean(),   nullable=False, server_default="0"),
        sa.Column("payload",   sa.Text(),      nullable=False),
        sa.Column("raw",       sa.Text(),      nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dcn_message_log_ts", "dcn_message_log", ["ts"])


def downgrade() -> None:
    op.drop_table("dcn_message_log")
