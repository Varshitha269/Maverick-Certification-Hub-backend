from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User

router = APIRouter()


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
