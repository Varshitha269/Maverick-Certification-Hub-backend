import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.schemas.assessment_brd import AssessmentCreate, AssessmentOut
from app.core.deps import require_role
from app.db.session import get_db
from app.models.assessment import AssessmentOutcome, AssessmentResult
from app.models.registration import Registration, RegistrationStatus
from app.models.user import User, UserRole
from app.services.audit_service import log_audit


router = APIRouter()


@router.post("/", response_model=AssessmentOut)
def create_result(
    payload: AssessmentCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    reg = db.query(Registration).filter(Registration.id == payload.registration_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail="Registration not found")
    try:
        outcome = AssessmentOutcome(payload.outcome)
    except Exception:  # noqa: BLE001
        outcome = AssessmentOutcome.pending

    row = AssessmentResult(
        registration_id=reg.id,
        drive_id=reg.drive_id,
        score=payload.score,
        outcome=outcome,
        assessed_on=payload.assessed_on,
        evidence_upload_id=payload.evidence_upload_id,
        evidence_url=payload.evidence_url,
        notes=payload.notes,
    )
    db.add(row)

    # update registration status
    if outcome == AssessmentOutcome.pass_:
        reg.status = RegistrationStatus.passed
    elif outcome == AssessmentOutcome.fail:
        reg.status = RegistrationStatus.failed
    elif outcome == AssessmentOutcome.no_show:
        reg.status = RegistrationStatus.assessed
    db.add(reg)

    db.commit()
    db.refresh(row)
    log_audit(
        db,
        actor=admin,
        action="result.create",
        entity="assessment_result",
        entity_id=row.id,
        request=request,
        details={"registration_id": reg.id, "outcome": outcome.value},
    )
    return row


@router.get("/", response_model=list[AssessmentOut])
def list_results(
    drive_id: int | None = None,
    registration_id: int | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):  # noqa: ARG001
    q = db.query(AssessmentResult)
    if drive_id is not None:
        q = q.filter(AssessmentResult.drive_id == drive_id)
    if registration_id is not None:
        q = q.filter(AssessmentResult.registration_id == registration_id)
    return q.order_by(AssessmentResult.created_at.desc()).limit(2000).all()


@router.post("/import-csv")
def import_results_csv(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    """
    Body: { "csv": "registration_id,score,outcome,assessed_on\\n1,720,pass,2026-05-01\\n..." }
    """
    csv_text = (payload.get("csv") or "").strip()
    if not csv_text:
        raise HTTPException(status_code=400, detail="Missing csv")

    r = csv.DictReader(io.StringIO(csv_text))
    created = 0
    skipped = 0
    for row in r:
        try:
            reg_id = int(row.get("registration_id") or 0)
        except Exception:  # noqa: BLE001
            skipped += 1
            continue
        reg = db.query(Registration).filter(Registration.id == reg_id).first()
        if not reg:
            skipped += 1
            continue
        outcome_raw = (row.get("outcome") or "pending").strip().lower()
        if outcome_raw == "pass":
            outcome = AssessmentOutcome.pass_
        elif outcome_raw == "fail":
            outcome = AssessmentOutcome.fail
        elif outcome_raw == "no_show":
            outcome = AssessmentOutcome.no_show
        else:
            outcome = AssessmentOutcome.pending
        score = None
        if row.get("score"):
            try:
                score = int(row["score"])
            except Exception:  # noqa: BLE001
                score = None
        assessed_on = (row.get("assessed_on") or None)

        res = AssessmentResult(
            registration_id=reg.id,
            drive_id=reg.drive_id,
            score=score,
            outcome=outcome,
            assessed_on=assessed_on,
        )
        db.add(res)
        created += 1

        if outcome == AssessmentOutcome.pass_:
            reg.status = RegistrationStatus.passed
        elif outcome == AssessmentOutcome.fail:
            reg.status = RegistrationStatus.failed
        db.add(reg)

    db.commit()
    log_audit(
        db,
        actor=admin,
        action="result.import_csv",
        entity="assessment_result",
        entity_id="bulk",
        request=request,
        details={"created": created, "skipped": skipped},
    )
    return {"created": created, "skipped": skipped}


@router.get("/export-csv")
def export_results_csv(
    request: Request,
    drive_id: int | None = None,
    registration_id: int | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    q = db.query(AssessmentResult)
    if drive_id is not None:
        q = q.filter(AssessmentResult.drive_id == drive_id)
    if registration_id is not None:
        q = q.filter(AssessmentResult.registration_id == registration_id)
    rows = q.order_by(AssessmentResult.created_at.desc()).all()
    reg_map = {r.id: r for r in db.query(Registration).all()}

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "result_id",
        "registration_id",
        "drive_id",
        "candidate_name",
        "candidate_email",
        "score",
        "outcome",
        "assessed_on",
        "evidence_url",
        "notes",
        "created_at",
    ])
    for row in rows:
        reg = reg_map.get(row.registration_id)
        w.writerow([
            row.id,
            row.registration_id,
            row.drive_id,
            reg.candidate_name if reg else "",
            reg.candidate_email if reg else "",
            row.score if row.score is not None else "",
            row.outcome.value if hasattr(row.outcome, "value") else str(row.outcome),
            row.assessed_on or "",
            row.evidence_url or "",
            row.notes or "",
            row.created_at.isoformat() if row.created_at else "",
        ])

    log_audit(
        db,
        actor=admin,
        action="result.export_csv",
        entity="assessment_result",
        entity_id=registration_id or drive_id or "all",
        request=request,
        details={"rows": len(rows), "drive_id": drive_id, "registration_id": registration_id},
    )
    buf.seek(0)
    filename = f"assessment-results-{registration_id or drive_id or 'all'}.csv"
    return StreamingResponse(
        iter([buf.getvalue().encode("utf-8")]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

