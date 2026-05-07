from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.schemas.drive_brd import DriveBRDOut, DriveBRDUpdate
from app.core.deps import require_role
from app.db.session import get_db
from app.models.assessment import AssessmentOutcome, AssessmentResult
from app.models.certification import Certification, CertificationDrive
from app.models.registration import Registration
from app.models.user import User, UserRole
from app.models.voucher import Voucher
from app.services.audit_service import log_audit
from app.services.storage_service import ensure_drive_repository_prefix


router = APIRouter()


def _ensure_missing_drives(db: Session, admin: User | None = None):
    certs = db.query(Certification).order_by(Certification.title.asc()).all()
    existing_cert_ids = {
        row[0]
        for row in db.query(CertificationDrive.certification_id).distinct().all()
    }
    created = []
    for cert in certs:
        if cert.id in existing_cert_ids:
            continue
        drive = CertificationDrive(
            certification_id=cert.id,
            name=f"{cert.title} - Default Drive",
            start_date=None,
            end_date=None,
            eligibility_rules=None,
            voucher_budget=None,
            sponsor=cert.provider,
            owner_email=admin.email if admin else None,
            target_count=None,
            status="open",
        )
        db.add(drive)
        db.flush()
        try:
            drive.repository_prefix = ensure_drive_repository_prefix(drive_id=drive.id, drive_name=drive.name)
        except Exception:  # noqa: BLE001
            drive.repository_prefix = None
        created.append({"drive_id": drive.id, "certification_id": cert.id, "certification": cert.title})
    if created:
        db.commit()
    return created, len(certs)


def _drive_to_out(db: Session, drive: CertificationDrive) -> dict:
    cert = db.query(Certification).filter(Certification.id == drive.certification_id).first()
    registrations_count = db.query(func.count(Registration.id)).filter(Registration.drive_id == drive.id).scalar() or 0
    assessed_count = db.query(func.count(AssessmentResult.id)).filter(AssessmentResult.drive_id == drive.id).scalar() or 0
    passed_count = (
        db.query(func.count(AssessmentResult.id))
        .filter(AssessmentResult.drive_id == drive.id, AssessmentResult.outcome == AssessmentOutcome.pass_)
        .scalar()
        or 0
    )
    failed_count = (
        db.query(func.count(AssessmentResult.id))
        .filter(AssessmentResult.drive_id == drive.id, AssessmentResult.outcome == AssessmentOutcome.fail)
        .scalar()
        or 0
    )
    voucher_count = db.query(func.count(Voucher.id)).filter(Voucher.drive_id == drive.id).scalar() or 0
    last_assessed = db.query(func.max(AssessmentResult.assessed_on)).filter(AssessmentResult.drive_id == drive.id).scalar()
    last_conducted_date = last_assessed or (drive.end_date if drive.status in {"closed", "completed"} else None)
    can_reconduct = bool(last_conducted_date or drive.status in {"closed", "completed"})
    can_conduct = drive.status in {"open", "planned", "active"} and not last_conducted_date
    next_action = "Re-conduct drive" if can_reconduct else ("Conduct drive" if can_conduct else "Review drive")

    return {
        "id": drive.id,
        "certification_id": drive.certification_id,
        "certification_title": cert.title if cert else None,
        "certification_provider": cert.provider if cert else None,
        "certification_category": cert.category if cert else None,
        "name": drive.name,
        "start_date": drive.start_date,
        "end_date": drive.end_date,
        "eligibility_rules": drive.eligibility_rules,
        "voucher_budget": drive.voucher_budget,
        "sponsor": drive.sponsor,
        "owner_email": drive.owner_email,
        "policy_url": drive.policy_url,
        "target_count": drive.target_count,
        "status": drive.status,
        "repository_prefix": drive.repository_prefix,
        "registrations_count": registrations_count,
        "assessed_count": assessed_count,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "voucher_count": voucher_count,
        "last_conducted_date": last_conducted_date,
        "can_conduct": can_conduct,
        "can_reconduct": can_reconduct,
        "next_action": next_action,
    }


