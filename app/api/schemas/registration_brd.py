from pydantic import BaseModel, EmailStr, Field


class RegistrationCreate(BaseModel):
    drive_id: int
    emp_id: str | None = Field(default=None, max_length=80)
    candidate_name: str = Field(max_length=200)
    candidate_email: EmailStr
    bu: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=120)
    manager_email: EmailStr | None = None
    exam_track: str | None = Field(default=None, max_length=160)
    slot: str | None = Field(default=None, max_length=120)
    prior_attempts: int = Field(default=0, ge=0)
    notes: str | None = None


class RegistrationUpdate(BaseModel):
    status: str | None = Field(default=None, max_length=40)
    notes: str | None = None


class RegistrationOut(BaseModel):
    id: int
    drive_id: int
    drive_name: str | None = None
    certification_id: int | None = None
    certification_title: str | None = None
    certification_provider: str | None = None
    emp_id: str | None
    candidate_name: str
    candidate_email: EmailStr
    bu: str | None
    location: str | None
    manager_email: EmailStr | None
    exam_track: str | None
    slot: str | None
    prior_attempts: int
    status: str
    notes: str | None

    model_config = {"from_attributes": True}

