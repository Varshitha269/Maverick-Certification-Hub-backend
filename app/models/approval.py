import enum

from sqlalchemy import Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.common import TimestampMixin


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


class Approval(Base, TimestampMixin):
    """
    Generic approval record for BRD 1–2 level approval workflows.
    """

    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True)

    registration_id: Mapped[int] = mapped_column(ForeignKey("registrations.id"), nullable=False, index=True)
    drive_id: Mapped[int] = mapped_column(ForeignKey("certification_drives.id"), nullable=False, index=True)

    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(Enum(ApprovalStatus), default=ApprovalStatus.pending, nullable=False, index=True)

    requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    approver_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)

    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)


Index("ix_approvals_drive_level_status", Approval.drive_id, Approval.level, Approval.status)
