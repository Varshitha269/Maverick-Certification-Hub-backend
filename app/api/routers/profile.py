from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.certification import Certification, CertificationDrive
from app.models.registration import Registration
from app.models.assessment import AssessmentResult

router = APIRouter()

@router.get("/badges")
def get_user_badges(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Fetch all badges the user has earned from completed certifications."""
    completed_enrollments = db.query(Enrollment).filter(
        Enrollment.user_id == user.id,
        Enrollment.status == EnrollmentStatus.completed
    ).all()
    
    badges = []
    for enr in completed_enrollments:
        c = db.query(Certification).filter(Certification.id == enr.certification_id).first()
        if c and c.badge_image_url:
            badges.append({
                "id": c.id,
                "title": c.title,
                "provider": c.provider,
                "badge_url": c.badge_image_url,
                "earned_at": enr.updated_at.isoformat() if enr.updated_at else enr.created_at.isoformat()
            })
            
    return {"badges": badges}


class ProfileUpdate(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class ThemePreference(BaseModel):
    theme: str  # 'light', 'dark', 'auto'


@router.get("/me")
def get_profile(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Get current user profile"""
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "preferences": {
            "theme": "dark",  # Default theme
            "notifications": True,
            "language": "en"
        }
    }


@router.get("/drive-history")
def get_drive_history(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    registrations = (
        db.query(Registration)
        .filter(Registration.candidate_email == user.email)
        .order_by(Registration.created_at.desc())
        .limit(100)
        .all()
    )
    rows = []
    for reg in registrations:
        drive = db.query(CertificationDrive).filter(CertificationDrive.id == reg.drive_id).first()
        cert = db.query(Certification).filter(Certification.id == drive.certification_id).first() if drive else None
        result = (
            db.query(AssessmentResult)
            .filter(AssessmentResult.registration_id == reg.id)
            .order_by(AssessmentResult.created_at.desc())
            .first()
        )
        rows.append(
            {
                "registration_id": reg.id,
                "drive_id": reg.drive_id,
                "drive_name": drive.name if drive else f"Drive #{reg.drive_id}",
                "drive_status": drive.status if drive else None,
                "certification_title": cert.title if cert else reg.exam_track,
                "provider": cert.provider if cert else None,
                "candidate_name": reg.candidate_name,
                "application_status": reg.status.value if hasattr(reg.status, "value") else str(reg.status),
                "outcome": result.outcome.value if result and hasattr(result.outcome, "value") else (str(result.outcome) if result else None),
                "score": result.score if result else None,
                "assessed_on": result.assessed_on if result else None,
                "updated_at": reg.updated_at,
            }
        )
    return {"items": rows}


@router.patch("/me")
def update_profile(
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Update user profile"""
    if payload.email and payload.email != user.email:
        # Check if email is already taken
        existing_user = db.query(User).filter(User.email == payload.email).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")
    
    if payload.full_name:
        user.full_name = payload.full_name
    
    if payload.email:
        user.email = payload.email
    
    db.commit()
    db.refresh(user)
    
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "message": "Profile updated successfully"
    }


@router.post("/change-password")
def change_password(
    payload: PasswordChange,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Change user password"""
    from app.core.security import verify_password, hash_password
    
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    user.hashed_password = hash_password(payload.new_password)
    db.commit()
    
    return {"message": "Password changed successfully"}


@router.patch("/preferences")
def update_preferences(
    payload: ThemePreference,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Update user preferences"""
    # For now, we'll just return success. In a real implementation,
    # you might want to store preferences in a separate table or JSON field
    return {
        "message": "Preferences updated successfully",
        "preferences": {
            "theme": payload.theme,
            "notifications": True,
            "language": "en"
        }
    }
