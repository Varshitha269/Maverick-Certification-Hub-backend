import datetime as dt
import json
import re
from difflib import SequenceMatcher

from fastapi import APIRouter, Depends, HTTPException
from openai import AzureOpenAI
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.api.routers.enrollments import _ensure_default_tasks
from app.api.routers.ai_insights import admin_voucher_recommendations
from app.core.config import settings
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.certification import Certification
from app.models.eligibility import EligibilityTestAttempt
from app.models.enrollment import Enrollment
from app.models.enrollment import EnrollmentStatus
from app.models.registration import Registration
from app.models.task import Task
from app.models.user import User
from app.models.user import UserRole
from app.models.upload import UploadedFile
from app.models.voucher import Voucher
from app.services.ai_service import extract_certificate_text_info, generate_task_plan
from app.services.storage_service import stream_blob


router = APIRouter()


TOKEN_STOPWORDS = {
    "and",
    "the",
    "for",
    "with",
    "certificate",
    "certification",
    "certified",
    "course",
    "exam",
    "proof",
    "completed",
    "completion",
    "professional",
    "associate",
    "foundation",
    "foundational",
    "fundamentals",
}

PROVIDER_ALIASES = {
    "aws": {"aws", "amazon", "amazonwebservices"},
    "amazon web services": {"aws", "amazon", "amazonwebservices"},
    "microsoft": {"microsoft", "azure"},
    "azure": {"microsoft", "azure"},
    "servicenow": {"servicenow", "service-now"},
    "google": {"google", "gcp", "googlecloud"},
    "google cloud": {"google", "gcp", "googlecloud"},
}


def _tokenize(value: str | None) -> set[str]:
    if not value:
        return set()
    compact = value.lower().replace("&", " and ")
    compact = re.sub(r"[_/().-]+", " ", compact)
    tokens = {
        token.strip("._-/()[]{}:,;")
        for token in re.findall(r"[a-zA-Z0-9+#]+", compact)
    }
    normalized = {token for token in tokens if token}
    return {token for token in normalized if len(token) >= 2 and token not in TOKEN_STOPWORDS}


def _provider_terms(value: str | None) -> set[str]:
    tokens = _tokenize(value)
    terms = set(tokens)
    raw = (value or "").strip().lower()
    for key, aliases in PROVIDER_ALIASES.items():
        if key in raw or tokens.intersection(aliases):
            terms.update(aliases)
    return terms


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _text_from_upload(upload: UploadedFile, *, max_bytes: int = 256_000) -> str:
    """
    Best-effort text source for verification. Real OCR/PDF parsing can be
    plugged in later; this still prevents a fixed pass score for unrelated
    uploads by validating filename and any extractable plain text bytes.
    """
    parts = [upload.original_filename or ""]
    try:
        data = bytearray()
        for chunk in stream_blob(upload.blob_path):
            data.extend(chunk)
            if len(data) >= max_bytes:
                break
        raw = bytes(data[:max_bytes])
        decoded = raw.decode("utf-8", errors="ignore")
        if len(decoded.strip()) < 20:
            decoded = raw.decode("latin-1", errors="ignore")
        cleaned = re.sub(r"[^\w\s+.#/-]", " ", decoded)
        parts.append(cleaned[:20_000])
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(part for part in parts if part)


