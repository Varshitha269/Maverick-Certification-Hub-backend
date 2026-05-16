from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

import datetime as dt

from app.api.schemas.drive_brd import DriveBRDCreate, DriveBRDOut, DriveBRDUpdate
from app.core.deps import require_role
from app.db.session import get_db
from app.models.assessment import AssessmentOutcome, AssessmentResult
from app.models.certification import Certification, CertificationDrive
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.registration import Registration, RegistrationStatus
from app.models.user import User, UserRole
from app.models.voucher import Voucher
from app.services.audit_service import log_audit
from app.models.notification import Notification, NotificationType
from app.services.notification_service import create_notification, deliver_due_notification_emails
from app.services.storage_service import ensure_drive_repository_prefix


router = APIRouter()


def _fallback_repository_prefix(*, drive_id: int, drive_name: str) -> str:
    safe = (drive_name or f"drive-{drive_id}").strip().replace(" ", "_").replace("/", "_").replace("\\", "_")
    return f"drives/{drive_id}-{safe}"


def _best_effort_repository_prefix(*, drive_id: int, drive_name: str) -> str:
    try:
        return ensure_drive_repository_prefix(drive_id=drive_id, drive_name=drive_name)
    except Exception:  # noqa: BLE001
        return _fallback_repository_prefix(drive_id=drive_id, drive_name=drive_name)


def _drive_notification_payload(db: Session, drive: CertificationDrive, *, title: str | None = None) -> tuple[str, str, str]:
    cert = db.query(Certification).filter(Certification.id == drive.certification_id).first()
    cert_title = cert.title if cert else drive.name
    notification_title = title or "New certification drive open"
    message = (
        f"{drive.name} is open for registration"
        f"{' until ' + drive.end_date if drive.end_date else ''}. "
        f"Certification: {cert_title}."
    )
    return notification_title, message, cert_title


def _notify_stakeholders_about_drive(db: Session, drive: CertificationDrive, admin: User, *, title: str | None = None) -> dict:
    notification_title, message, cert_title = _drive_notification_payload(db, drive, title=title)
    learners = db.query(User).filter(User.role == UserRole.user, User.is_active.is_(True)).all()
    admins = db.query(User).filter(User.role == UserRole.admin, User.is_active.is_(True)).all()
    notification_users: dict[int, User] = {user.id: user for user in learners}
    notification_users.update({user.id: user for user in admins})
    notification_users[admin.id] = admin
    owner_notified = False
    if drive.owner_email:
        owner = db.query(User).filter(User.email == drive.owner_email).first()
        if owner:
            notification_users[owner.id] = owner
            owner_notified = True

    for user in notification_users.values():
        audience = "learners" if user.role == UserRole.user else "admins"
        link_url = f"/registrations?drive_id={drive.id}" if user.role == UserRole.user else f"/admin-brd/drives?drive_id={drive.id}"
        user_message = message if user.role == UserRole.user else f"{drive.name} was created/updated. Owner: {drive.owner_email or admin.email}. Certification: {cert_title}."
        db.add(Notification(
            user_id=user.id,
            type=NotificationType.system,
            title=notification_title,
            message=user_message,
            link_url=link_url,
            priority="medium",
            icon="certificate",
            audience=audience,
            email_enabled=True,
        ))
    db.commit()
    deliver_due_notification_emails(db)

    return {
        "notifications": len(notification_users),
        "learner_notifications": len(learners),
        "admin_notifications": len([user for user in notification_users.values() if user.role == UserRole.admin]),
        "owner_notification": owner_notified,
        "email_notifications_queued": len(notification_users),
    }


def _notify_users_about_drive(db: Session, drive: CertificationDrive, *, title: str | None = None) -> int:
    notification_title, message, _ = _drive_notification_payload(db, drive, title=title)
    users = db.query(User).filter(User.role == UserRole.user, User.is_active.is_(True)).all()
    for user in users:
        create_notification(
            db,
            user_id=user.id,
            type=NotificationType.system,
            title=notification_title,
            message=message,
            link_url=f"/registrations?drive_id={drive.id}",
            priority="medium",
            icon="certificate",
            audience="learners",
            email_enabled=True,
        )
    return len(users)


def _find_certification(db: Session, *, title_terms: list[str], provider_terms: list[str] | None = None) -> Certification | None:
    certs = db.query(Certification).order_by(Certification.id.asc()).all()
    provider_terms = provider_terms or []
    for cert in certs:
        text = f"{cert.title or ''} {cert.provider or ''} {cert.category or ''} {cert.tags or ''}".lower()
        if all(term.lower() in text for term in title_terms) and all(term.lower() in text for term in provider_terms):
            return cert
    return None


