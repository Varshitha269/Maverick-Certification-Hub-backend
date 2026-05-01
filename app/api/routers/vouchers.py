from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.schemas.voucher import VoucherIssueRequest, VoucherOut, VoucherUpdateRequest
from app.core.config import settings
from app.core.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.voucher import Voucher
from app.models.notification import NotificationType
from app.services.audit_service import log_audit
from app.services.email_service import render_simple_email, send_email
from app.services.notification_service import create_notification


router = APIRouter()


@router.get("/me", response_model=list[VoucherOut])
def my_vouchers(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Voucher).filter(Voucher.user_id == user.id).order_by(Voucher.created_at.desc()).all()


@router.get("/", response_model=list[VoucherOut])
def admin_list_vouchers(
    user_id: int | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    q = db.query(Voucher)
    if user_id is not None:
        q = q.filter(Voucher.user_id == user_id)
    return q.order_by(Voucher.created_at.desc()).limit(500).all()


@router.post("/", response_model=VoucherOut)
def admin_issue_voucher(
    payload: VoucherIssueRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    existing = db.query(Voucher).filter(Voucher.code == payload.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Voucher code already exists")

    target = db.query(User).filter(User.id == payload.user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    row = Voucher(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)

    title = "Voucher issued"
    msg = f"A voucher has been issued to you: <b>{row.code}</b>."
    create_notification(
        db,
        user_id=target.id,
        type=NotificationType.voucher,
        title=title,
        message=f"Voucher issued: {row.code}",
        link_url=f"{settings.FRONTEND_BASE_URL}/dashboard",
    )
    html = render_simple_email(title, msg, action_url=f"{settings.FRONTEND_BASE_URL}/dashboard", action_text="Open dashboard", preheader="Voucher issued")
    send_email(db, to_email=target.email, subject=title, html_content=html, user_id=target.id)

    log_audit(
        db,
        actor=admin,
        action="voucher.issue",
        entity="voucher",
        entity_id=row.id,
        request=request,
        details={"user_id": target.id, "code": row.code, "drive_id": row.drive_id, "certification_id": row.certification_id},
    )
    return row


@router.patch("/{voucher_id}", response_model=VoucherOut)
def admin_update_voucher(
    voucher_id: int,
    payload: VoucherUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    row = db.query(Voucher).filter(Voucher.id == voucher_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Voucher not found")
    row.status = payload.status
    if payload.notes is not None:
        row.notes = payload.notes
    db.add(row)
    db.commit()
    db.refresh(row)

    log_audit(
        db,
        actor=admin,
        action="voucher.update",
        entity="voucher",
        entity_id=row.id,
        request=request,
        details={"status": row.status.value},
    )
    return row

