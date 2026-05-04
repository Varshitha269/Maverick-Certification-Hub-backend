from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas.enrollment import EnrollmentCreate, EnrollmentOut, EnrollmentUpdate
from app.core.config import settings
from app.core.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.certification import Certification
from app.models.certification import CertificationDrive
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.user import User, UserRole
from app.models.task import Task, TaskStatus
from app.services.email_service import render_simple_email, send_email
from app.services.notification_service import create_notification
from app.models.notification import NotificationType


router = APIRouter()


@router.get("/me", response_model=list[EnrollmentOut])
def my_enrollments(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Enrollment).filter(Enrollment.user_id == user.id).order_by(Enrollment.created_at.desc()).all()


@router.post("/me", response_model=EnrollmentOut)
def select_certification(payload: EnrollmentCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cert = db.query(Certification).filter(Certification.id == payload.certification_id).first()
    if not cert:
        raise HTTPException(status_code=404, detail="Certification not found")

    # No eligibility check — anyone can enroll or save for later

    existing = (
        db.query(Enrollment)
        .filter(Enrollment.user_id == user.id, Enrollment.certification_id == payload.certification_id)
        .first()
    )
    if existing:
        # If they previously saved for later and now want to enroll, upgrade the status
        if existing.status == EnrollmentStatus.saved_for_later and payload.status == EnrollmentStatus.selected:
            existing.status = EnrollmentStatus.selected
            db.add(existing)
            db.commit()
            db.refresh(existing)
            
            # Send notification for upgrading to enrolled
            create_notification(
                db,
                user_id=user.id,
                type=NotificationType.enrollment,
                title="Application Approved",
                message=f"You have officially enrolled in {cert.title} ({cert.provider}).",
                link_url=f"{settings.FRONTEND_BASE_URL}/learning/{existing.id}",
            )
            return existing
        raise HTTPException(status_code=400, detail="Already enrolled in this certification")

    enrollment = Enrollment(
        user_id=user.id,
        certification_id=payload.certification_id,
        drive_id=payload.drive_id,
        status=payload.status,
        target_completion_date=payload.target_completion_date,
        notes=payload.notes,
    )
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)

    # Create notification based on status
    is_saved = payload.status == EnrollmentStatus.saved_for_later
    
    subject = "Certification Saved" if is_saved else "Application Approved"
    message_text = (
        f"You saved {cert.title} to review later." if is_saved 
        else f"You have officially enrolled in {cert.title} ({cert.provider})."
    )
    
    create_notification(
        db,
        user_id=user.id,
        type=NotificationType.enrollment,
        title=subject,
        message=message_text,
        link_url=f"{settings.FRONTEND_BASE_URL}/dashboard",
    )
    
    # Send email only for actual enrollment
    if not is_saved:
        body = f"""
        You selected <b>{cert.title}</b> ({cert.provider}).<br/>
        Track your tasks and progress in your dashboard.
        """.strip()
        html = render_simple_email(
            subject,
            body,
            action_url=f"{settings.FRONTEND_BASE_URL}/dashboard",
            action_text="Open dashboard",
            preheader=f"Selected: {cert.title}",
        )
        send_email(db, to_email=user.email, subject=subject, html_content=html, user_id=user.id)

    return enrollment


@router.get("/me/{enrollment_id}", response_model=EnrollmentOut)
def get_my_enrollment(enrollment_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    enrollment = db.query(Enrollment).filter(Enrollment.id == enrollment_id, Enrollment.user_id == user.id).first()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    return enrollment


@router.patch("/me/{enrollment_id}", response_model=EnrollmentOut)
def update_my_enrollment(
    enrollment_id: int,
    payload: EnrollmentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    enrollment = db.query(Enrollment).filter(Enrollment.id == enrollment_id, Enrollment.user_id == user.id).first()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")
        
    was_completed = enrollment.status == EnrollmentStatus.completed
    
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(enrollment, k, v)
        
    # If it is newly marked as completed, autocomplete all related tasks
    if not was_completed and enrollment.status == EnrollmentStatus.completed:
        tasks = db.query(Task).filter(Task.enrollment_id == enrollment.id).all()
        for t in tasks:
            t.status = TaskStatus.done
            db.add(t)

    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    return enrollment


@router.get("/", response_model=list[EnrollmentOut])
def admin_list_enrollments(
    user_id: int | None = None,
    certification_id: int | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    q = db.query(Enrollment)
    if user_id is not None:
        q = q.filter(Enrollment.user_id == user_id)
    if certification_id is not None:
        q = q.filter(Enrollment.certification_id == certification_id)
    return q.order_by(Enrollment.created_at.desc()).all()