def _verification_score(*, cert: Certification, info: dict, evidence_text: str) -> dict:
    expected_title = cert.title or ""
    expected_provider = cert.provider or ""
    extracted_title = info.get("certification_title") or ""
    extracted_provider = info.get("provider") or ""

    expected_title_tokens = _tokenize(expected_title)
    evidence_tokens = _tokenize(f"{evidence_text} {extracted_title}")
    expected_provider_terms = _provider_terms(expected_provider)
    evidence_provider_terms = _provider_terms(f"{evidence_text} {extracted_provider}")

    title_overlap = (
        len(expected_title_tokens.intersection(evidence_tokens)) / max(1, len(expected_title_tokens))
        if expected_title_tokens
        else 0.0
    )
    expected_codes = {token for token in expected_title_tokens if any(char.isdigit() for char in token)}
    code_match = bool(expected_codes.intersection(evidence_tokens))
    if code_match:
        title_overlap = max(title_overlap, 0.6)
    provider_overlap = 1.0 if expected_provider_terms.intersection(evidence_provider_terms) else 0.0
    string_similarity = SequenceMatcher(
        None,
        re.sub(r"\s+", " ", expected_title.lower()).strip(),
        re.sub(r"\s+", " ", extracted_title.lower()).strip(),
    ).ratio() if extracted_title else 0.0
    ai_confidence = max(0.0, min(1.0, _safe_float(info.get("confidence"))))

    confidence = round(
        min(
            0.99,
            (title_overlap * 0.55)
            + (provider_overlap * 0.25)
            + (string_similarity * 0.15)
            + (ai_confidence * 0.05)
            + (0.35 if code_match and title_overlap >= 0.6 else 0.0),
        ),
        2,
    )
    matched = confidence >= 0.70 and title_overlap >= 0.45

    if matched:
        reason = "The uploaded certificate appears to match the enrollment certification."
    elif not evidence_text.strip():
        reason = "The upload could not be read well enough to verify it."
    elif title_overlap < 0.25 and provider_overlap == 0:
        reason = "The upload does not mention the expected certification or provider."
    elif title_overlap < 0.45:
        reason = "The provider may match, but the certification title does not match strongly enough."
    else:
        reason = "The certificate details are close, but below the approval threshold."

    return {
        "confidence": confidence,
        "matched": matched,
        "status": "matched" if matched else "mismatch",
        "reason": reason,
        "expected_certification": expected_title,
        "expected_provider": expected_provider,
        "match_details": {
            "title_overlap": round(title_overlap, 2),
            "provider_match": bool(provider_overlap),
            "code_match": code_match,
            "title_similarity": round(string_similarity, 2),
        },
    }


def _cert_summary(cert: Certification) -> str:
    parts = [
        f"{cert.title} by {cert.provider}",
        f"level: {cert.level or 'not specified'}",
        f"category: {cert.category or 'not specified'}",
    ]
    if cert.duration:
        parts.append(f"duration: {cert.duration}")
    if cert.estimated_hours:
        parts.append(f"estimated hours: {cert.estimated_hours}")
    return ", ".join(parts)


def _enum_value(value):
    return value.value if hasattr(value, "value") else value


def _cert_payload(cert: Certification) -> dict:
    return {
        "id": cert.id,
        "title": cert.title,
        "provider": cert.provider,
        "category": cert.category,
        "level": cert.level,
        "duration": cert.duration,
        "estimated_hours": cert.estimated_hours,
        "description": cert.description,
        "prerequisites": cert.prerequisites,
        "course_url": cert.course_url,
        "official_exam_url": cert.official_exam_url,
    }


def _enrollment_payload(db: Session, enrollment: Enrollment) -> dict:
    cert = db.query(Certification).filter(Certification.id == enrollment.certification_id).first()
    return {
        "id": enrollment.id,
        "certification_id": enrollment.certification_id,
        "certification": cert.title if cert else f"Certification #{enrollment.certification_id}",
        "status": _enum_value(enrollment.status),
        "progress_percent": enrollment.progress_percent,
        "target_completion_date": enrollment.target_completion_date,
        "admin_review_requested": enrollment.admin_review_requested,
    }


def _user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": _enum_value(user.role),
        "is_active": user.is_active,
        "created_at": user.created_at,
    }


