from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.common import TimestampMixin


class Certification(Base, TimestampMixin):
    __tablename__ = "certifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    level: Mapped[str | None] = mapped_column(String(80), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exam_cost: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tags: Mapped[str | None] = mapped_column(String(500), nullable=True)  # comma-separated
    category: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    duration: Mapped[str | None] = mapped_column(String(80), nullable=True)  # e.g. "3 months"
    prerequisites: Mapped[str | None] = mapped_column(Text, nullable=True)  # newline-separated list
    course_url: Mapped[str | None] = mapped_column(String(800), nullable=True)   # primary course link (Udemy/YT)
    official_exam_url: Mapped[str | None] = mapped_column(String(800), nullable=True)  # official exam registration
    resources_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: [{label,url,type,icon}]
    badge_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)  # Official badge graphic

    drives = relationship("CertificationDrive", back_populates="certification", cascade="all, delete-orphan")
    enrollments = relationship("Enrollment", back_populates="certification", cascade="all, delete-orphan")


class CertificationDrive(Base, TimestampMixin):
    __tablename__ = "certification_drives"

    id: Mapped[int] = mapped_column(primary_key=True)
    certification_id: Mapped[int] = mapped_column(ForeignKey("certifications.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    start_date: Mapped[str | None] = mapped_column(String(40), nullable=True)
    end_date: Mapped[str | None] = mapped_column(String(40), nullable=True)
    eligibility_rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    voucher_budget: Mapped[int | None] = mapped_column(Integer, nullable=True)

    certification = relationship("Certification", back_populates="drives")
    enrollments = relationship("Enrollment", back_populates="drive", cascade="all, delete-orphan")