def _create_drive(
    db: Session,
    *,
    certification_id: int,
    name: str,
    start_date: str | None,
    end_date: str | None,
    eligibility_rules: str | None = None,
    voucher_budget: int | None = None,
    sponsor: str | None = None,
    owner_email: str | None = None,
    policy_url: str | None = None,
    target_count: int | None = None,
    status: str = "open",
    repository_prefix: str | None = None,
) -> CertificationDrive:
    drive = CertificationDrive(
        certification_id=certification_id,
        name=name,
        start_date=start_date,
        end_date=end_date,
        eligibility_rules=eligibility_rules,
        voucher_budget=voucher_budget,
        sponsor=sponsor,
        owner_email=owner_email,
        policy_url=policy_url,
        target_count=target_count,
        status=status,
        repository_prefix=repository_prefix,
    )
    db.add(drive)
    db.flush()
    if not drive.repository_prefix:
        drive.repository_prefix = _best_effort_repository_prefix(drive_id=drive.id, drive_name=drive.name)
    return drive


def _get_or_create_demo_certification(
    db: Session,
    *,
    title: str,
    provider: str,
    category: str,
    level: str,
    tags: str,
    description: str,
) -> Certification:
    cert = db.query(Certification).filter(Certification.title == title, Certification.provider == provider).first()
    if cert:
        return cert
    cert = Certification(
        title=title,
        provider=provider,
        category=category,
        level=level,
        tags=tags,
        description=description,
        duration="6 weeks",
        estimated_hours=40,
        exam_cost=150,
    )
    db.add(cert)
    db.flush()
    return cert


def _ensure_demo_drives(db: Session, admin: User | None = None) -> list[int]:
    today = dt.date.today()
    owner_email = admin.email if admin else "cert-admin@maverick.local"
    certs = {
        "aws": _get_or_create_demo_certification(
            db,
            title="AWS Cloud Practitioner",
            provider="Amazon Web Services",
            category="Cloud",
            level="Foundational",
            tags="aws,cloud,practitioner",
            description="Foundational AWS cloud concepts, billing, security, and core services.",
        ),
        "azure": _get_or_create_demo_certification(
            db,
            title="Azure Fundamentals AZ-900",
            provider="Microsoft",
            category="Cloud",
            level="Foundational",
            tags="azure,fundamentals,az-900",
            description="Microsoft Azure cloud concepts, pricing, governance, and services.",
        ),
        "devops": _get_or_create_demo_certification(
            db,
            title="Certified Kubernetes Administrator",
            provider="CNCF / Linux Foundation",
            category="DevOps",
            level="Associate",
            tags="devops,kubernetes,administrator,cka",
            description="Kubernetes administration, clusters, workloads, networking, and troubleshooting.",
        ),
    }
    specs = [
        {
            "cert": certs["aws"],
            "name": "AWS Cloud Practitioner - Current Drive",
            "start_date": today.isoformat(),
            "end_date": (today + dt.timedelta(days=45)).isoformat(),
            "status": "open",
            "voucher_budget": 25,
            "target_count": 40,
            "sponsor": "Amazon Web Services",
        },
        {
            "cert": certs["azure"],
            "name": "Azure Fundamentals AZ-900 - Current Drive",
            "start_date": today.isoformat(),
            "end_date": (today + dt.timedelta(days=45)).isoformat(),
            "status": "open",
            "voucher_budget": 25,
            "target_count": 40,
            "sponsor": "Microsoft",
        },
        {
            "cert": certs["devops"],
            "name": "DevOps Kubernetes CKA - Current Drive",
            "start_date": today.isoformat(),
            "end_date": (today + dt.timedelta(days=45)).isoformat(),
            "status": "open",
            "voucher_budget": 15,
            "target_count": 25,
            "sponsor": "CNCF / Linux Foundation",
        },
        {
            "cert": certs["aws"],
            "name": "AWS Solutions Architect - Completed April Drive",
            "start_date": (today - dt.timedelta(days=80)).isoformat(),
            "end_date": (today - dt.timedelta(days=35)).isoformat(),
            "status": "completed",
            "voucher_budget": 20,
            "target_count": 30,
            "sponsor": "Amazon Web Services",
        },
        {
            "cert": certs["azure"],
            "name": "Azure Administrator AZ-104 - Completed March Drive",
            "start_date": (today - dt.timedelta(days=110)).isoformat(),
            "end_date": (today - dt.timedelta(days=65)).isoformat(),
            "status": "completed",
            "voucher_budget": 18,
            "target_count": 25,
            "sponsor": "Microsoft",
        },
        {
            "cert": certs["devops"],
            "name": "DevOps Kubernetes - Completed February Drive",
            "start_date": (today - dt.timedelta(days=140)).isoformat(),
            "end_date": (today - dt.timedelta(days=100)).isoformat(),
            "status": "completed",
            "voucher_budget": 12,
            "target_count": 20,
            "sponsor": "CNCF / Linux Foundation",
        },
    ]
    ready_ids: list[int] = []
    for spec in specs:
        existing = db.query(CertificationDrive).filter(CertificationDrive.name == spec["name"]).first()
        if existing:
            existing.certification_id = spec["cert"].id
            existing.start_date = spec["start_date"]
            existing.end_date = spec["end_date"]
            existing.status = spec["status"]
            existing.voucher_budget = spec["voucher_budget"]
            existing.target_count = spec["target_count"]
            existing.sponsor = spec["sponsor"]
            existing.owner_email = existing.owner_email or owner_email
            db.add(existing)
            ready_ids.append(existing.id)
            continue
        drive = _create_drive(
            db,
            certification_id=spec["cert"].id,
            name=spec["name"],
            start_date=spec["start_date"],
            end_date=spec["end_date"],
            eligibility_rules=None,
            voucher_budget=spec["voucher_budget"],
            sponsor=spec["sponsor"],
            owner_email=owner_email,
            target_count=spec["target_count"],
            status=spec["status"],
        )
        ready_ids.append(drive.id)
    db.commit()
    return ready_ids


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
        drive.repository_prefix = _best_effort_repository_prefix(drive_id=drive.id, drive_name=drive.name)
        created.append({"drive_id": drive.id, "certification_id": cert.id, "certification": cert.title})
    if created:
        db.commit()
    return created, len(certs)


