from pydantic import BaseModel, Field

from app.models.task import TaskStatus


class TaskCreate(BaseModel):
    enrollment_id: int | None = None
    title: str = Field(max_length=240)
    description: str | None = None
    status: TaskStatus = TaskStatus.todo
    due_date: str | None = Field(default=None, max_length=40)
    priority: int = Field(default=3, ge=1, le=5)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=240)
    description: str | None = None
    status: TaskStatus | None = None
    due_date: str | None = Field(default=None, max_length=40)
    priority: int | None = Field(default=None, ge=1, le=5)


class TaskOut(BaseModel):
    id: int
    user_id: int
    enrollment_id: int | None
    title: str
    description: str | None
    status: TaskStatus
    due_date: str | None
    priority: int

    model_config = {"from_attributes": True}

