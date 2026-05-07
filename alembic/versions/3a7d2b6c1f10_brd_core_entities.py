"""brd_core_entities

Revision ID: 3a7d2b6c1f10
Revises: c1efea66ce53
Create Date: 2026-05-04

Adds BRD entities (registrations, eligibility, approvals, assessment results)
and extends drives/vouchers without breaking existing behavior.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "3a7d2b6c1f10"
down_revision = "9468bbf70a49"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Extend certification_drives (safe nullable adds) ---
    op.add_column("certification_drives", sa.Column("sponsor", sa.String(length=200), nullable=True))
    op.add_column("certification_drives", sa.Column("owner_email", sa.String(length=320), nullable=True))
    op.add_column("certification_drives", sa.Column("policy_url", sa.String(length=800), nullable=True))
    op.add_column("certification_drives", sa.Column("target_count", sa.Integer(), nullable=True))
    op.add_column("certification_drives", sa.Column("status", sa.String(length=40), nullable=False, server_default="open"))
    op.add_column("certification_drives", sa.Column("repository_prefix", sa.String(length=300), nullable=True))
    op.create_index(op.f("ix_certification_drives_status"), "certification_drives", ["status"], unique=False)
    op.alter_column("certification_drives", "status", server_default=None)

    # --- New enums ---
    # We create types with DO blocks (idempotent) because some environments may
    # already have types from a manual SQL bootstrap.
    op.execute(
        """
DO $$ BEGIN
    CREATE TYPE registrationstatus AS ENUM ('submitted','eligible_pending_approval','eligible','ineligible','scheduled','assessed','passed','failed','voucher_issued','closed');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
"""
    )
    op.execute(
        """
DO $$ BEGIN
    CREATE TYPE eligibilitydecision AS ENUM ('eligible','ineligible','needs_approval');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
"""
    )
    op.execute(
        """
DO $$ BEGIN
    CREATE TYPE approvalstatus AS ENUM ('pending','approved','rejected','cancelled');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
"""
    )
    op.execute(
        """
DO $$ BEGIN
    CREATE TYPE assessmentoutcome AS ENUM ('pass','fail','no_show','pending');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
"""
    )

    registrationstatus = postgresql.ENUM(name="registrationstatus", create_type=False)
    eligibilitydecision = postgresql.ENUM(name="eligibilitydecision", create_type=False)
    approvalstatus = postgresql.ENUM(name="approvalstatus", create_type=False)
    assessmentoutcome = postgresql.ENUM(name="assessmentoutcome", create_type=False)

    # --- New tables (idempotent SQL to tolerate partial bootstrap runs) ---
    op.execute(
        """
