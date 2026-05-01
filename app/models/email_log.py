from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.common import TimestampMixin


class EmailLog(Base, TimestampMixin):
    __tablename__ = "email_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    to_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str] = mapped_column(String(40), default="sendgrid", nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

