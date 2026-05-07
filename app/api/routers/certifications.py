import json
import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.schemas.certification import CertificationCreate, CertificationOut, DriveCreate, DriveOut
from app.core.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.certification import Certification, CertificationDrive
from app.models.eligibility import EligibilityTestAttempt
from app.models.user import User, UserRole
from app.services.audit_service import log_audit


router = APIRouter()


def _build_eligibility_test(cert: Certification) -> dict:
    title = cert.title or "this certification"
    text = f"{cert.title or ''} {cert.provider or ''} {cert.category or ''} {cert.tags or ''}".lower()

    if "azure" in text:
        questions = [
            {
                "id": "q1",
                "question": "Azure is mainly related to which topic?",
                "options": [
                    "Microsoft cloud services",
                    "Cooking recipes",
                    "Movie editing only",
                    "Sports training",
                ],
                "answer": "Microsoft cloud services",
            },
            {
                "id": "q2",
                "question": "What should you learn first for Azure Fundamentals?",
                "options": ["Basic cloud and Azure concepts", "Advanced hacking", "Game design only", "Hardware repair"],
                "answer": "Basic cloud and Azure concepts",
            },
            {
                "id": "q3",
                "question": f"Why would you enroll in {title}?",
                "options": ["To learn the basics step by step", "To skip learning", "To avoid practice", "To delete my profile"],
                "answer": "To learn the basics step by step",
            },
        ]
    elif "aws" in text or "amazon web services" in text:
        questions = [
            {
                "id": "q1",
                "question": "AWS is mainly related to which topic?",
                "options": ["Amazon cloud services", "Cooking recipes", "Drawing cartoons only", "Sports training"],
                "answer": "Amazon cloud services",
            },
            {
                "id": "q2",
                "question": "What should a beginner learn first for AWS?",
                "options": ["Basic cloud concepts", "Advanced networking only", "Car repair", "Movie editing"],
                "answer": "Basic cloud concepts",
            },
            {
                "id": "q3",
                "question": f"Why would you enroll in {title}?",
                "options": ["To learn the basics step by step", "To skip learning", "To avoid practice", "To delete my profile"],
                "answer": "To learn the basics step by step",
            },
        ]
    elif "devops" in text or "kubernetes" in text or "docker" in text:
        questions = [
            {
                "id": "q1",
                "question": "DevOps is mainly about connecting which two areas?",
                "options": ["Development and operations", "Cooking and painting", "Movies and music", "Sports and travel"],
                "answer": "Development and operations",
            },
            {
                "id": "q2",
                "question": "What should a beginner focus on first in DevOps?",
                "options": ["Basic tools and workflow concepts", "Skipping all practice", "Only changing colors", "Deleting repositories"],
                "answer": "Basic tools and workflow concepts",
            },
            {
                "id": "q3",
                "question": f"Why would you enroll in {title}?",
                "options": ["To learn the basics step by step", "To skip learning", "To avoid practice", "To delete my profile"],
                "answer": "To learn the basics step by step",
            },
        ]
    elif "python" in text or "programming" in text or "developer" in text or "development" in text:
        questions = [
            {
                "id": "q1",
                "question": "Programming is mainly about what?",
                "options": ["Giving instructions to a computer", "Cooking food", "Driving a car", "Painting a wall"],
                "answer": "Giving instructions to a computer",
            },
            {
                "id": "q2",
                "question": "What should a beginner learn first in programming?",
                "options": ["Basic syntax and simple logic", "Advanced architecture only", "No practice", "Only exam rules"],
                "answer": "Basic syntax and simple logic",
            },
            {
                "id": "q3",
                "question": f"Why would you enroll in {title}?",
                "options": ["To learn the basics step by step", "To skip learning", "To avoid practice", "To delete my profile"],
                "answer": "To learn the basics step by step",
            },
        ]
    elif "servicenow" in text:
        questions = [
            {
                "id": "q1",
                "question": "ServiceNow is mainly used for what?",
                "options": ["Managing service workflows", "Cooking recipes", "Video games only", "Weather reports"],
                "answer": "Managing service workflows",
            },
            {
                "id": "q2",
                "question": "What should a beginner learn first in ServiceNow?",
                "options": ["Basic platform and workflow concepts", "Advanced scripting only", "Skipping practice", "Graphic design only"],
                "answer": "Basic platform and workflow concepts",
            },
            {
                "id": "q3",
                "question": f"Why would you enroll in {title}?",
                "options": ["To learn the basics step by step", "To skip learning", "To avoid practice", "To delete my profile"],
                "answer": "To learn the basics step by step",
            },
        ]
    elif "cloud" in text:
        questions = [
            {
                "id": "q1",
                "question": "Cloud computing is mainly about using services through what?",
                "options": ["The internet", "Only paper forms", "Only DVDs", "Only handwritten notes"],
                "answer": "The internet",
            },
            {
                "id": "q2",
                "question": "What should a beginner learn first in cloud?",
                "options": ["Basic cloud concepts", "Advanced billing formulas only", "No practice", "Only exam booking"],
                "answer": "Basic cloud concepts",
            },
            {
                "id": "q3",
                "question": f"Why would you enroll in {title}?",
                "options": ["To learn the basics step by step", "To skip learning", "To avoid practice", "To delete my profile"],
                "answer": "To learn the basics step by step",
            },
        ]
    else:
        questions = [
            {
                "id": "q1",
                "question": f"What is the main goal of enrolling in {title}?",
                "options": [
                    "To learn the basics step by step",
                    "To skip learning",
                    "To avoid practice",
                    "To delete my profile",
                ],
                "answer": "To learn the basics step by step",
            },
            {
                "id": "q2",
                "question": "What should you do if a topic is new to you?",
                "options": ["Start with beginner lessons", "Give up immediately", "Skip the course", "Choose random answers only"],
                "answer": "Start with beginner lessons",
            },
            {
                "id": "q3",
                "question": "What is the best attitude before starting a certification course?",
                "options": ["Be ready to learn and practice", "Avoid learning", "Ignore all tasks", "Never ask questions"],
                "answer": "Be ready to learn and practice",
            },
        ]

    return {
        "certification_id": cert.id,
        "title": f"{cert.title} eligibility test",
        "passing_score": 60,
        "questions": questions,
    }