def _available_tools(user: User) -> list[dict]:
    tools = [
        {"name": "list_certifications", "role": "user", "examples": ["list azure certifications", "show available certifications"]},
        {"name": "get_certification_details", "role": "user", "examples": ["requirements for AZ-900", "details for certification 15"]},
        {"name": "enroll_self", "role": "user", "examples": ["enroll me in certification 15", "save AWS Cloud Practitioner for later"]},
        {"name": "list_my_enrollments", "role": "user", "examples": ["my enrollments", "show my progress"]},
        {"name": "list_my_vouchers", "role": "user", "examples": ["my vouchers"]},
    ]
    if user.role == UserRole.admin:
        tools.extend(
            [
                {"name": "admin_metrics", "role": "admin", "examples": ["admin metrics", "dashboard overview"]},
                {"name": "admin_list_users", "role": "admin", "examples": ["list users", "show inactive users"]},
                {"name": "admin_list_enrollments", "role": "admin", "examples": ["list all enrollments"]},
                {"name": "admin_list_registrations", "role": "admin", "examples": ["list registrations", "pending registrations"]},
                {"name": "admin_list_vouchers", "role": "admin", "examples": ["list vouchers"]},
                {"name": "admin_voucher_recommendations", "role": "admin", "examples": ["smart voucher distribution", "recommend voucher allocation"]},
            ]
        )
    return tools


def _azure_chat_client() -> AzureOpenAI:
    if not settings.AZURE_OPENAI_ENDPOINT or not settings.AZURE_OPENAI_API_KEY:
        raise RuntimeError("Azure OpenAI is not configured")
    return AzureOpenAI(
        api_key=settings.AZURE_OPENAI_API_KEY,
        api_version=settings.AZURE_OPENAI_API_VERSION,
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
    )


def _tool_schemas(user: User) -> list[dict]:
    schemas = [
        {
            "type": "function",
            "function": {
                "name": "list_available_tools",
                "description": "Show what actions the assistant can perform for the current user's role.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_certifications",
                "description": "Search or list certifications visible to users.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search text such as Azure, AWS, Python, testing, or a provider name."},
                        "category": {"type": "string", "description": "Optional exact category filter."},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 25, "default": 10},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_certification_details",
                "description": "Get prerequisites, links, and details for one certification.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "certification_id": {"type": "integer", "description": "Certification id if known."},
                        "query": {"type": "string", "description": "Certification name or search text if id is unknown."},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "enroll_self",
                "description": "Enroll the current user in a certification, or save it for later.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "certification_id": {"type": "integer", "description": "Certification id if known."},
                        "query": {"type": "string", "description": "Certification name or search text if id is unknown."},
                        "status": {
                            "type": "string",
                            "enum": ["selected", "saved_for_later"],
                            "description": "Use saved_for_later only when the user asks to save/bookmark/review later.",
                            "default": "selected",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_my_enrollments",
                "description": "List the current user's certification enrollments and progress.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_my_vouchers",
                "description": "List vouchers assigned to the current user.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
                    },
                },
            },
        },
    ]
    if user.role == UserRole.admin:
        schemas.extend(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "admin_metrics",
                        "description": "Get admin dashboard metrics and totals.",
                        "parameters": {"type": "object", "properties": {}},
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "admin_list_users",
                        "description": "List users for admin review.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "Optional email/name search."},
                                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 25},
                            },
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "admin_list_enrollments",
                        "description": "List recent enrollments across all users.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "user_id": {"type": "integer"},
                                "certification_id": {"type": "integer"},
                                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 25},
                            },
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "admin_list_registrations",
                        "description": "List BRD registrations across candidates.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "status": {"type": "string", "description": "Optional registration status."},
                                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 25},
                            },
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "admin_list_vouchers",
                        "description": "List vouchers across users.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "user_id": {"type": "integer"},
                                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 25},
                            },
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "admin_voucher_recommendations",
                        "description": "Recommend smart voucher allocation from eligible, scheduled, assessed, or passed registrations. Use this for smart voucher distribution or allocation recommendations, not admin_list_vouchers.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "drive_id": {"type": "integer", "description": "Optional drive id. Omit to scan all drives."},
                            },
                        },
                    },
                },
            ]
        )
    return schemas


def _response(tool: str, text: str, data=None) -> dict:
    return {"response": text, "tool": tool, "data": data}