def _ensure_completed_drive_participants(db: Session) -> None:
    users = (
        db.query(User)
        .filter(User.role == UserRole.user, User.is_active.is_(True))
        .order_by(User.id.asc())
        .limit(12)
        .all()
    )
    if not users:
        return

    completed_drives = (
        db.query(CertificationDrive)
        .filter(CertificationDrive.status.in_(["completed", "closed"]))
        .order_by(CertificationDrive.end_date.desc(), CertificationDrive.id.desc())
        .limit(8)
        .all()
    )
    if not completed_drives:
        return

    outcomes = [AssessmentOutcome.pass_, AssessmentOutcome.pass_, AssessmentOutcome.fail, AssessmentOutcome.no_show]
    changed = False
    for drive_index, drive in enumerate(completed_drives):
        existing_count = db.query(func.count(Registration.id)).filter(Registration.drive_id == drive.id).scalar() or 0
        if existing_count >= 3:
            continue

        for offset in range(min(4, len(users))):
            user = users[(drive_index + offset) % len(users)]
            existing = (
                db.query(Registration)
                .filter(Registration.drive_id == drive.id, Registration.candidate_email == user.email)
                .first()
            )
            if existing:
                continue

            outcome = outcomes[(drive_index + offset) % len(outcomes)]
            reg_status = RegistrationStatus.passed if outcome == AssessmentOutcome.pass_ else (
                RegistrationStatus.failed if outcome == AssessmentOutcome.fail else RegistrationStatus.assessed
            )
            score = None
            if outcome == AssessmentOutcome.pass_:
                score = 760 + ((drive_index + offset) % 4) * 18
            elif outcome == AssessmentOutcome.fail:
                score = 610 + ((drive_index + offset) % 3) * 20

            reg = Registration(
                drive_id=drive.id,
                emp_id=f"EMP{user.id:04d}",
                candidate_name=user.full_name or user.email.split("@")[0].replace(".", " ").title(),
                candidate_email=user.email,
                bu="Cloud Practice",
                location="Bengaluru",
                manager_email=drive.owner_email,
                exam_track=drive.name,
                slot=drive.end_date,
                prior_attempts=0,
                status=reg_status,
                notes="Seeded completed-drive attendance record",
            )
            db.add(reg)
            db.flush()

            db.add(
                AssessmentResult(
                    registration_id=reg.id,
                    drive_id=drive.id,
                    score=score,
                    outcome=outcome,
                    assessed_on=drive.end_date,
                    notes="Completed-drive sample result",
                )
            )

            if outcome == AssessmentOutcome.pass_:
                enrollment = (
                    db.query(Enrollment)
                    .filter(
                        Enrollment.user_id == user.id,
                        Enrollment.certification_id == drive.certification_id,
                        Enrollment.drive_id == drive.id,
                    )
                    .first()
                )
                if not enrollment:
                    enrollment = Enrollment(
                        user_id=user.id,
                        certification_id=drive.certification_id,
                        drive_id=drive.id,
                        status=EnrollmentStatus.completed,
                        progress_percent=100,
                        notes=f"Completed through {drive.name}",
                    )
                    db.add(enrollment)
                else:
                    enrollment.status = EnrollmentStatus.completed
                    enrollment.progress_percent = 100
                    db.add(enrollment)

            changed = True

    if changed:
        db.commit()


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


