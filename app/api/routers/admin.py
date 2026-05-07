from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.schemas.user import AdminUserCreate, AdminUserOut, AdminUserUpdate, UserOut
from app.core.deps import require_role
from app.core.security import hash_password
from app.db.session import get_db
from app.models.certification import Certification
from app.models.certification import CertificationDrive
from app.models.audit import AuditLog
from app.models.email_log import EmailLog
from app.models.eligibility import EligibilityTestAttempt
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.registration import Registration
from app.models.task import Task, TaskStatus
from app.models.upload import UploadedFile, UploadPurpose
from app.models.user import User, UserRole
from app.models.voucher import Voucher, VoucherStatus
from app.services.audit_service import log_audit
from app.services.reminders import send_pending_and_overdue_reminders


router = APIRouter(dependencies=[Depends(require_role(UserRole.admin))])


@router.get("/users", response_model=list[AdminUserOut])
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    rows = []
    for user in users:
        last_login = (
            db.query(func.max(AuditLog.created_at))
            .filter(AuditLog.actor_user_id == user.id, AuditLog.action == "auth.login")
            .scalar()
        )
        enrollment_count = db.query(func.count(Enrollment.id)).filter(Enrollment.user_id == user.id).scalar() or 0
        completed_count = (
            db.query(func.count(Enrollment.id))
            .filter(Enrollment.user_id == user.id, Enrollment.status == EnrollmentStatus.completed)
            .scalar()
            or 0
        )
        registration_count = db.query(func.count(Registration.id)).filter(Registration.candidate_email == user.email).scalar() or 0
        eligibility_attempts = (
            db.query(func.count(EligibilityTestAttempt.id)).filter(EligibilityTestAttempt.user_id == user.id).scalar() or 0
        )
        avg_score = db.query(func.avg(EligibilityTestAttempt.score)).filter(EligibilityTestAttempt.user_id == user.id).scalar()
        rows.append(
            {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "is_active": user.is_active,
                "avatar_url": user.avatar_url,
                "created_at": user.created_at,
                "updated_at": user.updated_at,
                "last_login_at": last_login,
                "enrollment_count": enrollment_count,
                "registration_count": registration_count,
                "completed_count": completed_count,
                "eligibility_attempts": eligibility_attempts,
                "avg_eligibility_score": round(float(avg_score), 1) if avg_score is not None else None,
            }
        )
    return rows


@router.post("/users", response_model=UserOut)
def create_user(payload: AdminUserCreate, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_role(UserRole.admin))):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        is_active=payload.is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log_audit(
        db,
        actor=admin,
        action="user.create",
        entity="user",
        entity_id=user.id,
        request=request,
        details={"email": user.email, "role": user.role.value, "is_active": user.is_active},
    )
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(user, k, v)
    db.add(user)
    db.commit()
    db.refresh(user)
    log_audit(
        db,
        actor=admin,
        action="user.update",
        entity="user",
        entity_id=user.id,
        request=request,
        details=payload.model_dump(exclude_unset=True),
    )
    return user


@router.get("/analytics")
def analytics(db: Session = Depends(get_db)):
    return {
        "users": db.query(func.count(User.id)).scalar() or 0,
        "certifications": db.query(func.count(Certification.id)).scalar() or 0,
        "enrollments": db.query(func.count(Enrollment.id)).scalar() or 0,
        "tasks": db.query(func.count(Task.id)).scalar() or 0,
        "uploads": db.query(func.count(UploadedFile.id)).scalar() or 0,
        "emails": db.query(func.count(EmailLog.id)).scalar() or 0,
    }


