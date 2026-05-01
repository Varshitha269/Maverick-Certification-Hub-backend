from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas.task import TaskCreate, TaskOut, TaskUpdate
from app.core.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.task import Task
from app.models.user import User, UserRole


router = APIRouter()


@router.get("/me", response_model=list[TaskOut])
def my_tasks(
    enrollment_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Task).filter(Task.user_id == user.id)
    if enrollment_id is not None:
        q = q.filter(Task.enrollment_id == enrollment_id)
    return q.order_by(Task.created_at.desc()).all()


@router.post("/me", response_model=TaskOut)
def create_task(payload: TaskCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = Task(user_id=user.id, **payload.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.patch("/me/{task_id}", response_model=TaskOut)
def update_task(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(task, k, v)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.delete("/me/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
    return {"ok": True}


@router.get("/", response_model=list[TaskOut])
def admin_list_tasks(
    user_id: int | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    q = db.query(Task)
    if user_id is not None:
        q = q.filter(Task.user_id == user_id)
    return q.order_by(Task.created_at.desc()).all()

