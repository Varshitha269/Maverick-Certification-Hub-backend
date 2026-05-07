"""add_eligibility_test_attempts

Revision ID: d4e7f8a9b0c1
Revises: 3a7d2b6c1f10
Create Date: 2026-05-05 22:20:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "d4e7f8a9b0c1"
down_revision = "3a7d2b6c1f10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("eligibility_test_attempts"):
        op.create_table(
            "eligibility_test_attempts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("certification_id", sa.Integer(), nullable=False),
            sa.Column("score", sa.Integer(), nullable=False),
            sa.Column("passed", sa.Boolean(), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("answers_json", sa.Text(), nullable=True),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["certification_id"], ["certifications.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    existing_indexes = {idx["name"] for idx in inspect(bind).get_indexes("eligibility_test_attempts")}
    for name, columns in {
        op.f("ix_eligibility_test_attempts_certification_id"): ["certification_id"],
        op.f("ix_eligibility_test_attempts_passed"): ["passed"],
        op.f("ix_eligibility_test_attempts_status"): ["status"],
        op.f("ix_eligibility_test_attempts_user_id"): ["user_id"],
    }.items():
        if name not in existing_indexes:
            op.create_index(name, "eligibility_test_attempts", columns, unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_eligibility_test_attempts_user_id"), table_name="eligibility_test_attempts")
    op.drop_index(op.f("ix_eligibility_test_attempts_status"), table_name="eligibility_test_attempts")
    op.drop_index(op.f("ix_eligibility_test_attempts_passed"), table_name="eligibility_test_attempts")
    op.drop_index(op.f("ix_eligibility_test_attempts_certification_id"), table_name="eligibility_test_attempts")
    op.drop_table("eligibility_test_attempts")