@router.get("/brd-overview")
def brd_overview(db: Session = Depends(get_db)):
    pending_reviews = (
        db.query(func.count(Enrollment.id))
        .filter(Enrollment.admin_review_requested == True)  # noqa: E712
        .scalar()
        or 0
    )
    pending_documents = db.query(func.count(UploadedFile.id)).filter(UploadedFile.purpose != UploadPurpose.certificate).scalar() or 0
    issued_vouchers = db.query(func.count(Voucher.id)).filter(Voucher.status == VoucherStatus.issued).scalar() or 0
    used_vouchers = db.query(func.count(Voucher.id)).filter(Voucher.status == VoucherStatus.redeemed).scalar() or 0
    completed = db.query(func.count(Enrollment.id)).filter(Enrollment.status == EnrollmentStatus.completed).scalar() or 0
    total_enrollments = db.query(func.count(Enrollment.id)).scalar() or 0
    test_attempts = db.query(func.count(EligibilityTestAttempt.id)).scalar() or 0
    eligible_attempts = db.query(func.count(EligibilityTestAttempt.id)).filter(EligibilityTestAttempt.passed == True).scalar() or 0  # noqa: E712
    review_attempts = db.query(func.count(EligibilityTestAttempt.id)).filter(EligibilityTestAttempt.passed == False).scalar() or 0  # noqa: E712
    eligible_users = db.query(func.count(func.distinct(EligibilityTestAttempt.user_id))).filter(EligibilityTestAttempt.passed == True).scalar() or 0  # noqa: E712
    avg_test_score = db.query(func.avg(EligibilityTestAttempt.score)).scalar()

    review_rows = (
        db.query(Enrollment)
        .filter(Enrollment.admin_review_requested == True)  # noqa: E712
        .order_by(Enrollment.updated_at.desc())
        .limit(10)
        .all()
    )
    reviews = []
    for row in review_rows:
        user = db.query(User).filter(User.id == row.user_id).first()
        cert = db.query(Certification).filter(Certification.id == row.certification_id).first()
        reviews.append(
            {
                "id": row.id,
                "user": user.email if user else f"User #{row.user_id}",
                "certification": cert.title if cert else f"Certification #{row.certification_id}",
                "status": row.status,
                "progress_percent": row.progress_percent,
                "updated_at": row.updated_at,
            }
        )

    users_per_cert_rows = (
        db.query(Certification.title, func.count(Enrollment.id).label("users"))
        .join(Enrollment, Enrollment.certification_id == Certification.id)
        .group_by(Certification.title)
        .order_by(func.count(Enrollment.id).desc())
        .limit(8)
        .all()
    )
    active_users = db.query(func.count(User.id)).filter(User.is_active == True).scalar() or 0  # noqa: E712
    active_certifications = (
        db.query(func.count(func.distinct(Enrollment.certification_id)))
        .filter(Enrollment.status.in_([EnrollmentStatus.selected, EnrollmentStatus.in_progress]))
        .scalar()
        or 0
    )
    voucher_rows = db.query(Voucher.status, func.count(Voucher.id)).group_by(Voucher.status).all()
    audit_rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(8).all()
    test_rows = (
        db.query(EligibilityTestAttempt)
        .order_by(EligibilityTestAttempt.created_at.desc(), EligibilityTestAttempt.id.desc())
        .limit(8)
        .all()
    )
    github_rows = _github_activity_rows(db, limit=8)

    eligibility_activity = []
    for row in test_rows:
        attempt_user = db.query(User).filter(User.id == row.user_id).first()
        attempt_cert = db.query(Certification).filter(Certification.id == row.certification_id).first()
        eligibility_activity.append(
            {
                "id": row.id,
                "user_id": row.user_id,
                "user": attempt_user.email if attempt_user else f"User #{row.user_id}",
                "certification_id": row.certification_id,
                "certification": attempt_cert.title if attempt_cert else f"Certification #{row.certification_id}",
                "score": row.score,
                "passed": row.passed,
                "status": row.status,
                "created_at": row.created_at,
            }
        )

    return {
        "metrics": {
            "active_users": active_users,
            "active_certifications": active_certifications,
            "pending_reviews": pending_reviews,
            "pending_documents": pending_documents,
            "issued_vouchers": issued_vouchers,
            "used_vouchers": used_vouchers,
            "success_rate": round((completed / total_enrollments) * 100) if total_enrollments else 0,
            "eligibility_attempts": test_attempts,
            "eligible_attempts": eligible_attempts,
            "eligible_users": eligible_users,
            "eligibility_review_required": review_attempts,
            "avg_test_score": round(float(avg_test_score), 1) if avg_test_score is not None else 0,
        },
        "charts": {
            "users_per_certification": [{"name": title, "users": users} for title, users in users_per_cert_rows],
            "voucher_status": [{"name": status.value if hasattr(status, "value") else str(status), "value": count} for status, count in voucher_rows],
            "eligibility_tests": [
                {"name": "Eligible", "value": eligible_attempts},
                {"name": "Review", "value": review_attempts},
                {"name": "No Attempt", "value": max(0, total_enrollments - test_attempts)},
            ],
        },
        "admin_activity": [
            {
                "id": row.id,
                "action": row.action,
                "entity": row.entity,
                "actor_user_id": row.actor_user_id,
                "created_at": row.created_at,
            }
            for row in audit_rows
        ],
        "eligibility_activity": eligibility_activity,
        "github_activity": github_rows,
        "review_queue": reviews,
        "tooling": [
            {"name": "AI Copilot", "use": "Eligibility explanations, certificate verification, task generation"},
            {"name": "Power Apps", "use": "Approval app for managers and admins"},
            {"name": "Power BI", "use": "Portfolio analytics, completion trends, voucher usage"},
            {"name": "Azure Blob", "use": "Secure document repository"},
        ],
        "recommended_admin_tabs": [
            "Review applications",
            "Approve documents",
            "Assign vouchers",
            "Update results",
            "Monitor Power BI analytics",
        ],
    }


