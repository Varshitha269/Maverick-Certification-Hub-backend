"""add_resource_urls_to_certifications

Revision ID: b7e9c3d1f2a8
Revises: a3f8b1c2d4e5
Create Date: 2026-05-03 06:20:00.000000

Adds course_url, official_exam_url, resources_json columns to certifications table.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = 'b7e9c3d1f2a8'
down_revision = 'a3f8b1c2d4e5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('certifications', sa.Column('course_url', sa.String(length=800), nullable=True))
    op.add_column('certifications', sa.Column('official_exam_url', sa.String(length=800), nullable=True))
    op.add_column('certifications', sa.Column('resources_json', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('certifications', 'resources_json')
    op.drop_column('certifications', 'official_exam_url')
    op.drop_column('certifications', 'course_url')
