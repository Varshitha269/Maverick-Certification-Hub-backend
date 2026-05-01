import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.db.session import get_db
from app.models.certification import Certification
from app.models.enrollment import Enrollment
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

