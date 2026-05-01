import enum

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.common import TimestampMixin


class UploadPurpose(str, enum.Enum):
    certificate = "certificate"
    profile_doc = "profile_doc"
    other = "other"


class UploadedFile(Base, TimestampMixin):
    __tablename__ = "uploaded_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    enrollment_id: Mapped[int | None] = mapped_column(ForeignKey("enrollments.id"), nullable=True, index=True)

    purpose: Mapped[UploadPurpose] = mapped_column(Enum(UploadPurpose), default=UploadPurpose.other, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(260), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)

    storage_provider: Mapped[str] = mapped_column(String(40), default="azure_blob", nullable=False)
    blob_path: Mapped[str] = mapped_column(String(500), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user = relationship("User", back_populates="uploads")