def _extract_id(message: str) -> int | None:
    match = re.search(r"\b(?:id|certification|cert)\s*#?\s*(\d+)\b", message.lower())
    if match:
        return int(match.group(1))
    numbers = re.findall(r"\b\d+\b", message)
    return int(numbers[0]) if numbers else None


def _find_certification(db: Session, message: str) -> Certification | None:
    cert_id = _extract_id(message)
    if cert_id:
        cert = db.query(Certification).filter(Certification.id == cert_id).first()
        if cert:
            return cert

    ignore = {
        "show", "list", "cert", "certification", "certifications", "course", "courses", "details",
        "requirements", "requirement", "resources", "resource", "exam", "enroll", "save", "later",
        "me", "in", "for", "the", "about", "what", "are", "all", "available",
    }
    words = [word for word in re.findall(r"[a-zA-Z0-9+.#-]+", message.lower()) if len(word) >= 2 and word not in ignore]
    if not words:
        return None

    filters = []
    for word in words[:8]:
        like = f"%{word}%"
        filters.extend(
            [
                Certification.title.ilike(like),
                Certification.provider.ilike(like),
                Certification.category.ilike(like),
                Certification.tags.ilike(like),
            ]
        )
    return db.query(Certification).filter(or_(*filters)).order_by(Certification.id.asc()).first()


def _safe_limit(value, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))


