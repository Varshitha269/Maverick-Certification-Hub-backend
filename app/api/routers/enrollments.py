from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas.enrollment import EnrollmentCreate, EnrollmentOut, EnrollmentUpdate
from app.core.config import settings
from app.core.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.certification import Certification
from app.models.certification import CertificationDrive
from app.models.enrollment import Enrollment
from app.models.user import User, UserRole
from app.services.email_service import render_simple_email, send_email
from app.services.eligibility import check_eligibility
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

    if payload.drive_id is not None:
        drive = db.query(CertificationDrive).filter(CertificationDrive.id == payload.drive_id).first()
        if not drive:
            raise HTTPException(status_code=404, detail="Drive not found")
        if drive.certification_id != cert.id:
            raise HTTPException(status_code=400, detail="Drive does not belong to selected certification")
        elig = check_eligibility(user, drive.eligibility_rules)
        if not elig.eligible:
            raise HTTPException(status_code=403, detail=elig.reason or "Not eligible")

    existing = (
        db.query(Enrollment)
        .filter(Enrollment.user_id == user.id, Enrollment.certification_id == payload.certification_id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Already selected")

    enrollment = Enrollment(user_id=user.id, **payload.model_dump())
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)

    subject = "Certification selected"
    body = f"""
    You selected <b>{cert.title}</b> ({cert.provider}).<br/>
    Track your tasks and progress in your dashboard.
    """.strip()
    create_notification(
        db,
        user_id=user.id,
        type=NotificationType.enrollment,
        title=subject,
        message=f"You selected {cert.title} ({cert.provider}).",
        link_url=f"{settings.FRONTEND_BASE_URL}/dashboard",
    )
    html = render_simple_email(
        subject,
        body,
        action_url=f"{settings.FRONTEND_BASE_URL}/dashboard",
        action_text="Open dashboard",
        preheader=f"Selected: {cert.title}",
    )
    send_email(db, to_email=user.email, subject=subject, html_content=html, user_id=user.id)

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
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(enrollment, k, v)
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

