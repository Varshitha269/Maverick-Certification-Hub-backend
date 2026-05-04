from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.schemas.certification import CertificationCreate, CertificationOut, DriveCreate, DriveOut
from app.core.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.certification import Certification, CertificationDrive
from app.models.user import User, UserRole


router = APIRouter()


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
