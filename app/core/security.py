import datetime as dt
from typing import Any

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return pwd_context.verify(password, hashed_password)


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    expire = _utcnow() + dt.timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode: dict[str, Any] = {"sub": subject, "type": "access", "exp": expire}
    if extra:
        to_encode.update(extra)
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str) -> str:
    expire = _utcnow() + dt.timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode: dict[str, Any] = {"sub": subject, "type": "refresh", "exp": expire}
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