def _execute_chat_tool(name: str, args: dict, db: Session, user: User) -> dict:
    if name not in {tool["function"]["name"] for tool in _tool_schemas(user)}:
        raise HTTPException(status_code=403, detail=f"Tool not allowed for this role: {name}")

    if name == "list_available_tools":
        return _response("list_available_tools", "Available tools for this role.", _available_tools(user))

    if name == "list_certifications":
        limit = _safe_limit(args.get("limit"), 10, 25)
        query = (args.get("query") or "").strip()
        category = (args.get("category") or "").strip()
        q = db.query(Certification)
        if category:
            q = q.filter(Certification.category.ilike(category))
        if query:
            filters = []
            for word in re.findall(r"[a-zA-Z0-9+.#-]+", query.lower())[:8]:
                like = f"%{word}%"
                filters.extend(
                    [
                        Certification.title.ilike(like),
                        Certification.provider.ilike(like),
                        Certification.category.ilike(like),
                        Certification.tags.ilike(like),
                    ]
                )
            if filters:
                q = q.filter(or_(*filters))
        rows = q.order_by(Certification.id.asc()).limit(limit).all()
        data = [_cert_payload(cert) for cert in rows]
        return _response("list_certifications", f"Found {len(data)} certification(s).", data)

    if name == "get_certification_details":
        cert = None
        if args.get("certification_id"):
            cert = db.query(Certification).filter(Certification.id == int(args["certification_id"])).first()
        if not cert and args.get("query"):
            cert = _find_certification(db, str(args["query"]))
        if not cert:
            return _response("get_certification_details", "Certification not found.", None)
        return _response("get_certification_details", f"Details for {cert.title}.", _cert_payload(cert))

    if name == "enroll_self":
        cert = None
        if args.get("certification_id"):
            cert = db.query(Certification).filter(Certification.id == int(args["certification_id"])).first()
        if not cert and args.get("query"):
            cert = _find_certification(db, str(args["query"]))
        if not cert:
            return _response("enroll_self", "Certification not found. Ask the user which certification they mean.", None)

        status_raw = args.get("status") or "selected"
        status = EnrollmentStatus.saved_for_later if status_raw == "saved_for_later" else EnrollmentStatus.selected
        existing = (
            db.query(Enrollment)
            .filter(Enrollment.user_id == user.id, Enrollment.certification_id == cert.id)
            .first()
        )
        if existing:
            return _response("enroll_self", "User already has an enrollment for this certification.", _enrollment_payload(db, existing))

        if status != EnrollmentStatus.saved_for_later:
            passed_attempt = (
                db.query(EligibilityTestAttempt)
                .filter(
                    EligibilityTestAttempt.user_id == user.id,
                    EligibilityTestAttempt.certification_id == cert.id,
                    EligibilityTestAttempt.passed == True,  # noqa: E712
                )
                .order_by(EligibilityTestAttempt.created_at.desc(), EligibilityTestAttempt.id.desc())
                .first()
            )
            if not passed_attempt:
                return _response(
                    "enroll_self",
                    "Eligibility test must be passed before enrollment. Offer to save for later.",
                    {"certification": _cert_payload(cert), "requires_eligibility_test": True},
                )

        enrollment = Enrollment(user_id=user.id, certification_id=cert.id, status=status)
        db.add(enrollment)
        db.commit()
        db.refresh(enrollment)
        if status != EnrollmentStatus.saved_for_later:
            _ensure_default_tasks(db, enrollment, cert)
            db.commit()
            db.refresh(enrollment)
        return _response("enroll_self", "Enrollment action completed.", _enrollment_payload(db, enrollment))

    if name == "list_my_enrollments":
        limit = _safe_limit(args.get("limit"), 20, 50)
        rows = (
            db.query(Enrollment)
            .filter(Enrollment.user_id == user.id)
            .order_by(Enrollment.created_at.desc())
            .limit(limit)
            .all()
        )
        return _response("list_my_enrollments", f"Found {len(rows)} enrollment(s).", [_enrollment_payload(db, row) for row in rows])

    if name == "list_my_vouchers":
        limit = _safe_limit(args.get("limit"), 20, 50)
        rows = db.query(Voucher).filter(Voucher.user_id == user.id).order_by(Voucher.created_at.desc()).limit(limit).all()
        data = [
            {
                "id": row.id,
                "certification_id": row.certification_id,
                "status": _enum_value(row.status),
                "code": row.masked_code or row.code,
                "expires_at": row.expires_at,
            }
            for row in rows
        ]
        return _response("list_my_vouchers", f"Found {len(data)} voucher(s).", data)

    if name == "admin_metrics":
        data = {
            "users": db.query(func.count(User.id)).scalar() or 0,
            "active_users": db.query(func.count(User.id)).filter(User.is_active == True).scalar() or 0,  # noqa: E712
            "certifications": db.query(func.count(Certification.id)).scalar() or 0,
            "enrollments": db.query(func.count(Enrollment.id)).scalar() or 0,
            "registrations": db.query(func.count(Registration.id)).scalar() or 0,
            "vouchers": db.query(func.count(Voucher.id)).scalar() or 0,
            "tasks": db.query(func.count(Task.id)).scalar() or 0,
        }
        return _response("admin_metrics", "Admin metrics loaded.", data)

    if name == "admin_list_users":
        limit = _safe_limit(args.get("limit"), 25, 50)
        query = (args.get("query") or "").strip()
        q = db.query(User)
        if query:
            like = f"%{query}%"
            q = q.filter(or_(User.email.ilike(like), User.full_name.ilike(like)))
        rows = q.order_by(User.created_at.desc()).limit(limit).all()
        return _response("admin_list_users", f"Found {len(rows)} user(s).", [_user_payload(row) for row in rows])

    if name == "admin_list_enrollments":
        limit = _safe_limit(args.get("limit"), 25, 50)
        q = db.query(Enrollment)
        if args.get("user_id") is not None:
            q = q.filter(Enrollment.user_id == int(args["user_id"]))
        if args.get("certification_id") is not None:
            q = q.filter(Enrollment.certification_id == int(args["certification_id"]))
        rows = q.order_by(Enrollment.created_at.desc()).limit(limit).all()
        return _response("admin_list_enrollments", f"Found {len(rows)} enrollment(s).", [_enrollment_payload(db, row) for row in rows])

    if name == "admin_list_registrations":
        limit = _safe_limit(args.get("limit"), 25, 50)
        q = db.query(Registration)
        if args.get("status"):
            q = q.filter(Registration.status == str(args["status"]))
        rows = q.order_by(Registration.created_at.desc()).limit(limit).all()
        data = [
            {
                "id": row.id,
                "candidate_email": row.candidate_email,
                "candidate_name": row.candidate_name,
                "drive_id": row.drive_id,
                "status": _enum_value(row.status),
                "slot": row.slot,
            }
            for row in rows
        ]
        return _response("admin_list_registrations", f"Found {len(data)} registration(s).", data)

    if name == "admin_list_vouchers":
        limit = _safe_limit(args.get("limit"), 25, 50)
        q = db.query(Voucher)
        if args.get("user_id") is not None:
            q = q.filter(Voucher.user_id == int(args["user_id"]))
        rows = q.order_by(Voucher.created_at.desc()).limit(limit).all()
        data = [
            {
                "id": row.id,
                "user_id": row.user_id,
                "certification_id": row.certification_id,
                "status": _enum_value(row.status),
                "code": row.masked_code or row.code,
            }
            for row in rows
        ]
        return _response("admin_list_vouchers", f"Found {len(data)} voucher(s).", data)

    if name == "admin_voucher_recommendations":
        drive_id = int(args["drive_id"]) if args.get("drive_id") is not None else None
        result = admin_voucher_recommendations(drive_id=drive_id, db=db, admin=user)
        return _response("admin_voucher_recommendations", result.get("message") or "Voucher recommendations loaded.", result)

    raise HTTPException(status_code=400, detail=f"Unknown tool: {name}")


