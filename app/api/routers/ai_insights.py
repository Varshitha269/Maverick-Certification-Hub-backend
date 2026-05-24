import datetime as dt
import re
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.assessment import AssessmentOutcome, AssessmentResult
from app.models.certification import Certification, CertificationDrive
from app.models.eligibility import EligibilityTestAttempt
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.registration import Registration, RegistrationStatus
from app.models.task import Task, TaskStatus
from app.models.upload import UploadPurpose, UploadedFile
from app.models.user import User, UserRole
from app.models.voucher import Voucher, VoucherStatus


router = APIRouter()


STOPWORDS = {
    "and",
    "the",
    "for",
    "with",
    "certification",
    "certificate",
    "certified",
    "professional",
    "associate",
    "foundation",
    "fundamentals",
}


def _value(value):
    return value.value if hasattr(value, "value") else value


def _tokens(*values: str | None) -> set[str]:
    raw = " ".join(v or "" for v in values).lower()
    raw = raw.replace("&", " ")
    found = re.findall(r"[a-z0-9+#.]+", raw)
    return {t for t in found if len(t) > 1 and t not in STOPWORDS}


def _pct(value: float) -> int:
    return max(0, min(100, int(round(value))))


def _parse_date(value) -> dt.datetime | None:
    if not value:
        return None
    if isinstance(value, dt.datetime):
        return value
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _cert_payload(cert: Certification, extra: dict | None = None) -> dict:
    payload = {
        "id": cert.id,
        "title": cert.title,
        "provider": cert.provider,
        "category": cert.category,
        "level": cert.level,
        "estimated_hours": cert.estimated_hours,
        "duration": cert.duration,
        "description": cert.description,
        "prerequisites": cert.prerequisites,
    }
    if extra:
        payload.update(extra)
    return payload


def _user_cert_context(db: Session, user: User) -> dict:
    enrollments = db.query(Enrollment).filter(Enrollment.user_id == user.id).all()
    certs = {
        cert.id: cert
        for cert in db.query(Certification)
        .filter(Certification.id.in_([e.certification_id for e in enrollments] or [0]))
        .all()
    }
    completed = [e for e in enrollments if e.status == EnrollmentStatus.completed]
    active = [e for e in enrollments if e.status in {EnrollmentStatus.selected, EnrollmentStatus.in_progress}]
    completed_certs = [certs[e.certification_id] for e in completed if e.certification_id in certs]
    active_certs = [certs[e.certification_id] for e in active if e.certification_id in certs]
    skill_tokens = set()
    for cert in completed_certs + active_certs:
        skill_tokens.update(_tokens(cert.title, cert.provider, cert.category, cert.tags))
    preferred = Counter(c.provider for c in completed_certs + active_certs if c.provider)
    categories = Counter(c.category for c in completed_certs + active_certs if c.category)
    return {
        "enrollments": enrollments,
        "completed": completed,
        "active": active,
        "completed_certs": completed_certs,
        "active_certs": active_certs,
        "skill_tokens": skill_tokens,
        "preferred_providers": [p for p, _ in preferred.most_common(3)],
        "preferred_categories": [c for c, _ in categories.most_common(3)],
    }


def _cert_match_score(cert: Certification, ctx: dict) -> tuple[int, list[str], list[str]]:
    cert_tokens = _tokens(cert.title, cert.provider, cert.category, cert.tags, cert.prerequisites)
    overlap = cert_tokens.intersection(ctx["skill_tokens"])
    score = 35
    reasons: list[str] = []
    gaps: list[str] = []

    if cert.provider in ctx["preferred_providers"]:
        score += 20
        reasons.append(f"Matches your existing {cert.provider} learning history")
    if cert.category and cert.category in ctx["preferred_categories"]:
        score += 15
        reasons.append(f"Fits your strongest category: {cert.category}")
    if overlap:
        score += min(20, len(overlap) * 4)
        reasons.append(f"Shares skills: {', '.join(sorted(list(overlap))[:4])}")
    if not ctx["completed"] and str(cert.level or "").lower() in {"beginner", "foundational", "fundamentals"}:
        score += 15
        reasons.append("Good first certification based on level")
    if len(ctx["completed"]) >= 2 and str(cert.level or "").lower() in {"intermediate", "advanced", "professional"}:
        score += 10
        reasons.append("Good next step after your completed certifications")

    missing = sorted(list(cert_tokens.difference(ctx["skill_tokens"])))[:5]
    if missing:
        gaps = missing
    if not reasons:
        reasons.append("Useful option to broaden your certification portfolio")
    return _pct(score), reasons, gaps