def _github_activity_rows(db: Session, limit: int = 20):
    audit_rows = (
        db.query(AuditLog)
        .filter(AuditLog.action.in_(["drive.provision_repo", "drive.update"]))
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    rows = [
        {
            "id": f"audit-{row.id}",
            "type": row.action,
            "repository": row.details_json,
            "entity_id": row.entity_id,
            "actor_user_id": row.actor_user_id,
            "created_at": row.created_at,
        }
        for row in audit_rows
    ]
    if len(rows) < limit:
        drives = (
            db.query(CertificationDrive)
            .filter(CertificationDrive.repository_prefix.isnot(None))
            .order_by(CertificationDrive.updated_at.desc())
            .limit(limit - len(rows))
            .all()
        )
        rows.extend(
            [
                {
                    "id": f"drive-{drive.id}",
                    "type": "repository.linked",
                    "repository": drive.repository_prefix,
                    "entity_id": str(drive.id),
                    "actor_user_id": None,
                    "created_at": drive.updated_at,
                }
                for drive in drives
            ]
        )
    return rows


@router.get("/github-activity")
def github_activity(db: Session = Depends(get_db)):
    return {"activity": _github_activity_rows(db, limit=50)}


@router.get("/activity-heatmap")
def activity_heatmap(db: Session = Depends(get_db)):
    year_ago = datetime.now(timezone.utc) - timedelta(days=365)
    activity_map = defaultdict(list)

    enrollments = db.query(Enrollment).filter(Enrollment.created_at >= year_ago).all()
    for enrollment in enrollments:
        cert = db.query(Certification).filter(Certification.id == enrollment.certification_id).first()
        user = db.query(User).filter(User.id == enrollment.user_id).first()
        cert_title = cert.title if cert else f"Certification #{enrollment.certification_id}"
        user_label = user.email if user else f"User #{enrollment.user_id}"
        created_day = enrollment.created_at.strftime("%Y-%m-%d")
        action_text = "Started" if enrollment.status != EnrollmentStatus.saved_for_later else "Saved"
        activity_map[created_day].append(
            {
                "id": f"admin_enr_{enrollment.id}",
                "type": "enrollment",
                "title": f"{user_label} {action_text.lower()} {cert_title}",
                "time": enrollment.created_at.isoformat(),
                "url": f"/admin-brd/registrations",
            }
        )
        if enrollment.status == EnrollmentStatus.completed and enrollment.updated_at and enrollment.updated_at >= year_ago:
            completed_day = enrollment.updated_at.strftime("%Y-%m-%d")
            activity_map[completed_day].append(
                {
                    "id": f"admin_comp_{enrollment.id}",
                    "type": "completion",
                    "title": f"{user_label} completed {cert_title}",
                    "time": enrollment.updated_at.isoformat(),
                    "url": "/dashboard",
                }
            )

    tasks = db.query(Task).filter(Task.status == TaskStatus.done, Task.updated_at >= year_ago).all()
    for task in tasks:
        if not task.updated_at:
            continue
        user = db.query(User).filter(User.id == task.user_id).first()
        user_label = user.email if user else f"User #{task.user_id}"
        day = task.updated_at.strftime("%Y-%m-%d")
        activity_map[day].append(
            {
                "id": f"admin_task_{task.id}",
                "type": "task",
                "title": f"{user_label} completed task: {task.title}",
                "time": task.updated_at.isoformat(),
                "url": f"/learning/{task.enrollment_id}" if task.enrollment_id else "/dashboard",
            }
        )

    vouchers = db.query(Voucher).filter(Voucher.created_at >= year_ago).all()
    for voucher in vouchers:
        user = db.query(User).filter(User.id == voucher.user_id).first()
        cert = db.query(Certification).filter(Certification.id == voucher.certification_id).first() if voucher.certification_id else None
        user_label = user.email if user else f"User #{voucher.user_id}"
        cert_title = cert.title if cert else "a certification"
        day = voucher.created_at.strftime("%Y-%m-%d")
        activity_map[day].append(
            {
                "id": f"admin_vouch_{voucher.id}",
                "type": "voucher",
                "title": f"{user_label} received voucher for {cert_title}",
                "time": voucher.created_at.isoformat(),
                "url": "/vouchers",
            }
        )

    attempts = db.query(EligibilityTestAttempt).filter(EligibilityTestAttempt.created_at >= year_ago).all()
    for attempt in attempts:
        user = db.query(User).filter(User.id == attempt.user_id).first()
        cert = db.query(Certification).filter(Certification.id == attempt.certification_id).first()
        user_label = user.email if user else f"User #{attempt.user_id}"
        cert_title = cert.title if cert else f"Certification #{attempt.certification_id}"
        day = attempt.created_at.strftime("%Y-%m-%d")
        activity_map[day].append(
            {
                "id": f"admin_test_{attempt.id}",
                "type": "test",
                "title": f"{user_label} scored {attempt.score}% on {cert_title}",
                "time": attempt.created_at.isoformat(),
                "url": "/dashboard",
            }
        )

    for day in activity_map:
        activity_map[day] = sorted(activity_map[day], key=lambda x: x["time"], reverse=True)

    return {"heatmap": dict(activity_map)}


@router.post("/reminders/run")
def run_reminders(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_role(UserRole.admin))):
    result = send_pending_and_overdue_reminders(db)
    log_audit(db, actor=admin, action="reminders.run", entity="reminder_job", entity_id="default", request=request, details=result)
    return result


@router.get("/audit-logs")
def audit_logs(db: Session = Depends(get_db)):
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(200).all()
    return [
        {
            "id": r.id,
            "actor_user_id": r.actor_user_id,
            "action": r.action,
            "entity": r.entity,
            "entity_id": r.entity_id,
            "ip": r.ip,
            "created_at": r.created_at,
            "details_json": r.details_json,
        }
        for r in rows
    ]


@router.get("/email-logs")
def email_logs(db: Session = Depends(get_db)):
    rows = db.query(EmailLog).order_by(EmailLog.created_at.desc()).limit(200).all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "to_email": r.to_email,
            "subject": r.subject,
            "success": r.success,
            "error": r.error,
            "created_at": r.created_at,
        }
        for r in rows
    ]

