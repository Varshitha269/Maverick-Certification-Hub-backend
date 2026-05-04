from datetime import datetime
from pydantic import BaseModel, Field

from app.models.enrollment import EnrollmentStatus


class EnrollmentCreate(BaseModel):
    certification_id: int
    drive_id: int | None = None
    status: EnrollmentStatus = EnrollmentStatus.selected
    target_completion_date: str | None = Field(default=None, max_length=40)
    notes: str | None = None


class EnrollmentUpdate(BaseModel):
    status: EnrollmentStatus | None = None
    target_completion_date: str | None = Field(default=None, max_length=40)
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    admin_review_requested: bool | None = None
    notes: str | None = None


class EnrollmentOut(BaseModel):
    id: int
    user_id: int
    certification_id: int
    drive_id: int | None
    status: EnrollmentStatus
    target_completion_date: str | None
    progress_percent: int
    admin_review_requested: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}