def _candidate_score(db: Session, reg: Registration, drive: CertificationDrive | None = None) -> dict:
    user = db.query(User).filter(User.email == reg.candidate_email).first()
    status = _value(reg.status)
    score = 20
    reasons = []
    risks = []

    status_scores = {
        RegistrationStatus.passed.value: 95,
        RegistrationStatus.voucher_issued.value: 86,
        RegistrationStatus.assessed.value: 76,
        RegistrationStatus.scheduled.value: 72,
        RegistrationStatus.eligible.value: 68,
        RegistrationStatus.eligible_pending_approval.value: 55,
        RegistrationStatus.submitted.value: 40,
        RegistrationStatus.failed.value: 34,
        RegistrationStatus.ineligible.value: 15,
    }
    score = status_scores.get(status, score)
    reasons.append(f"Current registration status is {status}")

    if reg.prior_attempts:
        penalty = min(18, reg.prior_attempts * 6)
        score -= penalty
        risks.append(f"{reg.prior_attempts} prior attempt(s)")

    if user:
        completed = (
            db.query(func.count(Enrollment.id))
            .filter(Enrollment.user_id == user.id, Enrollment.status == EnrollmentStatus.completed)
            .scalar()
            or 0
        )
        active = (
            db.query(func.count(Enrollment.id))
            .filter(Enrollment.user_id == user.id, Enrollment.status.in_([EnrollmentStatus.selected, EnrollmentStatus.in_progress]))
            .scalar()
            or 0
        )
        avg_score = db.query(func.avg(EligibilityTestAttempt.score)).filter(EligibilityTestAttempt.user_id == user.id).scalar()
        uploads = db.query(func.count(UploadedFile.id)).filter(UploadedFile.user_id == user.id).scalar() or 0
        score += min(15, completed * 5)
        score += min(8, active * 2)
        if avg_score is not None:
            score += (float(avg_score) - 60) * 0.2
            reasons.append(f"Average eligibility score is {round(float(avg_score), 1)}%")
        if uploads:
            score += 4
            reasons.append("Has supporting documents uploaded")
        if completed:
            reasons.append(f"Completed {completed} certification(s)")
    else:
        risks.append("Candidate email is not linked to a platform user")
        score -= 8

    if drive and drive.target_count:
        regs_for_drive = db.query(func.count(Registration.id)).filter(Registration.drive_id == drive.id).scalar() or 0
        if regs_for_drive > drive.target_count:
            risks.append("Drive is above target capacity")

    return {
        "registration_id": reg.id,
        "drive_id": reg.drive_id,
        "candidate_name": reg.candidate_name,
        "candidate_email": reg.candidate_email,
        "status": status,
        "score": _pct(score),
        "recommendation": "approve" if score >= 65 else "review" if score >= 40 else "hold",
        "reasons": reasons[:4],
        "risks": risks[:4],
    }


