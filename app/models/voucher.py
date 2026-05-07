import enum
from datetime import timedelta

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

    # BRD security & tracking additions (keep `code` for backward compatibility)
    masked_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    code_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_registration_id: Mapped[int | None] = mapped_column(ForeignKey("registrations.id"), nullable=True, index=True)
    delivered_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    redeemed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    revoked_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    delivery_token_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)

    @property
    def expires_at(self) -> str | None:
        if not self.created_at:
            return None
        return (self.created_at + timedelta(days=90)).isoformat()


Index("ix_vouchers_user_status", Voucher.user_id, Voucher.status)

