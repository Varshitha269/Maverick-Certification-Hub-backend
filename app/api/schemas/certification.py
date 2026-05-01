from pydantic import BaseModel, Field


class CertificationCreate(BaseModel):
    title: str = Field(max_length=240)
    provider: str = Field(max_length=160)
    level: str | None = Field(default=None, max_length=80)
    description: str | None = None
    estimated_hours: int | None = Field(default=None, ge=0)
    exam_cost: int | None = Field(default=None, ge=0)
    tags: str | None = Field(default=None, max_length=500)


class CertificationOut(CertificationCreate):
    id: int

    model_config = {"from_attributes": True}


class DriveCreate(BaseModel):
    certification_id: int
    name: str = Field(max_length=200)
    start_date: str | None = Field(default=None, max_length=40)
    end_date: str | None = Field(default=None, max_length=40)
    eligibility_rules: str | None = None
    voucher_budget: int | None = Field(default=None, ge=0)


class DriveOut(DriveCreate):
    id: int

    model_config = {"from_attributes": True}

