import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.db.session import get_db
from app.models.certification import Certification
from app.models.eligibility import EligibilityTestAttempt
from app.models.enrollment import Enrollment
from app.models.registration import Registration
from app.models.user import User, UserRole
from app.services.audit_service import log_audit
from app.services.storage_service import get_blob_url, try_generate_sas_url, upload_bytes


router = APIRouter(dependencies=[Depends(require_role(UserRole.admin))])


@router.post("/enrollments")
def export_enrollments(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_role(UserRole.admin))):
    rows = db.query(Enrollment).order_by(Enrollment.created_at.desc()).all()
    cert_map = {c.id: c for c in db.query(Certification).all()}
    user_map = {u.id: u for u in db.query(User).all()}

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "enrollment_id",
            "user_id",
            "user_email",
            "certification_id",
            "certification_title",
            "provider",
            "drive_id",
            "status",
            "progress_percent",
            "target_completion_date",
            "created_at",
        ]
    )
    for e in rows:
        u = user_map.get(e.user_id)
        c = cert_map.get(e.certification_id)
        w.writerow(
            [
                e.id,
                e.user_id,
                (u.email if u else ""),
                e.certification_id,
                (c.title if c else ""),
                (c.provider if c else ""),
                e.drive_id or "",
                e.status.value,
                e.progress_percent,
                e.target_completion_date or "",
                e.created_at.isoformat() if e.created_at else "",
            ]
        )

    data = buf.getvalue().encode("utf-8")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    obj = upload_bytes(data=data, content_type="text/csv", filename=f"enrollments-{ts}.csv", user_id=admin.id, purpose="exports")

    sas = try_generate_sas_url(obj.blob_path, expires_in_minutes=30)
    url = sas or get_blob_url(obj.blob_path)

    log_audit(
        db,
        actor=admin,
        action="export.enrollments",
        entity="export",
        entity_id=obj.blob_path,
        request=request,
        details={"rows": len(rows), "blob_path": obj.blob_path, "signed": bool(sas)},
    )
    return {"blob_path": obj.blob_path, "url": url, "signed": bool(sas)}


@router.get("/users")
def export_users(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_role(UserRole.admin))):
    users = db.query(User).order_by(User.created_at.desc()).all()
    cert_map = {c.id: c for c in db.query(Certification).all()}
    enrollments = db.query(Enrollment).all()
    registrations = db.query(Registration).all()
    attempts = db.query(EligibilityTestAttempt).all()

    enrollments_by_user: dict[int, list[Enrollment]] = {}
    for enrollment in enrollments:
        enrollments_by_user.setdefault(enrollment.user_id, []).append(enrollment)

    registrations_by_email: dict[str, list[Registration]] = {}
    for registration in registrations:
        registrations_by_email.setdefault(registration.candidate_email.lower(), []).append(registration)

    attempts_by_user: dict[int, list[EligibilityTestAttempt]] = {}
    for attempt in attempts:
        attempts_by_user.setdefault(attempt.user_id, []).append(attempt)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "user_id",
            "email",
            "full_name",
            "role",
            "active",
            "registered_at",
            "registration_ids",
            "registration_statuses",
            "registration_drive_ids",
            "enrollment_ids",
            "enrolled_certification_ids",
            "enrolled_certifications",
            "enrollment_statuses",
            "eligibility_attempt_ids",
            "eligibility_certifications",
            "eligibility_scores",
            "eligibility_passed",
        ]
    )
    for user in users:
        user_enrollments = enrollments_by_user.get(user.id, [])
        user_regs = registrations_by_email.get(user.email.lower(), [])
        user_attempts = attempts_by_user.get(user.id, [])
        w.writerow(
            [
                user.id,
                user.email,
                user.full_name or "",
                user.role.value if hasattr(user.role, "value") else str(user.role),
                user.is_active,
                user.created_at.isoformat() if user.created_at else "",
                ";".join(str(r.id) for r in user_regs),
                ";".join(r.status.value if hasattr(r.status, "value") else str(r.status) for r in user_regs),
                ";".join(str(r.drive_id) for r in user_regs),
                ";".join(str(e.id) for e in user_enrollments),
                ";".join(str(e.certification_id) for e in user_enrollments),
                ";".join((cert_map.get(e.certification_id).title if cert_map.get(e.certification_id) else "") for e in user_enrollments),
                ";".join(e.status.value if hasattr(e.status, "value") else str(e.status) for e in user_enrollments),
                ";".join(str(a.id) for a in user_attempts),
                ";".join((cert_map.get(a.certification_id).title if cert_map.get(a.certification_id) else "") for a in user_attempts),
                ";".join(str(a.score) for a in user_attempts),
                ";".join("yes" if a.passed else "no" for a in user_attempts),
            ]
        )

    log_audit(
        db,
        actor=admin,
        action="export.users",
        entity="export",
        entity_id="users",
        request=request,
        details={"rows": len(users)},
    )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue().encode("utf-8")]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="users-certification-activity.csv"'},
    )

