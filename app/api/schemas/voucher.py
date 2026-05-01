from pydantic import BaseModel, Field

from app.models.voucher import VoucherStatus


class VoucherIssueRequest(BaseModel):
    user_id: int
    code: str = Field(max_length=120)
    drive_id: int | None = None
    certification_id: int | None = None
    notes: str | None = None


class VoucherUpdateRequest(BaseModel):
    status: VoucherStatus
    notes: str | None = None


class VoucherOut(BaseModel):
    id: int
    drive_id: int | None
    certification_id: int | None
    user_id: int
    code: str
    status: VoucherStatus
    notes: str | None

    model_config = {"from_attributes": True}