def _drives_to_out(db: Session, drives: list[CertificationDrive]) -> list[dict]:
    drive_ids = [drive.id for drive in drives]
    if not drive_ids:
        return []

    registrations = dict(
        db.query(Registration.drive_id, func.count(Registration.id))
        .filter(Registration.drive_id.in_(drive_ids))
        .group_by(Registration.drive_id)
        .all()
    )
    assessed = dict(
        db.query(AssessmentResult.drive_id, func.count(AssessmentResult.id))
        .filter(AssessmentResult.drive_id.in_(drive_ids))
        .group_by(AssessmentResult.drive_id)
        .all()
    )
    vouchers = dict(
        db.query(Voucher.drive_id, func.count(Voucher.id))
        .filter(Voucher.drive_id.in_(drive_ids))
        .group_by(Voucher.drive_id)
        .all()
    )
    last_assessed = dict(
        db.query(AssessmentResult.drive_id, func.max(AssessmentResult.assessed_on))
        .filter(AssessmentResult.drive_id.in_(drive_ids))
        .group_by(AssessmentResult.drive_id)
        .all()
    )
    outcome_counts = {
        (drive_id, outcome): count
        for drive_id, outcome, count in (
            db.query(AssessmentResult.drive_id, AssessmentResult.outcome, func.count(AssessmentResult.id))
            .filter(AssessmentResult.drive_id.in_(drive_ids))
            .group_by(AssessmentResult.drive_id, AssessmentResult.outcome)
            .all()
        )
    }
    registration_rows = (
        db.query(Registration)
        .filter(Registration.drive_id.in_(drive_ids))
        .order_by(Registration.drive_id.asc(), Registration.created_at.desc())
        .all()
    )
    result_by_registration = {
        row.registration_id: row
        for row in (
            db.query(AssessmentResult)
            .filter(AssessmentResult.drive_id.in_(drive_ids))
            .order_by(AssessmentResult.created_at.desc())
            .all()
        )
    }
    attendees_by_drive: dict[int, list[dict]] = {}
    for reg in registration_rows:
        if len(attendees_by_drive.get(reg.drive_id, [])) >= 5:
            continue
        result = result_by_registration.get(reg.id)
        attendees_by_drive.setdefault(reg.drive_id, []).append(
            {
                "registration_id": reg.id,
                "name": reg.candidate_name,
                "email": reg.candidate_email,
                "status": reg.status.value if hasattr(reg.status, "value") else str(reg.status),
                "outcome": result.outcome.value if result and hasattr(result.outcome, "value") else (str(result.outcome) if result else None),
                "score": result.score if result else None,
                "assessed_on": result.assessed_on if result else None,
            }
        )

    rows = []
    for drive in drives:
        cert = drive.certification
        last_conducted_date = last_assessed.get(drive.id) or (drive.end_date if drive.status in {"closed", "completed"} else None)
        can_reconduct = bool(last_conducted_date or drive.status in {"closed", "completed"})
        can_conduct = drive.status in {"open", "planned", "active"} and not last_conducted_date
        next_action = "Re-conduct drive" if can_reconduct else ("Conduct drive" if can_conduct else "Review drive")
        rows.append(
            {
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
                "registrations_count": registrations.get(drive.id, 0),
                "assessed_count": assessed.get(drive.id, 0),
                "passed_count": outcome_counts.get((drive.id, AssessmentOutcome.pass_), 0),
                "failed_count": outcome_counts.get((drive.id, AssessmentOutcome.fail), 0),
                "voucher_count": vouchers.get(drive.id, 0),
                "last_conducted_date": last_conducted_date,
                "can_conduct": can_conduct,
                "can_reconduct": can_reconduct,
                "next_action": next_action,
                "recent_attendees": attendees_by_drive.get(drive.id, []),
            }
        )
    return rows


