from fastapi import APIRouter, Depends, HTTPException
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


@router.delete("/me")
def deactivate_me(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    user.is_active = False
    db.add(user)
    db.commit()
    return {"ok": True}