CREATE TABLE IF NOT EXISTS registrations (
    id SERIAL PRIMARY KEY,
    drive_id INTEGER NOT NULL REFERENCES certification_drives(id),
    emp_id VARCHAR(80),
    candidate_name VARCHAR(200) NOT NULL,
    candidate_email VARCHAR(320) NOT NULL,
    bu VARCHAR(120),
    location VARCHAR(120),
    manager_email VARCHAR(320),
    exam_track VARCHAR(160),
    slot VARCHAR(120),
    prior_attempts INTEGER NOT NULL DEFAULT 0,
    status registrationstatus NOT NULL DEFAULT 'submitted',
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_registrations_candidate_email ON registrations(candidate_email);
CREATE INDEX IF NOT EXISTS ix_registrations_drive_id ON registrations(drive_id);
CREATE INDEX IF NOT EXISTS ix_registrations_emp_id ON registrations(emp_id);
CREATE INDEX IF NOT EXISTS ix_registrations_status ON registrations(status);
CREATE INDEX IF NOT EXISTS ix_registrations_drive_status ON registrations(drive_id, status);
"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS eligibility_evaluations (
    id SERIAL PRIMARY KEY,
    registration_id INTEGER NOT NULL REFERENCES registrations(id),
    drive_id INTEGER NOT NULL REFERENCES certification_drives(id),
    decision eligibilitydecision NOT NULL,
    reason VARCHAR(500),
    criteria_json TEXT,
    evaluated_by VARCHAR(40) NOT NULL DEFAULT 'rules_engine',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_eligibility_evaluations_decision ON eligibility_evaluations(decision);
CREATE INDEX IF NOT EXISTS ix_eligibility_evaluations_drive_id ON eligibility_evaluations(drive_id);
CREATE INDEX IF NOT EXISTS ix_eligibility_evaluations_registration_id ON eligibility_evaluations(registration_id);
"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS approvals (
    id SERIAL PRIMARY KEY,
    registration_id INTEGER NOT NULL REFERENCES registrations(id),
    drive_id INTEGER NOT NULL REFERENCES certification_drives(id),
    level INTEGER NOT NULL DEFAULT 1,
    status approvalstatus NOT NULL DEFAULT 'pending',
    requested_by_user_id INTEGER REFERENCES users(id),
    approver_email VARCHAR(320) NOT NULL,
    decision_notes TEXT,
    decided_by_user_id INTEGER REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_approvals_approver_email ON approvals(approver_email);
CREATE INDEX IF NOT EXISTS ix_approvals_drive_id ON approvals(drive_id);
CREATE INDEX IF NOT EXISTS ix_approvals_registration_id ON approvals(registration_id);
CREATE INDEX IF NOT EXISTS ix_approvals_requested_by_user_id ON approvals(requested_by_user_id);
CREATE INDEX IF NOT EXISTS ix_approvals_decided_by_user_id ON approvals(decided_by_user_id);
CREATE INDEX IF NOT EXISTS ix_approvals_status ON approvals(status);
CREATE INDEX IF NOT EXISTS ix_approvals_drive_level_status ON approvals(drive_id, level, status);
"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS assessment_results (
    id SERIAL PRIMARY KEY,
    registration_id INTEGER NOT NULL REFERENCES registrations(id),
    drive_id INTEGER NOT NULL REFERENCES certification_drives(id),
    score INTEGER,
    outcome assessmentoutcome NOT NULL DEFAULT 'pending',
    assessed_on VARCHAR(40),
    evidence_upload_id INTEGER REFERENCES uploaded_files(id),
    evidence_url VARCHAR(800),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_assessment_results_drive_id ON assessment_results(drive_id);
CREATE INDEX IF NOT EXISTS ix_assessment_results_outcome ON assessment_results(outcome);
CREATE INDEX IF NOT EXISTS ix_assessment_results_registration_id ON assessment_results(registration_id);
CREATE INDEX IF NOT EXISTS ix_assessment_results_evidence_upload_id ON assessment_results(evidence_upload_id);
"""
    )

    # --- Extend vouchers (all nullable adds) ---
    op.execute("ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS masked_code VARCHAR(32);")
    op.execute("ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS code_encrypted TEXT;")
    op.execute("ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS assigned_registration_id INTEGER;")
    op.execute("ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS delivered_at VARCHAR(40);")
    op.execute("ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS redeemed_at VARCHAR(40);")
    op.execute("ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS revoked_at VARCHAR(40);")
    op.execute("ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS delivery_token_id VARCHAR(80);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_vouchers_assigned_registration_id ON vouchers(assigned_registration_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_vouchers_delivery_token_id ON vouchers(delivery_token_id);")
    op.execute(
        """
DO $$ BEGIN
    ALTER TABLE vouchers ADD CONSTRAINT fk_vouchers_assigned_registration_id
      FOREIGN KEY (assigned_registration_id) REFERENCES registrations(id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
"""
    )


def downgrade() -> None:
    op.drop_constraint("fk_vouchers_assigned_registration_id", "vouchers", type_="foreignkey")
    op.drop_index(op.f("ix_vouchers_delivery_token_id"), table_name="vouchers")
    op.drop_index(op.f("ix_vouchers_assigned_registration_id"), table_name="vouchers")
    op.drop_column("vouchers", "delivery_token_id")
    op.drop_column("vouchers", "revoked_at")
    op.drop_column("vouchers", "redeemed_at")
    op.drop_column("vouchers", "delivered_at")
    op.drop_column("vouchers", "assigned_registration_id")
    op.drop_column("vouchers", "code_encrypted")
    op.drop_column("vouchers", "masked_code")

    op.drop_index(op.f("ix_assessment_results_evidence_upload_id"), table_name="assessment_results")
    op.drop_index(op.f("ix_assessment_results_registration_id"), table_name="assessment_results")
    op.drop_index(op.f("ix_assessment_results_outcome"), table_name="assessment_results")
    op.drop_index(op.f("ix_assessment_results_drive_id"), table_name="assessment_results")
    op.drop_table("assessment_results")

    op.drop_index("ix_approvals_drive_level_status", table_name="approvals")
    op.drop_index(op.f("ix_approvals_status"), table_name="approvals")
    op.drop_index(op.f("ix_approvals_decided_by_user_id"), table_name="approvals")
    op.drop_index(op.f("ix_approvals_requested_by_user_id"), table_name="approvals")
    op.drop_index(op.f("ix_approvals_registration_id"), table_name="approvals")
    op.drop_index(op.f("ix_approvals_drive_id"), table_name="approvals")
    op.drop_index(op.f("ix_approvals_approver_email"), table_name="approvals")
    op.drop_table("approvals")

    op.drop_index(op.f("ix_eligibility_evaluations_registration_id"), table_name="eligibility_evaluations")
    op.drop_index(op.f("ix_eligibility_evaluations_drive_id"), table_name="eligibility_evaluations")
    op.drop_index(op.f("ix_eligibility_evaluations_decision"), table_name="eligibility_evaluations")
    op.drop_table("eligibility_evaluations")

    op.drop_index("ix_registrations_drive_status", table_name="registrations")
    op.drop_index(op.f("ix_registrations_status"), table_name="registrations")
    op.drop_index(op.f("ix_registrations_emp_id"), table_name="registrations")
    op.drop_index(op.f("ix_registrations_drive_id"), table_name="registrations")
    op.drop_index(op.f("ix_registrations_candidate_email"), table_name="registrations")
    op.drop_table("registrations")

    op.drop_index(op.f("ix_certification_drives_status"), table_name="certification_drives")
    op.drop_column("certification_drives", "repository_prefix")
    op.drop_column("certification_drives", "status")
    op.drop_column("certification_drives", "target_count")
    op.drop_column("certification_drives", "policy_url")
    op.drop_column("certification_drives", "owner_email")
    op.drop_column("certification_drives", "sponsor")

    # drop enums (best-effort)
    op.execute("DROP TYPE IF EXISTS assessmentoutcome;")
    op.execute("DROP TYPE IF EXISTS approvalstatus;")
    op.execute("DROP TYPE IF EXISTS eligibilitydecision;")
    op.execute("DROP TYPE IF EXISTS registrationstatus;")

