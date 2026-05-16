import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.schemas.registration_brd import RegistrationCreate, RegistrationOut, RegistrationUpdate
from app.core.config import settings
from app.core.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.certification import CertificationDrive
from app.models.certification import Certification
from app.models.registration import Registration, RegistrationStatus
from app.models.user import User, UserRole
from app.services.audit_service import log_audit
from app.services.email_service import render_simple_email, send_email
from app.services.notification_service import notify_admins


router = APIRouter()


def _registration_to_out(db: Session, row: Registration) -> dict:
    drive = db.query(CertificationDrive).filter(CertificationDrive.id == row.drive_id).first()
    cert = db.query(Certification).filter(Certification.id == drive.certification_id).first() if drive else None
    return {
        "id": row.id,
        "drive_id": row.drive_id,
        "drive_name": drive.name if drive else None,
        "certification_id": cert.id if cert else None,
        "certification_title": cert.title if cert else None,
        "certification_provider": cert.provider if cert else None,
        "emp_id": row.emp_id,
        "candidate_name": row.candidate_name,
        "candidate_email": row.candidate_email,
        "bu": row.bu,
        "location": row.location,
        "manager_email": row.manager_email,
        "exam_track": row.exam_track,
        "slot": row.slot,
        "prior_attempts": row.prior_attempts,
        "status": row.status.value if hasattr(row.status, "value") else str(row.status),
        "notes": row.notes,
    }


@router.post("/", response_model=RegistrationOut)
def create_registration(
    payload: RegistrationCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    drive = db.query(CertificationDrive).filter(CertificationDrive.id == payload.drive_id).first()
    if not drive:
        raise HTTPException(status_code=404, detail="Drive not found")

    row = Registration(
        drive_id=payload.drive_id,
        emp_id=payload.emp_id,
        candidate_name=payload.candidate_name,
        candidate_email=str(payload.candidate_email),
        bu=payload.bu,
        location=payload.location,
        manager_email=str(payload.manager_email) if payload.manager_email else None,
        exam_track=payload.exam_track,
        slot=payload.slot,
        prior_attempts=payload.prior_attempts,
        status=RegistrationStatus.submitted,
        notes=payload.notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    # SLA-friendly auto-ack (best-effort)
    subject = f"Registration received: {drive.name}"
    body = f"""
    Hi {row.candidate_name},<br/>
    We received your registration for <b>{drive.name}</b>.<br/>
    You can track your status in the portal.
    """.strip()
    html = render_simple_email(
        subject,
        body,
        action_url=f"{settings.FRONTEND_BASE_URL}/dashboard",
        action_text="Open portal",
        preheader="Registration received",
    )
    send_email(db, to_email=row.candidate_email, subject=subject, html_content=html, user_id=user.id)
    notify_admins(
        db,
        title="New drive registration",
        message=f"{row.candidate_name} ({row.candidate_email}) registered for {drive.name}.",
        link_url=f"/admin-brd/registrations?drive_id={drive.id}",
        icon="applications",
    )

    log_audit(
        db,
        actor=user,
        action="registration.create",
        entity="registration",
        entity_id=row.id,
        request=request,
        details={"drive_id": row.drive_id, "candidate_email": row.candidate_email},
    )
    return row


@router.get("/me", response_model=list[RegistrationOut])
def my_registrations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return (
        db.query(Registration)
        .filter(Registration.candidate_email == user.email)
        .order_by(Registration.created_at.desc())
        .all()
    )


@router.get("/open-drives")
def open_drives(db: Session = Depends(get_db), user: User = Depends(get_current_user)):  # noqa: ARG001
    rows = (
        db.query(CertificationDrive)
        .filter(CertificationDrive.status == "open")
        .order_by(CertificationDrive.start_date.desc(), CertificationDrive.created_at.desc())
        .limit(100)
        .all()
    )
    result = []
    for drive in rows:
        cert = db.query(Certification).filter(Certification.id == drive.certification_id).first()
        result.append(
            {
                "id": drive.id,
                "name": drive.name,
                "certification_id": drive.certification_id,
                "certification_title": cert.title if cert else None,
                "certification_provider": cert.provider if cert else None,
                "certification_category": cert.category if cert else None,
                "start_date": drive.start_date,
                "end_date": drive.end_date,
                "voucher_budget": drive.voucher_budget,
                "target_count": drive.target_count,
                "sponsor": drive.sponsor,
            }
        )
    return result


@router.get("/", response_model=list[RegistrationOut])
def admin_list_registrations(
    drive_id: int | None = None,
    status: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):  # noqa: ARG001
    query = db.query(Registration)
    if drive_id is not None:
        query = query.filter(Registration.drive_id == drive_id)
    if status is not None:
        query = query.filter(Registration.status == status)
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.filter(
            (Registration.candidate_email.ilike(like))
            | (Registration.candidate_name.ilike(like))
            | (Registration.emp_id.ilike(like))
        )
    rows = query.order_by(Registration.created_at.desc()).limit(1000).all()
    return [_registration_to_out(db, row) for row in rows]


@router.patch("/{registration_id}", response_model=RegistrationOut)
def admin_update_registration(
    registration_id: int,
    payload: RegistrationUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    row = db.query(Registration).filter(Registration.id == registration_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Registration not found")
    before = {"status": row.status.value if row.status else None, "notes": row.notes}
    if payload.status is not None:
        try:
            row.status = RegistrationStatus(payload.status)
        except Exception:  # noqa: BLE001
            row.status = RegistrationStatus.submitted
    if payload.notes is not None:
        row.notes = payload.notes
    db.add(row)
    db.commit()
    db.refresh(row)
    subject = f"Registration updated: #{row.id}"
    body = f"""
    Your registration status was updated to <b>{row.status.value}</b>.<br/>
    {row.notes or ""}
    """.strip()
    html = render_simple_email(
        subject,
        body,
        action_url=f"{settings.FRONTEND_BASE_URL}/registrations",
        action_text="Open registrations",
        preheader=subject,
    )
    send_email(db, to_email=row.candidate_email, subject=subject, html_content=html)
    notify_admins(
        db,
        title="Admin updated registration",
        message=f"{admin.email} updated registration #{row.id} for {row.candidate_email} to {row.status.value}.",
        link_url=f"/admin-brd/registrations?drive_id={row.drive_id}",
        icon="applications",
    )
    log_audit(
        db,
        actor=admin,
        action="registration.update",
        entity="registration",
        entity_id=row.id,
        request=request,
        details={"before": before, "after": {"status": row.status.value, "notes": row.notes}},
    )
    return row


@router.get("/status/lookup")
def status_lookup(
    reg_id: int | None = None,
    email: str | None = None,
    emp_id: str | None = None,
    db: Session = Depends(get_db),
):
    """
    BRD FR-6: status lookup via portal.
    (Email keyword handling can be added later.)
    """
    q = db.query(Registration)
    if reg_id is not None:
        q = q.filter(Registration.id == reg_id)
    if email is not None:
        q = q.filter(Registration.candidate_email == email)
    if emp_id is not None:
        q = q.filter(Registration.emp_id == emp_id)
    rows = q.order_by(Registration.created_at.desc()).limit(50).all()
    return {
        "count": len(rows),
        "items": [
            {
                "id": r.id,
                "drive_id": r.drive_id,
                "status": r.status.value if r.status else None,
                "candidate_email": r.candidate_email,
                "updated_at": r.updated_at,
            }
            for r in rows
        ],
        "generated_at": dt.datetime.now(dt.timezone.utc),
    }

