from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenPair
from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User, UserRole
from app.services.audit_service import log_audit
from fastapi.security import OAuth2PasswordRequestForm


router = APIRouter()


@router.post("/register", response_model=TokenPair)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    existing = db.query(User).filter(func.lower(User.email) == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=UserRole.user,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenPair(
        access_token=create_access_token(user.email, {"role": user.role.value}),
        refresh_token=create_refresh_token(user.email),
    )


@router.post("/login")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    email = form_data.username.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == email).first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account is inactive")

    log_audit(
        db,
        actor=user,
        action="auth.login",
        entity="user",
        entity_id=user.id,
        request=request,
        details={"email": user.email, "role": user.role.value},
    )

    return {
        "access_token": create_access_token(user.email, {"role": user.role.value}),
        "token_type": "bearer"
    }


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):  # noqa: ARG001
    try:
        decoded = jwt.decode(payload.refresh_token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        if decoded.get("type") != "refresh" or not decoded.get("sub"):
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        subject = decoded["sub"]
    except JWTError as e:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from e

    user = db.query(User).filter(User.email == subject).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    return TokenPair(
        access_token=create_access_token(user.email, {"role": user.role.value}),
        refresh_token=create_refresh_token(user.email),
    )

