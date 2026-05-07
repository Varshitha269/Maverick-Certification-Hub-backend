import enum

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.common import TimestampMixin


class EligibilityDecision(str, enum.Enum):
    eligible = "eligible"
    ineligible = "ineligible"
    needs_approval = "needs_approval"


class EligibilityEvaluation(Base, TimestampMixin):
    __tablename__ = "eligibility_evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    registration_id: Mapped[int] = mapped_column(ForeignKey("registrations.id"), nullable=False, index=True)
    drive_id: Mapped[int] = mapped_column(ForeignKey("certification_drives.id"), nullable=False, index=True)

    decision: Mapped[EligibilityDecision] = mapped_column(Enum(EligibilityDecision), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # JSON string: inputs/rule results for auditability
    criteria_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluated_by: Mapped[str] = mapped_column(String(40), default="rules_engine", nullable=False)  # rules_engine/manual


class EligibilityTestAttempt(Base, TimestampMixin):
    __tablename__ = "eligibility_test_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    certification_id: Mapped[int] = mapped_column(ForeignKey("certifications.id"), nullable=False, index=True)

    score: Mapped[int] = mapped_column(Integer, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), default="review_required", nullable=False, index=True)
    answers_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

