import enum

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.common import TimestampMixin


class AssessmentOutcome(str, enum.Enum):
    pass_ = "pass"
    fail = "fail"
    no_show = "no_show"
    pending = "pending"


class AssessmentResult(Base, TimestampMixin):
    __tablename__ = "assessment_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    registration_id: Mapped[int] = mapped_column(ForeignKey("registrations.id"), nullable=False, index=True)
    drive_id: Mapped[int] = mapped_column(ForeignKey("certification_drives.id"), nullable=False, index=True)

    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[AssessmentOutcome] = mapped_column(Enum(AssessmentOutcome), default=AssessmentOutcome.pending, nullable=False, index=True)
    assessed_on: Mapped[str | None] = mapped_column(String(40), nullable=True)  # keep string for compatibility with existing patterns

    evidence_upload_id: Mapped[int | None] = mapped_column(ForeignKey("uploaded_files.id"), nullable=True, index=True)
    evidence_url: Mapped[str | None] = mapped_column(String(800), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

