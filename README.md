# Maverick Certification Hub — Backend (FastAPI)

## What you get
- **JWT auth** with **roles**: `admin`, `user`
- **Admin APIs**: manage users, certifications, certification drives, enrollments, tasks, analytics
- **User APIs**: profile, dashboards, enroll/select certifications, upload certificates, track tasks & progress
- **Email notifications** (Azure Communication Services Email): selection confirmation + pending/overdue reminders
- **Azure Blob Storage**: store uploaded certificates and generated exports
- **AI endpoints** (Azure OpenAI-ready): extract/validate certificate info and generate user task plans

## Quickstart (Windows)
CMD-only helper scripts:

```bash
setup.cmd
run.cmd
```

Manual steps (if you prefer):

Create a venv and install deps:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Copy env template and edit:

```bash
copy .env.example .env
```

Run DB migrations and start server:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

Open API docs:
- Swagger: `http://127.0.0.1:8000/docs`

## Default admin
- **email**: `admin@maverick.local`
- **password**: `Admin@12345`

## Notes
- Default DB is SQLite (`backend.db`) for dev. For **Azure Database for PostgreSQL**, set `DATABASE_URL` to `postgresql+psycopg2://...?sslmode=require`, run `pip install -r requirements.txt`, then `alembic upgrade head`. Optional raw DDL: `scripts/postgres_schema_manual.sql`.
- **Email:** set `ACS_EMAIL_CONNECTION_STRING` and `EMAIL_FROM` in `.env` (verified sender for your [ACS Email](https://learn.microsoft.com/azure/communication-services/concepts/email/email-overview) resource). If either is missing, sends are logged as failed in `email_logs`.
- Background reminder emails run via APScheduler inside the API process (good for hackathon/dev). For production, move the scheduler to a separate worker process.

