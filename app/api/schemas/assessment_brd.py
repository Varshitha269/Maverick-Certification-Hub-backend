from pydantic import BaseModel, Field


class AssessmentCreate(BaseModel):
    registration_id: int
    score: int | None = Field(default=None, ge=0)
    outcome: str = Field(default="pending")  # pass/fail/no_show/pending
    assessed_on: str | None = Field(default=None, max_length=40)
    evidence_upload_id: int | None = None
    evidence_url: str | None = Field(default=None, max_length=800)
    notes: str | None = None


class AssessmentOut(BaseModel):
    id: int
    registration_id: int
    drive_id: int
    score: int | None
    outcome: str
    assessed_on: str | None
    evidence_upload_id: int | None
    evidence_url: str | None
    notes: str | None

    model_config = {"from_attributes": True}

