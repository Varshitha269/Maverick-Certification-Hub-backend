"""catalog_and_saved_for_later

Revision ID: a3f8b1c2d4e5
Revises: c1efea66ce53
Create Date: 2026-05-03 06:00:00.000000

Adds:
  - category, duration, prerequisites columns to certifications table
  - saved_for_later value to enrollmentstatus enum
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = 'a3f8b1c2d4e5'
down_revision = 'c1efea66ce53'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to certifications
    op.add_column('certifications', sa.Column('category', sa.String(length=120), nullable=True))
    op.add_column('certifications', sa.Column('duration', sa.String(length=80), nullable=True))
    op.add_column('certifications', sa.Column('prerequisites', sa.Text(), nullable=True))

    # Create index on category for fast filtering
    op.create_index(op.f('ix_certifications_category'), 'certifications', ['category'], unique=False)

    # SQLite does NOT support ALTER TYPE for enums — we handle this at the application level.
    # The enum column in SQLite is stored as VARCHAR, so adding a new value to the Python enum
    # is sufficient. For PostgreSQL, you would run:
    # op.execute("ALTER TYPE enrollmentstatus ADD VALUE IF NOT EXISTS 'saved_for_later' BEFORE 'selected'")


def downgrade() -> None:
    op.drop_index(op.f('ix_certifications_category'), table_name='certifications')
    op.drop_column('certifications', 'prerequisites')
    op.drop_column('certifications', 'duration')
    op.drop_column('certifications', 'category')
