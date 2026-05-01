# Maverick Certification Hub — Backend (FastAPI)

## What you get
- **JWT auth** with **roles**: `admin`, `user`
- **Admin APIs**: manage users, certifications, certification drives, enrollments, tasks, analytics
- **User APIs**: profile, dashboards, enroll/select certifications, upload certificates, track tasks & progress
- **Email notifications** (SendGrid): selection confirmation + pending/overdue reminders
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
- Default DB is SQLite (`backend.db`) for dev; switch to Postgres via `DATABASE_URL`.
- Background reminder emails run via APScheduler inside the API process (good for hackathon/dev). For production, move the scheduler to a separate worker process.

