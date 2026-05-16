from sqlalchemy.orm import Session
from sqlalchemy import inspect, text

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import engine
from app.models import Base
from app.models.user import User, UserRole


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_uploaded_file_review_columns()


def _ensure_uploaded_file_review_columns() -> None:
    inspector = inspect(engine)
    if "uploaded_files" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("uploaded_files")}
    reviewed_at_type = "TIMESTAMP WITH TIME ZONE" if engine.dialect.name == "postgresql" else "DATETIME"
    columns = {
        "review_status": "VARCHAR(40) NOT NULL DEFAULT 'under_review'",
        "review_reason": "TEXT",
        "reviewed_by": "VARCHAR(320)",
        "reviewed_at": reviewed_at_type,
    }
    with engine.begin() as conn:
        for name, ddl in columns.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE uploaded_files ADD COLUMN {name} {ddl}"))


def ensure_bootstrap_admin(db: Session) -> None:
    if not settings.BOOTSTRAP_ADMIN_EMAIL or not settings.BOOTSTRAP_ADMIN_PASSWORD:
        return
    existing = db.query(User).filter(User.email == settings.BOOTSTRAP_ADMIN_EMAIL).first()
    if existing:
        return
    admin = User(
        email=settings.BOOTSTRAP_ADMIN_EMAIL,
        full_name="Admin",
        hashed_password=hash_password(settings.BOOTSTRAP_ADMIN_PASSWORD),
        role=UserRole.admin,
        is_active=True,
    )
    db.add(admin)
    db.commit()

