-- Maverick Certification Hub — PostgreSQL DDL (manual alternative to Alembic)
--
-- Prefer: set DATABASE_URL to Azure Postgres, install deps, run: alembic upgrade head
-- Use this file only if you must run raw SQL in Azure Portal / psql. Then run:
--   alembic stamp head
-- so future migrations do not try to recreate tables.
--
-- Execute on an EMPTY database (drops enums if re-run — adjust as needed).

BEGIN;

-- Enum types (names must match SQLAlchemy / Alembic migrations)
CREATE TYPE userrole AS ENUM ('admin', 'user');
CREATE TYPE enrollmentstatus AS ENUM ('selected', 'in_progress', 'completed', 'cancelled');
CREATE TYPE taskstatus AS ENUM ('todo', 'doing', 'done', 'blocked');
CREATE TYPE uploadpurpose AS ENUM ('certificate', 'profile_doc', 'other');
CREATE TYPE notificationtype AS ENUM ('system', 'enrollment', 'reminder', 'voucher');
CREATE TYPE voucherstatus AS ENUM ('issued', 'redeemed', 'expired', 'revoked');

CREATE TABLE certifications (
    id SERIAL PRIMARY KEY,
    title VARCHAR(240) NOT NULL,
    provider VARCHAR(160) NOT NULL,
    level VARCHAR(80),
    description TEXT,
    estimated_hours INTEGER,
    exam_cost INTEGER,
    tags VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_certifications_provider ON certifications (provider);
CREATE INDEX ix_certifications_title ON certifications (title);

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(320) NOT NULL,
    full_name VARCHAR(200),
    hashed_password VARCHAR(255) NOT NULL,
    role userrole NOT NULL,
    is_active BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE TABLE certification_drives (
    id SERIAL PRIMARY KEY,
    certification_id INTEGER NOT NULL REFERENCES certifications (id),
    name VARCHAR(200) NOT NULL,
    start_date VARCHAR(40),
    end_date VARCHAR(40),
    eligibility_rules TEXT,
    voucher_budget INTEGER,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_certification_drives_certification_id ON certification_drives (certification_id);

CREATE TABLE email_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users (id),
    to_email VARCHAR(320) NOT NULL,
    subject VARCHAR(300) NOT NULL,
    body_preview TEXT,
    provider VARCHAR(40) NOT NULL,
    provider_message_id VARCHAR(200),
    success BOOLEAN NOT NULL,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_email_logs_to_email ON email_logs (to_email);
CREATE INDEX ix_email_logs_user_id ON email_logs (user_id);

CREATE TABLE enrollments (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id),
    certification_id INTEGER NOT NULL REFERENCES certifications (id),
    drive_id INTEGER REFERENCES certification_drives (id),
    status enrollmentstatus NOT NULL,
    target_completion_date VARCHAR(40),
    progress_percent INTEGER NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_enrollments_certification_id ON enrollments (certification_id);
CREATE INDEX ix_enrollments_drive_id ON enrollments (drive_id);
CREATE INDEX ix_enrollments_user_id ON enrollments (user_id);

CREATE TABLE tasks (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id),
    enrollment_id INTEGER REFERENCES enrollments (id),
    title VARCHAR(240) NOT NULL,
    description TEXT,
    status taskstatus NOT NULL,
    due_date VARCHAR(40),
    priority INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_tasks_enrollment_id ON tasks (enrollment_id);
CREATE INDEX ix_tasks_user_id ON tasks (user_id);

CREATE TABLE uploaded_files (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id),
    enrollment_id INTEGER REFERENCES enrollments (id),
    purpose uploadpurpose NOT NULL,
    original_filename VARCHAR(260) NOT NULL,
    content_type VARCHAR(120),
    storage_provider VARCHAR(40) NOT NULL,
    blob_path VARCHAR(500) NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_uploaded_files_enrollment_id ON uploaded_files (enrollment_id);
CREATE INDEX ix_uploaded_files_user_id ON uploaded_files (user_id);

-- Migration c1efea66ce53_enhanced_admin
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    actor_user_id INTEGER REFERENCES users (id),
    action VARCHAR(120) NOT NULL,
    entity VARCHAR(80) NOT NULL,
    entity_id VARCHAR(80),
    ip VARCHAR(80),
    user_agent VARCHAR(300),
    details_json TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_audit_entity_entityid ON audit_logs (entity, entity_id);
CREATE INDEX ix_audit_logs_action ON audit_logs (action);
CREATE INDEX ix_audit_logs_actor_user_id ON audit_logs (actor_user_id);
CREATE INDEX ix_audit_logs_entity ON audit_logs (entity);
CREATE INDEX ix_audit_logs_entity_id ON audit_logs (entity_id);

CREATE TABLE notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id),
    type notificationtype NOT NULL,
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    link_url VARCHAR(500),
    read_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_notifications_user_id ON notifications (user_id);
CREATE INDEX ix_notifications_user_read ON notifications (user_id, read_at);

CREATE TABLE vouchers (
    id SERIAL PRIMARY KEY,
    drive_id INTEGER REFERENCES certification_drives (id),
    certification_id INTEGER REFERENCES certifications (id),
    user_id INTEGER NOT NULL REFERENCES users (id),
    code VARCHAR(120) NOT NULL,
    status voucherstatus NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_vouchers_certification_id ON vouchers (certification_id);
CREATE UNIQUE INDEX ix_vouchers_code ON vouchers (code);
CREATE INDEX ix_vouchers_drive_id ON vouchers (drive_id);
CREATE INDEX ix_vouchers_user_id ON vouchers (user_id);
CREATE INDEX ix_vouchers_user_status ON vouchers (user_id, status);

COMMIT;

-- Alembic revision marker (matches migrations 967f40ab7011 + c1efea66ce53).
-- Skip this block if you will run `alembic upgrade head` on an empty DB instead.
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
INSERT INTO alembic_version (version_num) VALUES ('c1efea66ce53')
ON CONFLICT (version_num) DO NOTHING;
