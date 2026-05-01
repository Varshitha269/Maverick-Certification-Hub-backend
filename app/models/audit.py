from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.common import TimestampMixin


class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    entity: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    ip: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)


Index("ix_audit_entity_entityid", AuditLog.entity, AuditLog.entity_id)

