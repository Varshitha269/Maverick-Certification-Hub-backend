from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app.api.schemas.user import UserOut, UserUpdate
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User


router = APIRouter()


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=UserOut)
def update_me(payload: UserUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.full_name is not None:
        user.full_name = payload.full_name
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/me/avatar", response_model=UserOut)
async def upload_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    import os
    import uuid
    from pathlib import Path
    
    # Create uploads directory if it doesn't exist
    upload_dir = Path("uploads/avatars")
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename
    file_extension = Path(file.filename).suffix
    unique_filename = f"{user.id}_{uuid.uuid4()}{file_extension}"
    file_path = upload_dir / unique_filename
    
    # Save file
    try:
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    
    # Store relative URL in database
    user.avatar_url = f"/uploads/avatars/{unique_filename}"
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/me")
def deactivate_me(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    user.is_active = False
    db.add(user)
    db.commit()
    return {"ok": True}

