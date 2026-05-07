"""notification_email_delivery

Revision ID: f2a4b6c8d0e1
Revises: e8f6a1b2c3d4
Create Date: 2026-05-07 00:10:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "f2a4b6c8d0e1"
down_revision = "e8f6a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {col["name"] for col in inspect(op.get_bind()).get_columns("notifications")}
    if "email_sent_at" not in existing:
        op.add_column("notifications", sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("notifications", "email_sent_at")