def _drive_stats(db: Session, drive: CertificationDrive) -> dict:
    regs = db.query(Registration).filter(Registration.drive_id == drive.id).all()
    results = db.query(AssessmentResult).filter(AssessmentResult.drive_id == drive.id).all()
    vouchers = db.query(Voucher).filter(Voucher.drive_id == drive.id).all()
    status_counts = Counter(_value(r.status) for r in regs)
    result_counts = Counter(_value(r.outcome) for r in results)
    voucher_counts = Counter(_value(v.status) for v in vouchers)
    passes = result_counts.get(AssessmentOutcome.pass_.value, 0)
    assessed = len([r for r in results if _value(r.outcome) != AssessmentOutcome.pending.value])
    target = drive.target_count or 0
    return {
        "drive_id": drive.id,
        "drive_name": drive.name,
        "status": drive.status,
        "target_count": target,
        "voucher_budget": drive.voucher_budget or 0,
        "registrations": len(regs),
        "status_counts": dict(status_counts),
        "assessments": len(results),
        "result_counts": dict(result_counts),
        "pass_rate": _pct((passes / assessed) * 100) if assessed else 0,
        "vouchers": len(vouchers),
        "voucher_counts": dict(voucher_counts),
        "budget_usage": _pct((len(vouchers) / (drive.voucher_budget or 1)) * 100) if drive.voucher_budget else 0,
    }


def _drive_risks_and_actions(stats: dict) -> tuple[list[str], list[str]]:
    risks = []
    actions = []
    pending = stats["status_counts"].get(RegistrationStatus.submitted.value, 0) + stats["status_counts"].get(
        RegistrationStatus.eligible_pending_approval.value, 0
    )
    if pending:
        risks.append(f"{pending} registration(s) still need eligibility or approval action")
        actions.append("Review pending eligibility decisions before issuing vouchers")
    if stats["target_count"] and stats["registrations"] < stats["target_count"]:
        gap = stats["target_count"] - stats["registrations"]
        risks.append(f"Drive is {gap} registration(s) below target")
        actions.append("Send a targeted announcement to eligible users")
    if stats["voucher_budget"] and stats["budget_usage"] >= 85:
        risks.append("Voucher budget is close to fully allocated")
        actions.append("Prioritize vouchers for the highest ranked candidates")
    if stats["assessments"] and stats["pass_rate"] < 60:
        risks.append(f"Pass rate is low at {stats['pass_rate']}%")
        actions.append("Schedule a preparation session for weaker topics")
    if not risks:
        risks.append("No major operational risk detected from current data")
    if not actions:
        actions.append("Continue monitoring registration, voucher, and result movement")
    return risks, actions


def _certificate_confidence(db: Session, upload: UploadedFile) -> dict:
    enrollment = db.query(Enrollment).filter(Enrollment.id == upload.enrollment_id).first() if upload.enrollment_id else None
    cert = db.query(Certification).filter(Certification.id == enrollment.certification_id).first() if enrollment else None
    if not cert:
        return {
            "upload_id": upload.id,
            "confidence": 25,
            "status": "needs_review",
            "matched": False,
            "reason": "Upload is not linked to an enrollment with a certification",
            "signals": ["missing enrollment link"],
        }

    evidence = f"{upload.original_filename} {upload.content_type or ''} {upload.review_reason or ''}"
    expected = _tokens(cert.title, cert.provider)
    found = _tokens(evidence)
    title_hit = expected.intersection(found)
    provider_hit = bool(_tokens(cert.provider).intersection(found))
    score = 25 + min(45, len(title_hit) * 12) + (20 if provider_hit else 0)
    if upload.purpose == UploadPurpose.certificate:
        score += 8
    if str(upload.review_status).lower() == "approved":
        score += 12
    elif str(upload.review_status).lower() == "rejected":
        score -= 20
    matched = score >= 70
    signals = []
    if title_hit:
        signals.append(f"Matched certification terms: {', '.join(sorted(title_hit)[:4])}")
    if provider_hit:
        signals.append(f"Matched provider: {cert.provider}")
    if upload.purpose == UploadPurpose.certificate:
        signals.append("Uploaded as certificate proof")
    if not signals:
        signals.append("Filename does not strongly match expected certification")
    return {
        "upload_id": upload.id,
        "filename": upload.original_filename,
        "expected_certification": cert.title,
        "expected_provider": cert.provider,
        "confidence": _pct(score),
        "status": "matched" if matched else "needs_review",
        "matched": matched,
        "reason": "Certificate evidence appears consistent" if matched else "Manual review recommended before approval",
        "signals": signals,
    }