@router.get("/", response_model=list[DriveBRDOut])
def list_drives(db: Session = Depends(get_db), admin: User = Depends(require_role(UserRole.admin))):
    _ensure_missing_drives(db, admin)
    rows = db.query(CertificationDrive).order_by(CertificationDrive.created_at.desc()).all()
    return [_drive_to_out(db, drive) for drive in rows]


@router.post("/ensure-defaults")
def ensure_default_drives(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    created, total_certs = _ensure_missing_drives(db, admin)
    log_audit(
        db,
        actor=admin,
        action="drive.ensure_defaults",
        entity="certification_drive",
        entity_id="bulk",
        request=request,
        details={"created": len(created), "drives": created},
    )
    return {"created": len(created), "drives": created, "total_certifications": total_certs}


@router.patch("/{drive_id}", response_model=DriveBRDOut)
def update_drive(
    drive_id: int,
    payload: DriveBRDUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    drive = db.query(CertificationDrive).filter(CertificationDrive.id == drive_id).first()
    if not drive:
        raise HTTPException(status_code=404, detail="Drive not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(drive, k, v)

    # If repository prefix wasn't set, provision it now (best-effort).
    if not drive.repository_prefix:
        try:
            drive.repository_prefix = ensure_drive_repository_prefix(drive_id=drive.id, drive_name=drive.name)
        except Exception:  # noqa: BLE001
            pass
    db.add(drive)
    db.commit()
    db.refresh(drive)
    log_audit(
        db,
        actor=admin,
        action="drive.update",
        entity="certification_drive",
        entity_id=drive.id,
        request=request,
        details=payload.model_dump(exclude_unset=True),
    )
    return _drive_to_out(db, drive)


@router.post("/{drive_id}/provision-repo", response_model=DriveBRDOut)
def provision_repository(
    drive_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    drive = db.query(CertificationDrive).filter(CertificationDrive.id == drive_id).first()
    if not drive:
        raise HTTPException(status_code=404, detail="Drive not found")
    drive.repository_prefix = ensure_drive_repository_prefix(drive_id=drive.id, drive_name=drive.name)
    db.add(drive)
    db.commit()
    db.refresh(drive)
    log_audit(
        db,
        actor=admin,
        action="drive.provision_repo",
        entity="certification_drive",
        entity_id=drive.id,
        request=request,
        details={"repository_prefix": drive.repository_prefix},
    )
    return _drive_to_out(db, drive)


@router.post("/{drive_id}/reconduct", response_model=DriveBRDOut)
def reconduct_drive(
    drive_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    source = db.query(CertificationDrive).filter(CertificationDrive.id == drive_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Drive not found")
    cert = db.query(Certification).filter(Certification.id == source.certification_id).first()
    existing_runs = db.query(func.count(CertificationDrive.id)).filter(CertificationDrive.certification_id == source.certification_id).scalar() or 0
    drive = CertificationDrive(
        certification_id=source.certification_id,
        name=f"{cert.title if cert else source.name} - Re-Conduct {existing_runs + 1}",
        start_date=None,
        end_date=None,
        eligibility_rules=source.eligibility_rules,
        voucher_budget=source.voucher_budget,
        sponsor=source.sponsor,
        owner_email=source.owner_email or admin.email,
        policy_url=source.policy_url,
        target_count=source.target_count,
        status="open",
    )
    db.add(drive)
    db.flush()
    try:
        drive.repository_prefix = ensure_drive_repository_prefix(drive_id=drive.id, drive_name=drive.name)
    except Exception:  # noqa: BLE001
        drive.repository_prefix = None
    db.commit()
    db.refresh(drive)
    log_audit(
        db,
        actor=admin,
        action="drive.reconduct",
        entity="certification_drive",
        entity_id=drive.id,
        request=request,
        details={"source_drive_id": source.id, "certification_id": source.certification_id},
    )
    return _drive_to_out(db, drive)