def _latest_attempt(db: Session, user_id: int, certification_id: int) -> EligibilityTestAttempt | None:
    return (
        db.query(EligibilityTestAttempt)
        .filter(
            EligibilityTestAttempt.user_id == user_id,
            EligibilityTestAttempt.certification_id == certification_id,
        )
        .order_by(EligibilityTestAttempt.created_at.desc(), EligibilityTestAttempt.id.desc())
        .first()
    )


@router.get("/", response_model=list[CertificationOut])
def list_certifications(
    search: str | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),  # noqa: ARG001
):
    q = db.query(Certification)
    if search:
        term = f"%{search}%"
        q = q.filter(
            or_(
                Certification.title.ilike(term),
                Certification.provider.ilike(term),
                Certification.tags.ilike(term),
                Certification.category.ilike(term),
                Certification.description.ilike(term),
            )
        )
    if category and category.lower() != "all":
        q = q.filter(Certification.category.ilike(f"%{category}%"))
    return q.order_by(Certification.category.asc(), Certification.title.asc()).all()


@router.get("/export/csv")
def export_certifications_csv(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    certs = db.query(Certification).order_by(Certification.category.asc(), Certification.title.asc()).all()
    drives = db.query(CertificationDrive).all()
    drives_by_cert: dict[int, list[CertificationDrive]] = {}
    for drive in drives:
        drives_by_cert.setdefault(drive.certification_id, []).append(drive)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "certification_id",
        "title",
        "provider",
        "category",
        "level",
        "duration",
        "estimated_hours",
        "exam_cost",
        "tags",
        "course_url",
        "official_exam_url",
        "badge_image_url",
        "drive_ids",
        "drive_names",
        "drive_statuses",
        "voucher_budgets",
        "repository_prefixes",
        "prerequisites",
        "description",
    ])
    for cert in certs:
        cert_drives = drives_by_cert.get(cert.id, [])
        w.writerow([
            cert.id,
            cert.title,
            cert.provider,
            cert.category or "",
            cert.level or "",
            cert.duration or "",
            cert.estimated_hours if cert.estimated_hours is not None else "",
            cert.exam_cost if cert.exam_cost is not None else "",
            cert.tags or "",
            cert.course_url or "",
            cert.official_exam_url or "",
            cert.badge_image_url or "",
            ";".join(str(d.id) for d in cert_drives),
            ";".join(d.name for d in cert_drives),
            ";".join(d.status for d in cert_drives),
            ";".join("" if d.voucher_budget is None else str(d.voucher_budget) for d in cert_drives),
            ";".join(d.repository_prefix or "" for d in cert_drives),
            (cert.prerequisites or "").replace("\r\n", "\n"),
            cert.description or "",
        ])

    log_audit(
        db,
        actor=admin,
        action="certification.export_csv",
        entity="certification",
        entity_id="all",
        request=request,
        details={"rows": len(certs)},
    )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue().encode("utf-8")]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="certifications-with-drives.csv"'},
    )