@router.post("/chat")
def ai_chat(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Role-aware AI tool caller for the in-app assistant.
    Azure OpenAI chooses from backend-approved tools; the backend executes
    only tools allowed for the authenticated user's role.
    Body: { "message": "...", "history": [{ "role": "...", "content": "..." }] }
    """
    if not settings.AI_ENABLED:
        raise HTTPException(status_code=503, detail="AI is disabled. Set AI_ENABLED=true.")
    if (settings.AI_PROVIDER or "").strip().lower() != "azure_openai":
        raise HTTPException(status_code=503, detail="Real chat tool-calling requires AI_PROVIDER=azure_openai.")

    message = (payload.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Missing 'message'")

    history = payload.get("history") or []
    messages = [
        {
            "role": "system",
            "content": (
                "You are the Maverick Certification Hub assistant. "
                "Use tools whenever the user asks for application data or actions. "
                "Do not invent IDs, users, enrollments, vouchers, registrations, or certification data. "
                "The backend exposes only tools allowed for this authenticated user's role. "
                f"Current user: {user.email}; role: {user.role.value}."
            ),
        }
    ]
    for item in history[-8:]:
        role = item.get("role")
        content = (item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    client = _azure_chat_client()
    schemas = _tool_schemas(user)
    try:
        first = client.chat.completions.create(
            model=settings.AZURE_OPENAI_DEPLOYMENT,
            messages=messages,
            tools=schemas,
            tool_choice="auto",
            max_completion_tokens=1200,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(e)) from e

    assistant = first.choices[0].message
    tool_calls = assistant.tool_calls or []
    if not tool_calls:
        return _response("none", assistant.content or "I could not decide which tool to use.", None)

    assistant_message = {
        "role": "assistant",
        "content": assistant.content,
        "tool_calls": [
            {
                "id": call.id,
                "type": call.type,
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                },
            }
            for call in tool_calls
        ],
    }
    followup_messages = [*messages, assistant_message]
    executed = []
    for call in tool_calls:
        try:
            args = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        result = _execute_chat_tool(call.function.name, args, db, user)
        executed.append({"name": call.function.name, "arguments": args, "result": result})
        followup_messages.append(
            {
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result, default=str),
            }
        )

    try:
        final = client.chat.completions.create(
            model=settings.AZURE_OPENAI_DEPLOYMENT,
            messages=[
                *followup_messages,
                {
                    "role": "system",
                    "content": (
                        "Summarize the tool result for the user. Be concise. "
                        "If the tool performed an action, state the outcome clearly. "
                        "If data is empty, say so and suggest the next useful action."
                    ),
                },
            ],
            max_completion_tokens=1200,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(e)) from e

    return {
        "response": final.choices[0].message.content or executed[-1]["result"]["response"],
        "tool": executed[-1]["name"] if executed else None,
        "tool_calls": executed,
        "data": executed[-1]["result"].get("data") if executed else None,
    }


@router.post("/certificate/extract")
def ai_extract_certificate(payload: dict, user: User = Depends(get_current_user)):
    if not settings.AI_ENABLED:
        raise HTTPException(status_code=503, detail="AI is disabled. Set AI_ENABLED=true and configure Azure OpenAI.")
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Missing 'text'")
    try:
        info = extract_certificate_text_info(text)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(e)) from e
    return info.__dict__


@router.post("/tasks/generate")
def ai_generate_tasks(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Generate tasks for a certification enrollment.
    Body: { "enrollment_id": 123, "weeks": 6, "hours_per_week": 6 }
    """
    if not settings.AI_ENABLED:
        raise HTTPException(status_code=503, detail="AI is disabled. Set AI_ENABLED=true and configure Azure OpenAI.")

    enrollment_id = payload.get("enrollment_id")
    if not enrollment_id:
        raise HTTPException(status_code=400, detail="Missing 'enrollment_id'")

    enrollment = db.query(Enrollment).filter(Enrollment.id == int(enrollment_id), Enrollment.user_id == user.id).first()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    cert = db.query(Certification).filter(Certification.id == enrollment.certification_id).first()
    if not cert:
        raise HTTPException(status_code=404, detail="Certification not found")

    weeks = int(payload.get("weeks") or 6)
    hours_per_week = int(payload.get("hours_per_week") or 6)

    try:
        plan = generate_task_plan(certification_title=cert.title, weeks=weeks, hours_per_week=hours_per_week)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(e)) from e
    created = 0
    now = dt.datetime.now(dt.timezone.utc)
    for t in plan:
        title = (t.get("title") or "").strip()
        if not title:
            continue
        due_offset = int(t.get("due_offset_days") or 7)
        due = (now + dt.timedelta(days=max(1, due_offset))).isoformat()
        task = Task(
            user_id=user.id,
            enrollment_id=enrollment.id,
            title=title[:240],
            description=(t.get("description") or None),
            due_date=due,
            priority=int(t.get("priority") or 3),
        )
        db.add(task)
        created += 1
    db.commit()
    return {"created": created}


