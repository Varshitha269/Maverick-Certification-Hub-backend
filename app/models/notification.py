import datetime as dt
import enum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.common import TimestampMixin


class NotificationType(str, enum.Enum):
    system = "system"
    enrollment = "enrollment"
    reminder = "reminder"
    voucher = "voucher"


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    type: Mapped[NotificationType] = mapped_column(Enum(NotificationType), default=NotificationType.system, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    link_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(20), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(800), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(80), nullable=True)
    scheduled_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    audience: Mapped[str | None] = mapped_column(String(80), nullable=True)
    content_format: Mapped[str] = mapped_column(String(20), default="plain", nullable=False)

    read_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


Index("ix_notifications_user_read", Notification.user_id, Notification.read_at)

