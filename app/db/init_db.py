from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import engine
from app.models import Base
from app.models.user import User, UserRole


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)


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