@router.post("/certificate/verify_upload")
def ai_verify_certificate_upload(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Verify an uploaded certificate.
    Body: { "upload_id": 123 }
    """
    upload_id = payload.get("upload_id")
    if not upload_id:
        raise HTTPException(status_code=400, detail="Missing 'upload_id'")

    upload = db.query(UploadedFile).filter(UploadedFile.id == int(upload_id), UploadedFile.user_id == user.id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    if not upload.enrollment_id:
        raise HTTPException(status_code=400, detail="Link the certificate upload to an enrollment before verification")

    enrollment = (
        db.query(Enrollment)
        .filter(Enrollment.id == upload.enrollment_id, Enrollment.user_id == user.id)
        .first()
    )
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found for this upload")

    cert = db.query(Certification).filter(Certification.id == enrollment.certification_id).first()
    if not cert:
        raise HTTPException(status_code=404, detail="Certification not found for this enrollment")

    evidence_text = _text_from_upload(upload)
    info = {
        "candidate_name": user.full_name or user.email,
        "certification_title": None,
        "provider": None,
        "issued_on": None,
        "credential_id": None,
        "confidence": 0.0,
    }

    if settings.AI_ENABLED:
        try:
            extracted = extract_certificate_text_info(evidence_text)
            info.update(extracted.__dict__)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=503, detail=str(e)) from e
    else:
        info["certification_title"] = upload.original_filename

    verification = _verification_score(cert=cert, info=info, evidence_text=evidence_text)
    return {**info, **verification}

