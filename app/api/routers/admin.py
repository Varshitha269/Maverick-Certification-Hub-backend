from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.schemas.user import AdminUserCreate, AdminUserUpdate, UserOut
from app.core.deps import require_role
from app.core.security import hash_password
from app.db.session import get_db
from app.models.certification import Certification
from app.models.audit import AuditLog
from app.models.email_log import EmailLog
from app.models.enrollment import Enrollment
from app.models.task import Task
from app.models.upload import UploadedFile
from app.models.user import User, UserRole
from app.services.audit_service import log_audit
from app.services.reminders import send_pending_and_overdue_reminders


router = APIRouter(dependencies=[Depends(require_role(UserRole.admin))])


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(User).order_by(User.created_at.desc()).all()


@router.post("/users", response_model=UserOut)
def create_user(payload: AdminUserCreate, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_role(UserRole.admin))):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        is_active=payload.is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log_audit(
        db,
        actor=admin,
        action="user.create",
        entity="user",
        entity_id=user.id,
        request=request,
        details={"email": user.email, "role": user.role.value, "is_active": user.is_active},
    )
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(user, k, v)
    db.add(user)
    db.commit()
    db.refresh(user)
    log_audit(
        db,
        actor=admin,
        action="user.update",
        entity="user",
        entity_id=user.id,
        request=request,
        details=payload.model_dump(exclude_unset=True),
    )
    return user


@router.get("/analytics")
def analytics(db: Session = Depends(get_db)):
    return {
        "users": db.query(func.count(User.id)).scalar() or 0,
        "certifications": db.query(func.count(Certification.id)).scalar() or 0,
        "enrollments": db.query(func.count(Enrollment.id)).scalar() or 0,
        "tasks": db.query(func.count(Task.id)).scalar() or 0,
        "uploads": db.query(func.count(UploadedFile.id)).scalar() or 0,
        "emails": db.query(func.count(EmailLog.id)).scalar() or 0,
    }


@router.post("/reminders/run")
def run_reminders(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_role(UserRole.admin))):
    result = send_pending_and_overdue_reminders(db)
    log_audit(db, actor=admin, action="reminders.run", entity="reminder_job", entity_id="default", request=request, details=result)
    return result


@router.get("/audit-logs")
def audit_logs(db: Session = Depends(get_db)):
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(200).all()
    return [
        {
            "id": r.id,
            "actor_user_id": r.actor_user_id,
            "action": r.action,
            "entity": r.entity,
            "entity_id": r.entity_id,
            "ip": r.ip,
            "created_at": r.created_at,
            "details_json": r.details_json,
        }
        for r in rows
    ]


@router.get("/email-logs")
def email_logs(db: Session = Depends(get_db)):
    rows = db.query(EmailLog).order_by(EmailLog.created_at.desc()).limit(200).all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "to_email": r.to_email,
            "subject": r.subject,
            "success": r.success,
            "error": r.error,
            "created_at": r.created_at,
        }
        for r in rows
    ]

