import enum

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.common import TimestampMixin


class TaskStatus(str, enum.Enum):
    todo = "todo"
    doing = "doing"
    done = "done"
    blocked = "blocked"


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    enrollment_id: Mapped[int | None] = mapped_column(ForeignKey("enrollments.id"), nullable=True, index=True)

    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.todo, nullable=False)
    due_date: Mapped[str | None] = mapped_column(String(40), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=3, nullable=False)  # 1-high,5-low

    user = relationship("User", back_populates="tasks")

