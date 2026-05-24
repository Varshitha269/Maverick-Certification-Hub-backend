import datetime as dt
import re
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_
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
        parsed = value
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
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


def _candidate_scores(db: Session, regs: list[Registration], drives: dict[int, CertificationDrive]) -> list[dict]:
    if not regs:
        return []

    emails = {str(reg.candidate_email or "").lower() for reg in regs if reg.candidate_email}
    users = (
        db.query(User)
        .filter(func.lower(User.email).in_(emails or {"__none__"}))
        .all()
    )
    users_by_email = {user.email.lower(): user for user in users}
    user_ids = [user.id for user in users]

    completed_counts = dict(
        db.query(Enrollment.user_id, func.count(Enrollment.id))
        .filter(Enrollment.user_id.in_(user_ids or [0]), Enrollment.status == EnrollmentStatus.completed)
        .group_by(Enrollment.user_id)
        .all()
    )
    active_counts = dict(
        db.query(Enrollment.user_id, func.count(Enrollment.id))
        .filter(
            Enrollment.user_id.in_(user_ids or [0]),
            Enrollment.status.in_([EnrollmentStatus.selected, EnrollmentStatus.in_progress]),
        )
        .group_by(Enrollment.user_id)
        .all()
    )
    avg_scores = dict(
        db.query(EligibilityTestAttempt.user_id, func.avg(EligibilityTestAttempt.score))
        .filter(EligibilityTestAttempt.user_id.in_(user_ids or [0]))
        .group_by(EligibilityTestAttempt.user_id)
        .all()
    )
    upload_counts = dict(
        db.query(UploadedFile.user_id, func.count(UploadedFile.id))
        .filter(UploadedFile.user_id.in_(user_ids or [0]))
        .group_by(UploadedFile.user_id)
        .all()
    )
    regs_for_drive = dict(
        db.query(Registration.drive_id, func.count(Registration.id))
        .filter(Registration.drive_id.in_([reg.drive_id for reg in regs] or [0]))
        .group_by(Registration.drive_id)
        .all()
    )

    rows = []
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
    for reg in regs:
        user = users_by_email.get(str(reg.candidate_email or "").lower())
        drive = drives.get(reg.drive_id)
        status = _value(reg.status)
        score = status_scores.get(status, 20)
        reasons = [f"Current registration status is {status}"]
        risks = []

        if reg.prior_attempts:
            penalty = min(18, reg.prior_attempts * 6)
            score -= penalty
            risks.append(f"{reg.prior_attempts} prior attempt(s)")

        if user:
            completed = completed_counts.get(user.id, 0)
            active = active_counts.get(user.id, 0)
            avg_score = avg_scores.get(user.id)
            uploads = upload_counts.get(user.id, 0)
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

        if drive and drive.target_count and regs_for_drive.get(drive.id, 0) > drive.target_count:
            risks.append("Drive is above target capacity")

        rows.append(
            {
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
        )
    return rows
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


def _enrollment_readiness(db: Session, enrollment: Enrollment, user: User) -> dict:
    cert = db.query(Certification).filter(Certification.id == enrollment.certification_id).first()
    tasks = db.query(Task).filter(Task.enrollment_id == enrollment.id).all()
    done_tasks = [task for task in tasks if task.status == TaskStatus.done]
    open_tasks = [task for task in tasks if task.status != TaskStatus.done]
    now = dt.datetime.now(dt.timezone.utc)
    overdue = []
    for task in open_tasks:
        due = _parse_date(task.due_date)
        if due and due < now:
            overdue.append(task)

    task_score = (len(done_tasks) / len(tasks)) * 100 if tasks else enrollment.progress_percent
    progress_score = enrollment.progress_percent or 0
    attempts = (
        db.query(EligibilityTestAttempt)
        .filter(EligibilityTestAttempt.user_id == user.id, EligibilityTestAttempt.certification_id == enrollment.certification_id)
        .order_by(EligibilityTestAttempt.created_at.desc())
        .all()
    )
    latest_attempt = attempts[0] if attempts else None
    eligibility_score = latest_attempt.score if latest_attempt else 45
    uploads = db.query(func.count(UploadedFile.id)).filter(UploadedFile.user_id == user.id, UploadedFile.enrollment_id == enrollment.id).scalar() or 0
    days_signal = 50
    target = _parse_date(enrollment.target_completion_date)
    if target:
        days_left = (target - now).days
        if days_left >= 14:
            days_signal = 80
        elif days_left >= 0:
            days_signal = 60
        else:
            days_signal = 25

    readiness = _pct((task_score * 0.32) + (progress_score * 0.28) + (eligibility_score * 0.25) + (days_signal * 0.10) + (min(uploads, 2) * 2.5) - (len(overdue) * 5))
    if readiness >= 80:
        level = "exam_ready"
        action = "Book the exam or request voucher allocation."
    elif readiness >= 60:
        level = "nearly_ready"
        action = "Close remaining tasks and revise weak topics before booking."
    elif readiness >= 40:
        level = "needs_preparation"
        action = "Follow a focused two-week study sprint before attempting the exam."
    else:
        level = "not_ready"
        action = "Continue foundational preparation before using an exam voucher."
    signals = [
        f"Task completion is {round(task_score)}%",
        f"Enrollment progress is {progress_score}%",
        f"Latest eligibility score is {eligibility_score}%" if latest_attempt else "No eligibility score found",
    ]
    if overdue:
        signals.append(f"{len(overdue)} overdue task(s)")
    if uploads:
        signals.append(f"{uploads} supporting upload(s)")
    return {
        "enrollment_id": enrollment.id,
        "certification_id": enrollment.certification_id,
        "certification": cert.title if cert else f"Certification #{enrollment.certification_id}",
        "provider": cert.provider if cert else None,
        "readiness_score": readiness,
        "readiness_level": level,
        "recommended_action": action,
        "signals": signals,
        "open_tasks": len(open_tasks),
        "overdue_tasks": len(overdue),
    }


def _historical_pass_rate(db: Session, certification_id: int | None = None) -> int:
    q = db.query(AssessmentResult)
    if certification_id is not None:
        drive_ids = [row[0] for row in db.query(CertificationDrive.id).filter(CertificationDrive.certification_id == certification_id).all()]
        q = q.filter(AssessmentResult.drive_id.in_(drive_ids or [0]))
    rows = q.filter(AssessmentResult.outcome.in_([AssessmentOutcome.pass_, AssessmentOutcome.fail, AssessmentOutcome.no_show])).all()
    if not rows:
        return 60
    passed = len([row for row in rows if row.outcome == AssessmentOutcome.pass_])
    return _pct((passed / len(rows)) * 100)


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


@router.get("/user/exam-readiness")
def user_exam_readiness(
    enrollment_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Enrollment).filter(Enrollment.user_id == user.id)
    if enrollment_id is not None:
        q = q.filter(Enrollment.id == enrollment_id)
    else:
        q = q.filter(Enrollment.status.in_([EnrollmentStatus.selected, EnrollmentStatus.in_progress]))
    enrollments = q.order_by(Enrollment.updated_at.desc(), Enrollment.created_at.desc()).limit(12).all()
    rows = [_enrollment_readiness(db, enrollment, user) for enrollment in enrollments]
    rows.sort(key=lambda item: item["readiness_score"], reverse=True)
    if enrollment_id is not None and not rows:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    return {
        "readiness": rows,
        "summary": "Exam readiness combines task completion, progress, eligibility score, deadline pressure, and evidence uploads.",
    }


@router.post("/user/resume-recommendations")
def resume_recommendations(payload: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    resume_text = (payload.get("resume_text") or payload.get("text") or "").strip()
    goal = (payload.get("goal") or "").strip()
    if not resume_text:
        raise HTTPException(status_code=400, detail="Missing resume_text")
    resume_tokens = _tokens(resume_text, goal)
    ctx = _user_cert_context(db, user)
    owned_ids = {enrollment.certification_id for enrollment in ctx["enrollments"]}
    rows = []
    for cert in db.query(Certification).order_by(Certification.id.asc()).all():
        cert_tokens = _tokens(cert.title, cert.provider, cert.category, cert.tags, cert.prerequisites, cert.description)
        overlap = sorted(resume_tokens.intersection(cert_tokens))
        gap_tokens = sorted(cert_tokens.difference(resume_tokens))[:5]
        score = 30 + min(45, len(overlap) * 7)
        if goal and _tokens(goal).intersection(cert_tokens):
            score += 18
        if cert.id in owned_ids:
            score -= 18
        if cert.category and cert.category in ctx["preferred_categories"]:
            score += 8
        rows.append(
            _cert_payload(
                cert,
                {
                    "resume_match_score": _pct(score),
                    "matched_skills": overlap[:6],
                    "skill_gaps": gap_tokens,
                    "reason": f"Matches resume terms: {', '.join(overlap[:4])}" if overlap else "Useful stretch certification for the target profile",
                    "already_in_plan": cert.id in owned_ids,
                },
            )
        )
    rows.sort(key=lambda item: item["resume_match_score"], reverse=True)
    return {
        "goal": goal or None,
        "detected_skills": sorted(resume_tokens)[:30],
        "recommendations": rows[:10],
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
    rows = _candidate_scores(db, regs, drives)
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
    emails = {candidate["candidate_email"].lower() for candidate in ranked if candidate.get("candidate_email")}
    users = db.query(User).filter(func.lower(User.email).in_(emails or {"__none__"})).all()
    users_by_email = {user.email.lower(): user for user in users}
    voucher_q = db.query(Voucher).filter(Voucher.user_id.in_([user.id for user in users] or [0]), Voucher.status == VoucherStatus.issued)
    if drive_id is not None:
        voucher_q = voucher_q.filter(Voucher.drive_id == drive_id)
    issued_voucher_keys = {(voucher.user_id, voucher.drive_id) for voucher in voucher_q.all()}
    for candidate in ranked:
        user = users_by_email.get(str(candidate["candidate_email"] or "").lower())
        if not user:
            missing_user_count += 1
        existing = bool(
            user
            and (
                (user.id, candidate["drive_id"]) in issued_voucher_keys
                or (drive_id is None and any(key[0] == user.id for key in issued_voucher_keys))
            )
        )
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


@router.get("/admin/voucher-budget-optimizer")
def admin_voucher_budget_optimizer(
    drive_id: int | None = None,
    budget: int | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):  # noqa: ARG001
    recommendations = admin_voucher_recommendations(drive_id=drive_id, db=db, admin=admin)["recommendations"]
    if budget is None:
        if drive_id is not None:
            drive = db.query(CertificationDrive).filter(CertificationDrive.id == drive_id).first()
            issued = db.query(func.count(Voucher.id)).filter(Voucher.drive_id == drive_id, Voucher.status == VoucherStatus.issued).scalar() or 0
            budget = max(0, (drive.voucher_budget or 0) - issued) if drive else 0
        else:
            budget = min(10, len(recommendations))
    budget = max(0, int(budget or 0))
    allocations = []
    skipped = []
    for candidate in recommendations:
        item = {
            **candidate,
            "allocation_rank": len(allocations) + 1,
            "budget_reason": "Highest readiness score within available voucher capacity",
        }
        if len(allocations) < budget:
            allocations.append(item)
        else:
            skipped.append({**candidate, "skip_reason": "Outside current voucher budget"})
    return {
        "budget": budget,
        "allocated_count": len(allocations),
        "skipped_count": len(skipped),
        "allocations": allocations,
        "skipped": skipped[:20],
        "summary": f"Allocated {len(allocations)} voucher slot(s) from {len(recommendations)} eligible recommendation(s).",
    }


@router.get("/admin/reconduct-recommendations")
def admin_reconduct_recommendations(db: Session = Depends(get_db), admin: User = Depends(require_role(UserRole.admin))):  # noqa: ARG001
    rows = []
    activity_drive_ids = {
        row[0]
        for row in db.query(Registration.drive_id).distinct().all()
    }.union(
        {
            row[0]
            for row in db.query(AssessmentResult.drive_id).distinct().all()
        }
    )
    drives = (
        db.query(CertificationDrive)
        .filter(CertificationDrive.id.in_(list(activity_drive_ids) or [0]))
        .order_by(CertificationDrive.id.desc())
        .limit(100)
        .all()
    )
    for drive in drives:
        stats = _drive_stats(db, drive)
        failed = stats["result_counts"].get(AssessmentOutcome.fail.value, 0)
        no_show = stats["result_counts"].get(AssessmentOutcome.no_show.value, 0)
        passed = stats["result_counts"].get(AssessmentOutcome.pass_.value, 0)
        demand = stats["registrations"]
        closed_signal = 15 if drive.status in {"closed", "completed"} else 0
        pass_gap = max(0, 75 - stats["pass_rate"]) * 0.35 if stats["assessments"] else 0
        score = closed_signal + min(30, demand * 4) + min(25, (failed + no_show) * 6) + pass_gap
        if stats["voucher_budget"] and stats["voucher_counts"].get(VoucherStatus.issued.value, 0) >= stats["voucher_budget"]:
            score -= 8
        if score < 25:
            continue
        cert = db.query(Certification).filter(Certification.id == drive.certification_id).first()
        reasons = []
        if drive.status in {"closed", "completed"}:
            reasons.append("Previous drive is already conducted or closed")
        if failed or no_show:
            reasons.append(f"{failed + no_show} failed/no-show candidate(s) can be retargeted")
        if demand:
            reasons.append(f"{demand} registration(s) show demand")
        if stats["pass_rate"] and stats["pass_rate"] < 75:
            reasons.append(f"Pass rate is {stats['pass_rate']}%")
        rows.append(
            {
                "drive_id": drive.id,
                "drive_name": drive.name,
                "certification": cert.title if cert else None,
                "provider": cert.provider if cert else None,
                "reconduct_score": _pct(score),
                "registrations": demand,
                "pass_rate": stats["pass_rate"],
                "failed_or_no_show": failed + no_show,
                "recommended_action": "Re-conduct with targeted preparation" if score >= 65 else "Monitor demand before re-conducting",
                "reasons": reasons[:4],
            }
        )
    rows.sort(key=lambda item: item["reconduct_score"], reverse=True)
    return {"recommendations": rows[:20]}


@router.get("/admin/pass-rate-predictor")
def admin_pass_rate_predictor(
    drive_id: int | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):  # noqa: ARG001
    q = db.query(CertificationDrive)
    if drive_id is not None:
        q = q.filter(CertificationDrive.id == drive_id)
    else:
        active_drive_ids = [row[0] for row in db.query(Registration.drive_id).distinct().all()]
        q = q.filter(CertificationDrive.id.in_(active_drive_ids or [0]))
    drives = q.order_by(CertificationDrive.id.desc()).limit(100).all()
    drive_ids = [drive.id for drive in drives]
    drive_map = {drive.id: drive for drive in drives}
    regs = db.query(Registration).filter(Registration.drive_id.in_(drive_ids or [0])).all()
    regs_by_drive: dict[int, list[Registration]] = {}
    for reg in regs:
        regs_by_drive.setdefault(reg.drive_id, []).append(reg)

    scored_candidates = _candidate_scores(db, regs, drive_map)
    scores_by_drive: dict[int, list[dict]] = {}
    for candidate in scored_candidates:
        scores_by_drive.setdefault(candidate["drive_id"], []).append(candidate)

    outcome_counts = {
        (row.drive_id, row.outcome): row.count
        for row in (
            db.query(AssessmentResult.drive_id, AssessmentResult.outcome, func.count(AssessmentResult.id).label("count"))
            .filter(AssessmentResult.drive_id.in_(drive_ids or [0]))
            .group_by(AssessmentResult.drive_id, AssessmentResult.outcome)
            .all()
        )
    }
    historical_counts = {}
    for cert_id, outcome, count in (
        db.query(CertificationDrive.certification_id, AssessmentResult.outcome, func.count(AssessmentResult.id))
        .join(AssessmentResult, AssessmentResult.drive_id == CertificationDrive.id)
        .filter(AssessmentResult.outcome.in_([AssessmentOutcome.pass_, AssessmentOutcome.fail, AssessmentOutcome.no_show]))
        .group_by(CertificationDrive.certification_id, AssessmentResult.outcome)
        .all()
    ):
        historical_counts.setdefault(cert_id, Counter())[outcome] = count

    predictions = []
    for drive in drives:
        drive_regs = regs_by_drive.get(drive.id, [])
        if not drive_regs:
            continue
        ranked = scores_by_drive.get(drive.id, [])
        avg_readiness = sum(item["score"] for item in ranked) / max(1, len(ranked))
        cert_history = historical_counts.get(drive.certification_id, Counter())
        historical_total = sum(cert_history.values())
        historical = _pct((cert_history.get(AssessmentOutcome.pass_, 0) / historical_total) * 100) if historical_total else 60
        passed = outcome_counts.get((drive.id, AssessmentOutcome.pass_), 0)
        failed = outcome_counts.get((drive.id, AssessmentOutcome.fail), 0)
        no_show = outcome_counts.get((drive.id, AssessmentOutcome.no_show), 0)
        assessed = passed + failed + no_show
        actual = _pct((passed / assessed) * 100) if assessed else None
        predicted = _pct((avg_readiness * 0.58) + (historical * 0.32) + (min(100, len(drive_regs) * 8) * 0.10))
        confidence = _pct(45 + min(25, len(drive_regs) * 4) + (20 if assessed else 0))
        predictions.append(
            {
                "drive_id": drive.id,
                "drive_name": drive.name,
                "predicted_pass_rate": predicted,
                "confidence": confidence,
                "actual_pass_rate": actual,
                "candidate_count": len(drive_regs),
                "avg_readiness_score": round(avg_readiness, 1),
                "historical_pass_rate": historical,
                "risk_level": "low" if predicted >= 75 else "medium" if predicted >= 55 else "high",
                "recommended_action": "Proceed with exam scheduling" if predicted >= 75 else "Run preparation intervention before assessment",
            }
        )
    predictions.sort(key=lambda item: item["predicted_pass_rate"])
    return {"predictions": predictions}


@router.get("/admin/fraud-duplicate-detection")
def admin_fraud_duplicate_detection(db: Session = Depends(get_db), admin: User = Depends(require_role(UserRole.admin))):  # noqa: ARG001
    flags = []
    duplicate_regs = (
        db.query(Registration.drive_id, func.lower(Registration.candidate_email), func.count(Registration.id))
        .group_by(Registration.drive_id, func.lower(Registration.candidate_email))
        .having(func.count(Registration.id) > 1)
        .all()
    )
    for drive_id, email, count in duplicate_regs:
        flags.append(
            {
                "id": f"dup-reg-{drive_id}-{email}",
                "type": "duplicate_registration",
                "severity": "high",
                "email": email,
                "drive_id": drive_id,
                "count": count,
                "reason": "Same candidate email registered multiple times for one drive",
            }
        )
    repeated_attempts = db.query(Registration).filter(Registration.prior_attempts >= 2).limit(100).all()
    for reg in repeated_attempts:
        flags.append(
            {
                "id": f"attempts-{reg.id}",
                "type": "repeated_attempts",
                "severity": "medium" if reg.prior_attempts < 4 else "high",
                "email": reg.candidate_email,
                "drive_id": reg.drive_id,
                "registration_id": reg.id,
                "count": reg.prior_attempts,
                "reason": f"{reg.prior_attempts} prior attempt(s) before this registration",
            }
        )
    voucher_rows = db.query(Voucher).all()
    voucher_pairs = Counter((voucher.user_id, voucher.certification_id, voucher.drive_id) for voucher in voucher_rows)
    for (user_id, certification_id, drive_id), count in voucher_pairs.items():
        if count > 1:
            flags.append(
                {
                    "id": f"dup-voucher-{user_id}-{certification_id}-{drive_id}",
                    "type": "duplicate_voucher_allocation",
                    "severity": "high",
                    "user_id": user_id,
                    "certification_id": certification_id,
                    "drive_id": drive_id,
                    "count": count,
                    "reason": "Multiple vouchers exist for the same user/certification/drive combination",
                }
            )
    uploads = db.query(UploadedFile).filter(UploadedFile.purpose == UploadPurpose.certificate).order_by(UploadedFile.created_at.desc()).limit(100).all()
    for upload in uploads:
        confidence = _certificate_confidence(db, upload)
        if confidence["confidence"] < 45:
            flags.append(
                {
                    "id": f"upload-{upload.id}",
                    "type": "certificate_mismatch",
                    "severity": "medium",
                    "user_id": upload.user_id,
                    "upload_id": upload.id,
                    "count": 1,
                    "reason": confidence["reason"],
                }
            )
    severity_order = {"high": 0, "medium": 1, "low": 2}
    flags.sort(key=lambda item: (severity_order.get(item["severity"], 3), item["type"]))
    return {"flags": flags[:50], "summary": f"Found {len(flags)} potential duplicate or fraud signal(s)."}


@router.post("/admin/nl-query")
def admin_natural_language_query(payload: dict, db: Session = Depends(get_db), admin: User = Depends(require_role(UserRole.admin))):  # noqa: ARG001
    query = (payload.get("query") or payload.get("message") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Missing query")
    q = query.lower()
    limit = max(1, min(int(payload.get("limit") or 25), 50))
    rows = []
    explanation = "Matched a general admin query."
    if "passed" in q and ("voucher" in q or "without" in q or "not received" in q):
        explanation = "Users who passed a drive but do not have an issued voucher for that drive."
        regs = db.query(Registration).filter(Registration.status == RegistrationStatus.passed).order_by(Registration.created_at.desc()).limit(250).all()
        for reg in regs:
            user = db.query(User).filter(User.email == reg.candidate_email).first()
            has_voucher = bool(user and db.query(Voucher).filter(Voucher.user_id == user.id, Voucher.drive_id == reg.drive_id, Voucher.status == VoucherStatus.issued).first())
            if not has_voucher:
                rows.append({"registration_id": reg.id, "drive_id": reg.drive_id, "candidate_email": reg.candidate_email, "status": _value(reg.status)})
            if len(rows) >= limit:
                break
    elif "eligible" in q and "voucher" in q:
        explanation = "Eligible or passed candidates who are ready for voucher allocation."
        rows = admin_voucher_recommendations(db=db, admin=admin)["recommendations"][:limit]
    elif "duplicate" in q or "fraud" in q or "suspicious" in q:
        explanation = "Potential fraud or duplicate signals."
        rows = admin_fraud_duplicate_detection(db=db, admin=admin)["flags"][:limit]
    elif "reconduct" in q or "re-conduct" in q:
        explanation = "Drives recommended for re-conduct."
        rows = admin_reconduct_recommendations(db=db, admin=admin)["recommendations"][:limit]
    elif "pass rate" in q or "passrate" in q:
        explanation = "Predicted pass-rate risks by drive."
        rows = admin_pass_rate_predictor(db=db, admin=admin)["predictions"][:limit]
    else:
        status = None
        for candidate_status in RegistrationStatus:
            if candidate_status.value.replace("_", " ") in q or candidate_status.value in q:
                status = candidate_status
                break
        reg_query = db.query(Registration)
        if status:
            reg_query = reg_query.filter(Registration.status == status)
            explanation = f"Registrations filtered by status {status.value}."
        elif "registration" in q or "candidate" in q:
            explanation = "Recent registrations."
        else:
            explanation = "Recent registrations fallback. Try asking for vouchers, fraud, pass rate, or re-conduct."
        rows = [
            {
                "registration_id": reg.id,
                "drive_id": reg.drive_id,
                "candidate_email": reg.candidate_email,
                "candidate_name": reg.candidate_name,
                "status": _value(reg.status),
            }
            for reg in reg_query.order_by(Registration.created_at.desc()).limit(limit).all()
        ]
    return {"query": query, "explanation": explanation, "rows": rows, "count": len(rows)}


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
