from __future__ import annotations

from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.api_v1 import api_router
from app.core.config import settings
from app.db.init_db import create_tables, ensure_bootstrap_admin
from app.db.session import SessionLocal
from app.services.reminders import send_pending_and_overdue_reminders


def _start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")

    def _job():
        with SessionLocal() as db:
            send_pending_and_overdue_reminders(db)

    scheduler.add_job(_job, "interval", minutes=settings.REMINDER_JOB_INTERVAL_MINUTES, id="reminders", replace_existing=True)
    scheduler.start()
    return scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    with SessionLocal() as db:
        ensure_bootstrap_admin(db)
    scheduler = _start_scheduler()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
def health():
    return {"ok": True, "env": settings.ENVIRONMENT}

