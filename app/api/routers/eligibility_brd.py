import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.schemas.eligibility_brd import (
    ApprovalCreate,
    ApprovalDecision,
    ApprovalOut,
    EligibilityEvaluateRequest,
    EligibilityEvaluationOut,
)
from app.core.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.approval import Approval, ApprovalStatus
from app.models.certification import CertificationDrive
from app.models.eligibility import EligibilityDecision, EligibilityEvaluation
from app.models.registration import Registration, RegistrationStatus
from app.models.user import User, UserRole
from app.services.audit_service import log_audit
from app.services.eligibility import check_eligibility


router = APIRouter()


@router.post("/evaluate", response_model=EligibilityEvaluationOut)
def evaluate_eligibility(
    payload: EligibilityEvaluateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    reg = db.query(Registration).filter(Registration.id == payload.registration_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail="Registration not found")
    drive = db.query(CertificationDrive).filter(CertificationDrive.id == reg.drive_id).first()
    if not drive:
        raise HTTPException(status_code=404, detail="Drive not found")

    # Use existing rules engine (user-based) where possible; we map candidate email to a user if present.
    user = db.query(User).filter(User.email == reg.candidate_email).first()
    if user:
        elig = check_eligibility(user, drive.eligibility_rules)
        decision = EligibilityDecision.eligible if elig.eligible else EligibilityDecision.ineligible
        reason = elig.reason
        criteria_json = json.dumps({"user_id": user.id, "email": user.email, "rules": drive.eligibility_rules})
    else:
        decision = EligibilityDecision.needs_approval if drive.eligibility_rules else EligibilityDecision.eligible
        reason = None if decision == EligibilityDecision.eligible else "User not found; manual approval required"
        criteria_json = json.dumps({"email": reg.candidate_email, "rules": drive.eligibility_rules})

    ev = EligibilityEvaluation(
        registration_id=reg.id,
        drive_id=drive.id,
        decision=decision,
        reason=reason,
        criteria_json=criteria_json,
        evaluated_by="rules_engine",
    )
    db.add(ev)

    # Update registration status
    if decision == EligibilityDecision.eligible:
        reg.status = RegistrationStatus.eligible
    elif decision == EligibilityDecision.ineligible:
        reg.status = RegistrationStatus.ineligible
    else:
        reg.status = RegistrationStatus.eligible_pending_approval
    db.add(reg)
    if decision == EligibilityDecision.needs_approval:
        existing_pending = (
            db.query(Approval)
            .filter(Approval.registration_id == reg.id, Approval.status == ApprovalStatus.pending)
            .first()
        )
        if not existing_pending:
            db.add(
                Approval(
                    registration_id=reg.id,
                    drive_id=drive.id,
                    level=1,
                    status=ApprovalStatus.pending,
                    requested_by_user_id=admin.id,
                    approver_email=reg.manager_email or drive.owner_email or admin.email,
                )
            )
    db.commit()
    db.refresh(ev)

    log_audit(
        db,
        actor=admin,
        action="eligibility.evaluate",
        entity="registration",
        entity_id=reg.id,
        request=request,
        details={"decision": decision.value, "reason": reason},
    )
    return ev


@router.post("/approvals", response_model=ApprovalOut)
def create_approval(
    payload: ApprovalCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    reg = db.query(Registration).filter(Registration.id == payload.registration_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail="Registration not found")
    row = Approval(
        registration_id=reg.id,
        drive_id=reg.drive_id,
        level=payload.level,
        status=ApprovalStatus.pending,
        requested_by_user_id=admin.id,
        approver_email=payload.approver_email,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log_audit(
        db,
        actor=admin,
        action="approval.create",
        entity="approval",
        entity_id=row.id,
        request=request,
        details={"registration_id": reg.id, "level": row.level, "approver_email": row.approver_email},
    )
    return row


@router.get("/approvals", response_model=list[ApprovalOut])
def list_approvals(
    status: str | None = None,
    drive_id: int | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):  # noqa: ARG001
    q = db.query(Approval)
    if drive_id is not None:
        q = q.filter(Approval.drive_id == drive_id)
    if status is not None:
        q = q.filter(Approval.status == status)
    return q.order_by(Approval.created_at.desc()).limit(1000).all()


@router.post("/approvals/{approval_id}/decide", response_model=ApprovalOut)
def decide_approval(
    approval_id: int,
    payload: ApprovalDecision,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    row = db.query(Approval).filter(Approval.id == approval_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Approval not found")
    if row.status != ApprovalStatus.pending:
        raise HTTPException(status_code=400, detail="Approval is not pending")
    row.status = ApprovalStatus.approved if payload.status == "approved" else ApprovalStatus.rejected
    row.decision_notes = payload.decision_notes
    row.decided_by_user_id = admin.id
    db.add(row)

    reg = db.query(Registration).filter(Registration.id == row.registration_id).first()
    if reg:
        reg.status = RegistrationStatus.eligible if row.status == ApprovalStatus.approved else RegistrationStatus.ineligible
        db.add(reg)

    db.commit()
    db.refresh(row)
    log_audit(
        db,
        actor=admin,
        action="approval.decide",
        entity="approval",
        entity_id=row.id,
        request=request,
        details={"status": row.status.value, "registration_id": row.registration_id},
    )
    return row

