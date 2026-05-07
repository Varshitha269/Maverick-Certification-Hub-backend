from pydantic import BaseModel, Field


class DriveBRDUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    start_date: str | None = Field(default=None, max_length=40)
    end_date: str | None = Field(default=None, max_length=40)
    eligibility_rules: str | None = None
    voucher_budget: int | None = Field(default=None, ge=0)
    sponsor: str | None = Field(default=None, max_length=200)
    owner_email: str | None = Field(default=None, max_length=320)
    policy_url: str | None = Field(default=None, max_length=800)
    target_count: int | None = Field(default=None, ge=0)
    status: str | None = Field(default=None, max_length=40)  # open/closed
    repository_prefix: str | None = Field(default=None, max_length=300)


class DriveBRDOut(BaseModel):
    id: int
    certification_id: int
    certification_title: str | None = None
    certification_provider: str | None = None
    certification_category: str | None = None
    name: str
    start_date: str | None
    end_date: str | None
    eligibility_rules: str | None
    voucher_budget: int | None
    sponsor: str | None
    owner_email: str | None
    policy_url: str | None
    target_count: int | None
    status: str
    repository_prefix: str | None
    registrations_count: int = 0
    assessed_count: int = 0
    passed_count: int = 0
    failed_count: int = 0
    voucher_count: int = 0
    last_conducted_date: str | None = None
    can_conduct: bool = True
    can_reconduct: bool = False
    next_action: str | None = None

    model_config = {"from_attributes": True}

