import enum

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.common import TimestampMixin


class EnrollmentStatus(str, enum.Enum):
    selected = "selected"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class Enrollment(Base, TimestampMixin):
    __tablename__ = "enrollments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    certification_id: Mapped[int] = mapped_column(ForeignKey("certifications.id"), nullable=False, index=True)
    drive_id: Mapped[int | None] = mapped_column(ForeignKey("certification_drives.id"), nullable=True, index=True)

    status: Mapped[EnrollmentStatus] = mapped_column(Enum(EnrollmentStatus), default=EnrollmentStatus.selected, nullable=False)
    target_completion_date: Mapped[str | None] = mapped_column(String(40), nullable=True)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    user = relationship("User", back_populates="enrollments")
    certification = relationship("Certification", back_populates="enrollments")
    drive = relationship("CertificationDrive", back_populates="enrollments")

