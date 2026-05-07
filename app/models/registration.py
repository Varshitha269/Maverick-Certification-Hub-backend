import enum

from sqlalchemy import Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.common import TimestampMixin


class RegistrationStatus(str, enum.Enum):
    submitted = "submitted"
    eligible_pending_approval = "eligible_pending_approval"
    eligible = "eligible"
    ineligible = "ineligible"
    scheduled = "scheduled"
    assessed = "assessed"
    passed = "passed"
    failed = "failed"
    voucher_issued = "voucher_issued"
    closed = "closed"


class Registration(Base, TimestampMixin):
    """
    BRD Registration entity.
    This is intentionally separate from `Enrollment` to preserve existing flows.
    """

    __tablename__ = "registrations"

    id: Mapped[int] = mapped_column(primary_key=True)

    drive_id: Mapped[int] = mapped_column(ForeignKey("certification_drives.id"), nullable=False, index=True)

    # Candidate fields
    emp_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    candidate_name: Mapped[str] = mapped_column(String(200), nullable=False)
    candidate_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    bu: Mapped[str | None] = mapped_column(String(120), nullable=True)
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    manager_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    exam_track: Mapped[str | None] = mapped_column(String(160), nullable=True)
    slot: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prior_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    status: Mapped[RegistrationStatus] = mapped_column(
        Enum(RegistrationStatus), default=RegistrationStatus.submitted, nullable=False, index=True
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


Index("ix_registrations_drive_status", Registration.drive_id, Registration.status)