@router.get("/user/roadmap")
def user_roadmap(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ctx = _user_cert_context(db, user)
    all_certs = db.query(Certification).order_by(Certification.id.asc()).all()
    owned_ids = {e.certification_id for e in ctx["enrollments"]}
    candidates = [c for c in all_certs if c.id not in owned_ids]
    scored = sorted(((_cert_match_score(c, ctx), c) for c in candidates), key=lambda item: item[0][0], reverse=True)
    next_certs = [_cert_payload(cert, {"match_score": score, "reasons": reasons, "skill_gaps": gaps}) for (score, reasons, gaps), cert in scored[:5]]

    level = "Beginner" if len(ctx["completed"]) <= 1 else "Intermediate" if len(ctx["completed"]) <= 4 else "Advanced"
    focus = ctx["preferred_categories"][0] if ctx["preferred_categories"] else "cloud and professional skills"
    roadmap = [
        {"stage": "Now", "title": "Finish active enrollments", "details": f"{len(ctx['active'])} active certification(s) need steady progress."},
        {"stage": "Next", "title": "Close skill gaps", "details": f"Focus on {focus} topics and prerequisites before the next drive."},
        {"stage": "Later", "title": "Advance certification level", "details": f"Move from {level.lower()} readiness into the next role-aligned credential."},
    ]
    gaps = sorted(set(g for cert in next_certs for g in cert["skill_gaps"]))[:8]
    return {
        "profile": {
            "level": level,
            "completed_count": len(ctx["completed"]),
            "active_count": len(ctx["active"]),
            "preferred_providers": ctx["preferred_providers"],
            "preferred_categories": ctx["preferred_categories"],
        },
        "roadmap": roadmap,
        "skill_gaps": gaps,
        "recommended_next": next_certs,
    }


@router.get("/user/certification-matches")
def certification_matches(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ctx = _user_cert_context(db, user)
    owned_ids = {e.certification_id for e in ctx["enrollments"]}
    rows = [c for c in db.query(Certification).all() if c.id not in owned_ids]
    ranked = []
    for cert in rows:
        score, reasons, gaps = _cert_match_score(cert, ctx)
        ranked.append(_cert_payload(cert, {"match_score": score, "reasons": reasons, "skill_gaps": gaps}))
    ranked.sort(key=lambda item: item["match_score"], reverse=True)
    return {"matches": ranked[:12]}


@router.post("/user/learning-path")
def learning_path(payload: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    goal = (payload.get("goal") or "Cloud Engineer").strip()
    goal_tokens = _tokens(goal)
    ctx = _user_cert_context(db, user)
    owned_ids = {e.certification_id for e in ctx["enrollments"]}
    certs = [c for c in db.query(Certification).all() if c.id not in owned_ids]

    def rank(cert: Certification):
        score, reasons, gaps = _cert_match_score(cert, ctx)
        score += min(25, len(goal_tokens.intersection(_tokens(cert.title, cert.category, cert.tags))) * 8)
        return score, reasons, gaps

    ranked = sorted(((rank(c), c) for c in certs), key=lambda item: item[0][0], reverse=True)[:6]
    steps = []
    for index, ((score, reasons, gaps), cert) in enumerate(ranked, start=1):
        steps.append(
            {
                "step": index,
                "certification": _cert_payload(cert),
                "match_score": _pct(score),
                "focus": reasons[0] if reasons else "Build role-aligned capability",
                "skill_gaps": gaps[:4],
                "estimated_weeks": max(2, round((cert.estimated_hours or 30) / 6)),
            }
        )
    return {
        "goal": goal,
        "summary": f"Suggested path toward {goal} using your current certification history.",
        "steps": steps,
    }


@router.get("/admin/drive-insights/{drive_id}")
def admin_drive_summary(drive_id: int, db: Session = Depends(get_db), admin: User = Depends(require_role(UserRole.admin))):  # noqa: ARG001
    drive = db.query(CertificationDrive).filter(CertificationDrive.id == drive_id).first()
    if not drive:
        raise HTTPException(status_code=404, detail="Drive not found")
    stats = _drive_stats(db, drive)
    risks, actions = _drive_risks_and_actions(stats)
    return {"summary": f"{drive.name} has {stats['registrations']} registration(s) and {stats['pass_rate']}% pass rate.", "stats": stats, "risks": risks, "next_actions": actions}


@router.get("/admin/candidate-ranking")
def admin_candidate_ranking(drive_id: int | None = None, db: Session = Depends(get_db), admin: User = Depends(require_role(UserRole.admin))):  # noqa: ARG001
    q = db.query(Registration)
    if drive_id is not None:
        q = q.filter(Registration.drive_id == drive_id)
    regs = q.order_by(Registration.created_at.desc()).limit(250).all()
    drives = {d.id: d for d in db.query(CertificationDrive).filter(CertificationDrive.id.in_([r.drive_id for r in regs] or [0])).all()}
    rows = [_candidate_score(db, reg, drives.get(reg.drive_id)) for reg in regs]
    rows.sort(key=lambda item: item["score"], reverse=True)
    return {"candidates": rows}


@router.get("/admin/voucher-recommendations")
def admin_voucher_recommendations(drive_id: int | None = None, db: Session = Depends(get_db), admin: User = Depends(require_role(UserRole.admin))):  # noqa: ARG001
    ranked = admin_candidate_ranking(drive_id=drive_id, db=db, admin=admin)["candidates"]
    recommendations = []
    eligible_statuses = {"eligible", "scheduled", "assessed", "passed"}
    ready_count = 0
    already_issued_count = 0
    missing_user_count = 0
    for candidate in ranked:
        user = db.query(User).filter(User.email == candidate["candidate_email"]).first()
        if not user:
            missing_user_count += 1
        existing = None
        if user:
            q = db.query(Voucher).filter(Voucher.user_id == user.id, Voucher.status == VoucherStatus.issued)
            if drive_id is not None:
                q = q.filter(Voucher.drive_id == drive_id)
            existing = q.first()
        if candidate["status"] in eligible_statuses:
            ready_count += 1
        if existing:
            already_issued_count += 1
        if candidate["status"] in eligible_statuses and not existing:
            recommendations.append(
                {
                    **candidate,
                    "user_id": user.id if user else None,
                    "priority": "high" if candidate["score"] >= 75 else "medium",
                    "reason": "Ready for voucher allocation based on eligibility and completion signals",
                }
            )
    source = {
        "table": "registrations",
        "drive_id": drive_id,
        "eligible_statuses": sorted(eligible_statuses),
        "ranked_candidates": len(ranked),
        "ready_candidates": ready_count,
        "already_issued_candidates": already_issued_count,
        "unlinked_candidate_users": missing_user_count,
    }
    message = (
        f"Found {len(recommendations)} voucher recommendation(s) from registration statuses: "
        f"{', '.join(source['eligible_statuses'])}."
    )
    if drive_id is not None and not recommendations:
        message = (
            "No voucher recommendations for this drive. Use a drive with registrations in "
            "eligible, scheduled, assessed, or passed status, or clear the drive filter to scan all drives."
        )
    return {"recommendations": recommendations[:30], "source": source, "message": message}


@router.post("/admin/certificate-confidence")
def admin_certificate_confidence(payload: dict, db: Session = Depends(get_db), admin: User = Depends(require_role(UserRole.admin))):  # noqa: ARG001
    upload_id = payload.get("upload_id")
    if not upload_id:
        raise HTTPException(status_code=400, detail="Missing 'upload_id'")
    upload = db.query(UploadedFile).filter(UploadedFile.id == int(upload_id)).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    return _certificate_confidence(db, upload)


@router.post("/reminders/message")
def reminder_message(payload: dict, user: User = Depends(get_current_user)):
    reminder_type = (payload.get("type") or "progress").strip()
    audience = (payload.get("audience") or ("admins" if user.role == UserRole.admin else "learner")).strip()
    context = (payload.get("context") or "").strip()
    templates = {
        "progress": "You still have certification tasks waiting. Please update your progress this week so your learning plan stays on track.",
        "voucher": "Your voucher is ready or needs action. Please review the voucher details and complete the next step before it expires.",
        "drive": "A certification drive needs attention. Please review the drive timeline, eligibility status, and pending actions.",
        "upload": "A document is pending review or re-upload. Please check the upload status and provide a clear supporting file if needed.",
        "risk": "Some learners are showing delay risk. Please review the risk list and send targeted support reminders.",
    }
    message = templates.get(reminder_type, templates["progress"])
    if context:
        message = f"{message}\n\nContext: {context}"
    return {
        "type": reminder_type,
        "audience": audience,
        "subject": f"Maverick Certification Hub reminder: {reminder_type.title()}",
        "message": message,
        "channels": ["in-app", "email"],
    }


@router.get("/admin/dropout-risk")
def admin_dropout_risk(db: Session = Depends(get_db), admin: User = Depends(require_role(UserRole.admin))):  # noqa: ARG001
    now = dt.datetime.now(dt.timezone.utc)
    rows = (
        db.query(Enrollment)
        .filter(Enrollment.status.in_([EnrollmentStatus.selected, EnrollmentStatus.in_progress]))
        .order_by(Enrollment.updated_at.asc())
        .limit(500)
        .all()
    )
    risks = []
    for enrollment in rows:
        user = db.query(User).filter(User.id == enrollment.user_id).first()
        cert = db.query(Certification).filter(Certification.id == enrollment.certification_id).first()
        tasks = db.query(Task).filter(Task.enrollment_id == enrollment.id).all()
        open_tasks = [t for t in tasks if t.status != TaskStatus.done]
        overdue = []
        for task in open_tasks:
            due = _parse_date(task.due_date)
            if due and due < now:
                overdue.append(task)
        updated = enrollment.updated_at or enrollment.created_at
        inactive_days = (now - updated).days if updated else 0
        score = (100 - enrollment.progress_percent) * 0.35 + len(overdue) * 10 + min(35, inactive_days * 2)
        level = "high" if score >= 65 else "medium" if score >= 35 else "low"
        if level != "low":
            risks.append(
                {
                    "enrollment_id": enrollment.id,
                    "user_id": enrollment.user_id,
                    "user": user.email if user else f"User #{enrollment.user_id}",
                    "certification": cert.title if cert else f"Certification #{enrollment.certification_id}",
                    "risk_score": _pct(score),
                    "risk_level": level,
                    "progress_percent": enrollment.progress_percent,
                    "overdue_tasks": len(overdue),
                    "inactive_days": inactive_days,
                    "recommended_action": "Send support reminder and review blockers" if level == "high" else "Nudge learner to update progress",
                }
            )
    risks.sort(key=lambda item: item["risk_score"], reverse=True)
    return {"risks": risks[:50]}


@router.get("/admin/drive-report/{drive_id}")
def admin_drive_report(drive_id: int, db: Session = Depends(get_db), admin: User = Depends(require_role(UserRole.admin))):  # noqa: ARG001
    drive = db.query(CertificationDrive).filter(CertificationDrive.id == drive_id).first()
    if not drive:
        raise HTTPException(status_code=404, detail="Drive not found")
    cert = db.query(Certification).filter(Certification.id == drive.certification_id).first()
    stats = _drive_stats(db, drive)
    risks, actions = _drive_risks_and_actions(stats)
    candidates = admin_candidate_ranking(drive_id=drive_id, db=db, admin=admin)["candidates"][:5]
    vouchers = admin_voucher_recommendations(drive_id=drive_id, db=db, admin=admin)["recommendations"][:5]
    return {
        "title": f"AI Drive Report: {drive.name}",
        "certification": cert.title if cert else None,
        "provider": cert.provider if cert else None,
        "executive_summary": f"{drive.name} currently has {stats['registrations']} registration(s), {stats['vouchers']} voucher(s), and {stats['pass_rate']}% pass rate.",
        "stats": stats,
        "risks": risks,
        "next_actions": actions,
        "top_candidates": candidates,
        "voucher_recommendations": vouchers,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
