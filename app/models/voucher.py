import enum

from sqlalchemy import Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.common import TimestampMixin


class VoucherStatus(str, enum.Enum):
    issued = "issued"
    redeemed = "redeemed"
    expired = "expired"
    revoked = "revoked"


class Voucher(Base, TimestampMixin):
    __tablename__ = "vouchers"

    id: Mapped[int] = mapped_column(primary_key=True)
    drive_id: Mapped[int | None] = mapped_column(ForeignKey("certification_drives.id"), nullable=True, index=True)
    certification_id: Mapped[int | None] = mapped_column(ForeignKey("certifications.id"), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    code: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    status: Mapped[VoucherStatus] = mapped_column(Enum(VoucherStatus), default=VoucherStatus.issued, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


Index("ix_vouchers_user_status", Voucher.user_id, Voucher.status)