@router.post("/", response_model=CertificationOut)
def create_certification(
    payload: CertificationCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    cert = Certification(**payload.model_dump())
    db.add(cert)
    db.commit()
    db.refresh(cert)
    return cert


@router.get("/{cert_id}", response_model=CertificationOut)
def get_certification(cert_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):  # noqa: ARG001
    cert = db.query(Certification).filter(Certification.id == cert_id).first()
    if not cert:
        raise HTTPException(status_code=404, detail="Certification not found")
    return cert


@router.get("/{cert_id}/eligibility")
def check_eligibility(cert_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cert = db.query(Certification).filter(Certification.id == cert_id).first()
    if not cert:
        raise HTTPException(status_code=404, detail="Certification not found")

    prereqs = [p.strip() for p in (cert.prerequisites or "").splitlines() if p.strip()]
    matched_skills = []
    user_text = f"{user.full_name or ''} {user.email}".lower()
    for prereq in prereqs:
        words = [w.strip(".,;:()[]").lower() for w in prereq.split() if len(w.strip(".,;:()[]")) > 3]
        if any(word in user_text for word in words):
            matched_skills.append(prereq)

    eligible = len(prereqs) == 0 or len(matched_skills) > 0 or (cert.level or "").lower() in {"entry", "foundation", "foundational"}
    missing = [p for p in prereqs if p not in matched_skills]
    explanation = (
        "AI eligibility check: you can enroll now. The program is either open-entry or your profile matches at least one listed prerequisite."
        if eligible
        else "AI eligibility check: enrollment may need admin review because the listed prerequisites are not visible in your profile yet."
    )
    if missing:
        explanation += " Upload supporting documents or request manager approval for: " + "; ".join(missing[:3])

    attempt = _latest_attempt(db, user.id, cert.id)
    return {
        "certification_id": cert.id,
        "eligible": eligible,
        "status": "eligible" if eligible else "review_required",
        "explanation": explanation,
        "matched": matched_skills,
        "missing": missing,
        "test_attempt": (
            {
                "id": attempt.id,
                "score": attempt.score,
                "passed": attempt.passed,
                "status": attempt.status,
                "message": attempt.message,
                "created_at": attempt.created_at,
            }
            if attempt
            else None
        ),
        "recommended_tools": [
            {"name": "Azure OpenAI", "purpose": "Explain eligibility and generate task plans"},
            {"name": "Power Apps", "purpose": "Mobile-friendly approval and document intake"},
            {"name": "Power BI", "purpose": "Certification success, voucher usage, and completion analytics"},
        ],
    }


@router.get("/{cert_id}/eligibility-test")
def eligibility_test(cert_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):  # noqa: ARG001
    cert = db.query(Certification).filter(Certification.id == cert_id).first()
    if not cert:
        raise HTTPException(status_code=404, detail="Certification not found")
    test = _build_eligibility_test(cert)
    attempt = _latest_attempt(db, user.id, cert.id)
    if attempt:
        test["latest_attempt"] = {
            "id": attempt.id,
            "score": attempt.score,
            "passed": attempt.passed,
            "status": attempt.status,
            "message": attempt.message,
            "created_at": attempt.created_at,
        }
    return test


@router.post("/{cert_id}/eligibility-test/submit")
def submit_eligibility_test(
    cert_id: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cert = db.query(Certification).filter(Certification.id == cert_id).first()
    if not cert:
        raise HTTPException(status_code=404, detail="Certification not found")
    test = _build_eligibility_test(cert)
    answers = payload.get("answers") or {}
    correct = 0
    for question in test["questions"]:
        if answers.get(question["id"]) == question["answer"]:
            correct += 1
    score = round((correct / len(test["questions"])) * 100)
    passed = score >= test["passing_score"]
    message = "Eligibility test passed. You can enroll." if passed else "Eligibility test did not pass. Admin review is recommended."
    attempt = EligibilityTestAttempt(
        user_id=user.id,
        certification_id=cert_id,
        score=score,
        passed=passed,
        status="eligible" if passed else "review_required",
        answers_json=json.dumps(answers),
        message=message,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    log_audit(
        db,
        actor=user,
        action="eligibility_test.submit",
        entity="certification",
        entity_id=cert_id,
        request=request,
        details={"score": score, "passed": passed, "attempt_id": attempt.id},
    )
    return {
        "attempt_id": attempt.id,
        "certification_id": cert_id,
        "score": score,
        "passed": passed,
        "status": attempt.status,
        "message": message,
    }


@router.patch("/{cert_id}", response_model=CertificationOut)
def update_certification(
    cert_id: int,
    payload: CertificationCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    cert = db.query(Certification).filter(Certification.id == cert_id).first()
    if not cert:
        raise HTTPException(status_code=404, detail="Certification not found")
    for k, v in payload.model_dump().items():
        setattr(cert, k, v)
    db.add(cert)
    db.commit()
    db.refresh(cert)
    return cert


@router.delete("/{cert_id}")
def delete_certification(
    cert_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    cert = db.query(Certification).filter(Certification.id == cert_id).first()
    if not cert:
        raise HTTPException(status_code=404, detail="Certification not found")
    db.delete(cert)
    db.commit()
    return {"ok": True}


@router.get("/{cert_id}/drives", response_model=list[DriveOut])
def list_drives(cert_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):  # noqa: ARG001
    return db.query(CertificationDrive).filter(CertificationDrive.certification_id == cert_id).all()


@router.post("/drives", response_model=DriveOut)
def create_drive(
    payload: DriveCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    cert = db.query(Certification).filter(Certification.id == payload.certification_id).first()
    if not cert:
        raise HTTPException(status_code=404, detail="Certification not found")
    drive = CertificationDrive(**payload.model_dump())
    db.add(drive)
    db.commit()
    db.refresh(drive)
    return drive
