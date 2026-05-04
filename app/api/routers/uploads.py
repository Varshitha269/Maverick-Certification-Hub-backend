from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.upload import UploadedFile, UploadPurpose
from app.models.user import User, UserRole
from app.models.enrollment import Enrollment
from app.models.certification import Certification
from app.services.storage_service import upload_bytes


router = APIRouter()


@router.get("/me")
def my_uploads(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Get user's uploaded files with certification details"""
    rows = db.query(UploadedFile).filter(UploadedFile.user_id == user.id).order_by(UploadedFile.created_at.desc()).all()
    
    uploads = []
    for r in rows:
        upload_data = {
            "id": r.id,
            "purpose": r.purpose,
            "original_filename": r.original_filename,
            "content_type": r.content_type,
            "blob_path": r.blob_path,
            "size_bytes": r.size_bytes,
            "sha256": r.sha256,
            "created_at": r.created_at,
            "download_url": f"/api/v1/uploads/{r.id}/download",
        }
        
        # Add certification information if linked to enrollment
        if r.enrollment_id:
            enrollment = db.query(Enrollment).filter(Enrollment.id == r.enrollment_id).first()
            if enrollment:
                certification = db.query(Certification).filter(Certification.id == enrollment.certification_id).first()
                if certification:
                    upload_data.update({
                        "certification": {
                            "id": certification.id,
                            "title": certification.title,
                            "provider": certification.provider
                        },
                        "enrollment_status": enrollment.status,
                        "enrollment_date": enrollment.created_at
                    })
        
        uploads.append(upload_data)
    
    return uploads


@router.get("/certificates")
def get_user_certificates(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Get user's completed certificates"""
    # Get completed enrollments with certificate uploads
    completed_enrollments = (
        db.query(Enrollment)
        .filter(
            Enrollment.user_id == user.id,
            Enrollment.status == "completed"
        )
        .all()
    )
    
    certificates = []
    for enrollment in completed_enrollments:
        # Get certification details
        certification = db.query(Certification).filter(Certification.id == enrollment.certification_id).first()
        
        # Get certificate uploads for this enrollment
        cert_uploads = (
            db.query(UploadedFile)
            .filter(
                UploadedFile.user_id == user.id,
                UploadedFile.enrollment_id == enrollment.id,
                UploadedFile.purpose == UploadPurpose.certificate
            )
            .all()
        )
        
        certificates.append({
            "id": enrollment.id,
            "certification": {
                "id": certification.id,
                "title": certification.title,
                "provider": certification.provider,
                "description": certification.description
            } if certification else None,
            "completed_date": enrollment.updated_at,
            "certificate_files": [
                {
                    "id": upload.id,
                    "filename": upload.original_filename,
                    "download_url": f"/api/v1/uploads/{upload.id}/download",
                    "upload_date": upload.created_at
                }
                for upload in cert_uploads
            ],
            "has_certificate": len(cert_uploads) > 0
        })
    
    return certificates


@router.post("/me")
async def upload_my_file(
    file: UploadFile = File(...),
    purpose: UploadPurpose = Form(UploadPurpose.other),
    enrollment_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    obj = upload_bytes(data=data, content_type=file.content_type, filename=file.filename or "upload.bin", user_id=user.id, purpose=purpose.value)
    row = UploadedFile(
        user_id=user.id,
        enrollment_id=enrollment_id,
        purpose=purpose,
        original_filename=file.filename or "upload.bin",
        content_type=file.content_type,
        blob_path=obj.blob_path,
        size_bytes=obj.size_bytes,
        sha256=obj.sha256,
        storage_provider="azure_blob",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "blob_path": row.blob_path, "size_bytes": row.size_bytes, "sha256": row.sha256}


from fastapi.responses import StreamingResponse

@router.get("/{upload_id}/download")
def download_file(upload_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    upload = db.query(UploadedFile).filter(UploadedFile.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    if user.role != UserRole.admin and upload.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    from app.services.storage_service import stream_blob
    try:
        chunks = stream_blob(upload.blob_path)
        return StreamingResponse(
            chunks, 
            media_type=upload.content_type or "application/octet-stream",
            headers={"Content-Disposition": f'inline; filename="{upload.original_filename}"'}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to stream file from storage")


@router.get("/", dependencies=[Depends(require_role(UserRole.admin))])
def admin_uploads(db: Session = Depends(get_db), admin: User = Depends(require_role(UserRole.admin))):  # noqa: ARG001
    rows = db.query(UploadedFile).order_by(UploadedFile.created_at.desc()).limit(500).all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "enrollment_id": r.enrollment_id,
            "purpose": r.purpose,
            "original_filename": r.original_filename,
            "blob_path": r.blob_path,
            "size_bytes": r.size_bytes,
            "created_at": r.created_at,
        }
        for r in rows
    ]

