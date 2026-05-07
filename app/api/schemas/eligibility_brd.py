from pydantic import BaseModel, Field


class EligibilityEvaluateRequest(BaseModel):
    registration_id: int


class EligibilityEvaluationOut(BaseModel):
    id: int
    registration_id: int
    drive_id: int
    decision: str
    reason: str | None
    criteria_json: str | None
    evaluated_by: str

    model_config = {"from_attributes": True}


class ApprovalCreate(BaseModel):
    registration_id: int
    level: int = Field(default=1, ge=1, le=2)
    approver_email: str = Field(max_length=320)


class ApprovalDecision(BaseModel):
    status: str = Field(pattern="^(approved|rejected)$")
    decision_notes: str | None = None


class ApprovalOut(BaseModel):
    id: int
    registration_id: int
    drive_id: int
    level: int
    status: str
    approver_email: str
    requested_by_user_id: int | None
    decided_by_user_id: int | None
    decision_notes: str | None

    model_config = {"from_attributes": True}

