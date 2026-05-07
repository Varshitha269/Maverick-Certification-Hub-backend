"""enhance_notifications

Revision ID: e8f6a1b2c3d4
Revises: d4e7f8a9b0c1
Create Date: 2026-05-07 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "e8f6a1b2c3d4"
down_revision = "d4e7f8a9b0c1"
branch_labels = None
depends_on = None


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    bind = op.get_bind()
    existing = {col["name"] for col in inspect(bind).get_columns(table)}
    if column.name not in existing:
        op.add_column(table, column)


def upgrade() -> None:
    _add_column_if_missing("notifications", sa.Column("priority", sa.String(length=20), nullable=True))
    _add_column_if_missing("notifications", sa.Column("image_url", sa.String(length=800), nullable=True))
    _add_column_if_missing("notifications", sa.Column("icon", sa.String(length=80), nullable=True))
    _add_column_if_missing("notifications", sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing("notifications", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing("notifications", sa.Column("push_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    _add_column_if_missing("notifications", sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    _add_column_if_missing("notifications", sa.Column("audience", sa.String(length=80), nullable=True))
    _add_column_if_missing("notifications", sa.Column("content_format", sa.String(length=20), nullable=False, server_default="plain"))

    bind = op.get_bind()
    indexes = {idx["name"] for idx in inspect(bind).get_indexes("notifications")}
    if "ix_notifications_schedule" not in indexes:
        op.create_index("ix_notifications_schedule", "notifications", ["scheduled_at", "expires_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    indexes = {idx["name"] for idx in inspect(bind).get_indexes("notifications")}
    if "ix_notifications_schedule" in indexes:
        op.drop_index("ix_notifications_schedule", table_name="notifications")
    for column in [
        "content_format",
        "audience",
        "email_enabled",
        "push_enabled",
        "expires_at",
        "scheduled_at",
        "icon",
        "image_url",
        "priority",
    ]:
        op.drop_column("notifications", column)
