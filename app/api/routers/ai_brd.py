from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.certification import CertificationDrive
from app.models.registration import Registration
from app.models.user import User, UserRole
from app.services.ai_service import extract_skills_from_text, generate_drive_exec_summary


router = APIRouter()


@router.post("/skills/extract")
def ai_extract_skills(payload: dict, user: User = Depends(get_current_user)):
    if not settings.AI_ENABLED:
        raise HTTPException(status_code=503, detail="AI is disabled. Set AI_ENABLED=true and configure Azure OpenAI.")
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Missing 'text'")
    return extract_skills_from_text(text=text)


@router.get("/admin/drive-summary/{drive_id}")
def ai_drive_summary(
    drive_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    if not settings.AI_ENABLED:
        raise HTTPException(status_code=503, detail="AI is disabled. Set AI_ENABLED=true and configure Azure OpenAI.")
    drive = db.query(CertificationDrive).filter(CertificationDrive.id == drive_id).first()
    if not drive:
        raise HTTPException(status_code=404, detail="Drive not found")
    regs = db.query(Registration).filter(Registration.drive_id == drive_id).all()
    status_counts: dict[str, int] = {}
    for r in regs:
        key = r.status.value if r.status else "unknown"
        status_counts[key] = status_counts.get(key, 0) + 1
    stats = {
        "drive_id": drive_id,
        "drive_name": drive.name,
        "registration_count": len(regs),
        "status_counts": status_counts,
        "voucher_budget": drive.voucher_budget,
        "target_count": drive.target_count,
    }
    return generate_drive_exec_summary(drive_name=drive.name, stats=stats)