@router.get("/", response_model=list[DriveBRDOut])
def list_drives(db: Session = Depends(get_db), admin: User = Depends(require_role(UserRole.admin))):
    _ensure_demo_drives(db, admin)
    _ensure_missing_drives(db, admin)
    _ensure_completed_drive_participants(db)
    rows = (
        db.query(CertificationDrive)
        .options(joinedload(CertificationDrive.certification))
        .order_by(CertificationDrive.created_at.desc())
        .all()
    )
    return _drives_to_out(db, rows)


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


@router.post("/seed-current")
def seed_current_drives(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    today = dt.date.today()
    start = today.isoformat()
    end = (today + dt.timedelta(days=45)).isoformat()
    specs = [
        {
            "key": "aws",
            "terms": ["aws", "cloud", "practitioner"],
            "provider_terms": [],
            "name": "AWS Cloud Practitioner - Current Drive",
            "voucher_budget": 25,
            "target_count": 40,
            "sponsor": "Amazon Web Services",
        },
        {
            "key": "azure",
            "terms": ["azure", "fundamentals"],
            "provider_terms": [],
            "name": "Azure Fundamentals AZ-900 - Current Drive",
            "voucher_budget": 25,
            "target_count": 40,
            "sponsor": "Microsoft",
        },
        {
            "key": "devops",
            "terms": ["kubernetes", "administrator"],
            "provider_terms": [],
            "name": "DevOps Kubernetes CKA - Current Drive",
            "voucher_budget": 15,
            "target_count": 25,
            "sponsor": "CNCF / Linux Foundation",
        },
    ]
    created = []
    reused = []
    for spec in specs:
        cert = _find_certification(db, title_terms=spec["terms"], provider_terms=spec["provider_terms"])
        if not cert:
            reused.append({"key": spec["key"], "reason": "certification not found"})
            continue
        existing = (
            db.query(CertificationDrive)
            .filter(
                CertificationDrive.certification_id == cert.id,
                CertificationDrive.name == spec["name"],
                CertificationDrive.status == "open",
            )
            .first()
        )
        if existing:
            reused.append({"drive_id": existing.id, "certification": cert.title})
            continue
        drive = _create_drive(
            db,
            certification_id=cert.id,
            name=spec["name"],
            start_date=start,
            end_date=end,
            eligibility_rules=None,
            voucher_budget=spec["voucher_budget"],
            sponsor=spec["sponsor"],
            owner_email=admin.email,
            target_count=spec["target_count"],
            status="open",
        )
        created.append(drive)

    db.commit()
    notified = 0
    email_queued = 0
    for drive in created:
        db.refresh(drive)
        notification_result = _notify_stakeholders_about_drive(db, drive, admin)
        notified += notification_result["notifications"]
        email_queued += notification_result["email_notifications_queued"]
    log_audit(
        db,
        actor=admin,
        action="drive.seed_current",
        entity="certification_drive",
        entity_id="current",
        request=request,
        details={
            "created": [drive.id for drive in created],
            "reused": reused,
            "notified": notified,
            "email_notifications_queued": email_queued,
        },
    )
    return {
        "created": len(created),
        "created_drive_ids": [drive.id for drive in created],
        "reused": reused,
        "notified": notified,
        "email_notifications_queued": email_queued,
        "start_date": start,
        "end_date": end,
    }


@router.post("/seed-completed")
def seed_completed_drives(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    today = dt.date.today()
    specs = [
        {
            "terms": ["aws", "solutions", "architect", "associate"],
            "name": "AWS Solutions Architect - Completed April Drive",
            "start_date": (today - dt.timedelta(days=80)).isoformat(),
            "end_date": (today - dt.timedelta(days=35)).isoformat(),
            "voucher_budget": 20,
            "target_count": 30,
            "sponsor": "Amazon Web Services",
        },
        {
            "terms": ["azure", "administrator"],
            "name": "Azure Administrator AZ-104 - Completed March Drive",
            "start_date": (today - dt.timedelta(days=110)).isoformat(),
            "end_date": (today - dt.timedelta(days=65)).isoformat(),
            "voucher_budget": 18,
            "target_count": 25,
            "sponsor": "Microsoft",
        },
        {
            "terms": ["docker", "certified"],
            "name": "Docker Certified Associate - Completed February Drive",
            "start_date": (today - dt.timedelta(days=140)).isoformat(),
            "end_date": (today - dt.timedelta(days=100)).isoformat(),
            "voucher_budget": 12,
            "target_count": 20,
            "sponsor": "Docker",
        },
        {
            "terms": ["servicenow", "system", "administrator"],
            "name": "ServiceNow CSA - Completed January Drive",
            "start_date": (today - dt.timedelta(days=170)).isoformat(),
            "end_date": (today - dt.timedelta(days=130)).isoformat(),
            "voucher_budget": 16,
            "target_count": 22,
            "sponsor": "ServiceNow",
        },
        {
            "terms": ["python", "entry"],
            "name": "Python PCEP - Completed December Drive",
            "start_date": (today - dt.timedelta(days=205)).isoformat(),
            "end_date": (today - dt.timedelta(days=165)).isoformat(),
            "voucher_budget": 14,
            "target_count": 28,
            "sponsor": "Python Institute",
        },
    ]
    created = []
    reused = []
    ready_ids = []
    for spec in specs:
        cert = _find_certification(db, title_terms=spec["terms"])
        if not cert:
            reused.append({"name": spec["name"], "reason": "certification not found"})
            continue
        existing = db.query(CertificationDrive).filter(CertificationDrive.name == spec["name"]).first()
        if existing:
            existing.status = "completed"
            existing.start_date = spec["start_date"]
            existing.end_date = spec["end_date"]
            existing.voucher_budget = spec["voucher_budget"]
            existing.target_count = spec["target_count"]
            existing.sponsor = spec["sponsor"]
            existing.owner_email = existing.owner_email or admin.email
            db.add(existing)
            ready_ids.append(existing.id)
            reused.append({"drive_id": existing.id, "certification": cert.title})
            continue
        drive = _create_drive(
            db,
            certification_id=cert.id,
            name=spec["name"],
            start_date=spec["start_date"],
            end_date=spec["end_date"],
            eligibility_rules=None,
            voucher_budget=spec["voucher_budget"],
            sponsor=spec["sponsor"],
            owner_email=admin.email,
            target_count=spec["target_count"],
            status="completed",
        )
        created.append(drive)
        ready_ids.append(drive.id)
    db.commit()
    for drive in created:
        db.refresh(drive)
    log_audit(
        db,
        actor=admin,
        action="drive.seed_completed",
        entity="certification_drive",
        entity_id="completed",
        request=request,
        details={"created": [drive.id for drive in created], "ready": ready_ids, "reused": reused},
    )
    return {
        "created": len(created),
        "created_drive_ids": [drive.id for drive in created],
        "ready": len(ready_ids),
        "ready_drive_ids": ready_ids,
        "reused": reused,
    }


@router.post("/", response_model=DriveBRDOut)
def create_drive(
    payload: DriveBRDCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    cert = db.query(Certification).filter(Certification.id == payload.certification_id).first()
    if not cert:
        raise HTTPException(status_code=404, detail="Certification not found")
    data = payload.model_dump(exclude_unset=True)
    data["owner_email"] = data.get("owner_email") or admin.email
    data["status"] = data.get("status") or "open"
    data["start_date"] = data.get("start_date")
    data["end_date"] = data.get("end_date")
    drive = _create_drive(db, **data)
    db.commit()
    db.refresh(drive)
    notification_result = _notify_stakeholders_about_drive(db, drive, admin)
    log_audit(
        db,
        actor=admin,
        action="drive.create",
        entity="certification_drive",
        entity_id=drive.id,
        request=request,
        details={**payload.model_dump(exclude_unset=True), **notification_result},
    )
    return _drive_to_out(db, drive)


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
        drive.repository_prefix = _best_effort_repository_prefix(drive_id=drive.id, drive_name=drive.name)
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
    drive.repository_prefix = _best_effort_repository_prefix(drive_id=drive.id, drive_name=drive.name)
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
    drive = _create_drive(
        db,
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
    db.commit()
    db.refresh(drive)
    notification_result = _notify_stakeholders_about_drive(db, drive, admin, title="Certification drive re-conduct open")
    log_audit(
        db,
        actor=admin,
        action="drive.reconduct",
        entity="certification_drive",
        entity_id=drive.id,
        request=request,
        details={"source_drive_id": source.id, "certification_id": source.certification_id, **notification_result},
    )
    return _drive_to_out(db, drive)

