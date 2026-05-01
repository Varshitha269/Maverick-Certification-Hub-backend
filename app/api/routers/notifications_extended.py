from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import datetime, timedelta
from typing import List

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.certification import Certification
from app.models.notification import Notification

router = APIRouter()


@router.get("/")
def get_notifications(
    limit: int = 10,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get user notifications"""
    # Get recent certifications uploaded
    recent_certs = (
        db.query(Certification)
        .filter(Certification.created_at >= datetime.now() - timedelta(days=7))
        .order_by(desc(Certification.created_at))
        .limit(5)
        .all()
    )
    
    # Get user's enrollment updates
    user_enrollments = (
        db.query(Enrollment)
        .filter(Enrollment.user_id == user.id)
        .order_by(desc(Enrollment.updated_at))
        .limit(5)
        .all()
    )
    
    notifications = []
    
    # Add certification notifications
    for cert in recent_certs:
        notifications.append({
            "id": f"cert_{cert.id}",
            "title": "New Certification Available",
            "message": f"{cert.title} by {cert.provider} is now available",
            "type": "info",
            "timestamp": cert.created_at,
            "action_url": f"/dashboard/certifications/{cert.id}"
        })
    
    # Add enrollment notifications
    for enrollment in user_enrollments:
        if enrollment.status == EnrollmentStatus.completed:
            notifications.append({
                "id": f"enroll_{enrollment.id}",
                "title": "Certification Completed",
                "message": f"Congratulations! You completed {enrollment.certification.title}",
                "type": "success",
                "timestamp": enrollment.updated_at,
                "action_url": f"/dashboard/certifications/{enrollment.certification_id}"
            })
        elif enrollment.status == EnrollmentStatus.in_progress:
            notifications.append({
                "id": f"enroll_{enrollment.id}",
                "title": "In Progress",
                "message": f"Continue learning {enrollment.certification.title}",
                "type": "warning",
                "timestamp": enrollment.updated_at,
                "action_url": f"/dashboard/enrollments/{enrollment.id}"
            })
    
    # Sort by timestamp and limit
    notifications.sort(key=lambda x: x["timestamp"], reverse=True)
    
    return {
        "notifications": notifications[:limit],
        "unread_count": len([n for n in notifications[:limit] if n["type"] == "info"])
    }


@router.get("/certifications/recent")
def get_recent_certifications(
    limit: int = 10,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get recently uploaded certifications that might interest the user"""
    recent_certs = (
        db.query(Certification)
        .filter(Certification.created_at >= datetime.now() - timedelta(days=30))
        .order_by(desc(Certification.created_at))
        .limit(limit)
        .all()
    )
    
    # Get user's current enrollments to avoid duplicates
    user_enrolled_cert_ids = (
        db.query(Enrollment.certification_id)
        .filter(Enrollment.user_id == user.id)
        .subquery()
    )
    
    # Filter out certifications user is already enrolled in
    available_certs = [
        cert for cert in recent_certs 
        if cert.id not in [row[0] for row in user_enrolled_cert_ids.all()]
    ]
    
    return {
        "certifications": [
            {
                "id": cert.id,
                "title": cert.title,
                "provider": cert.provider,
                "description": cert.description,
                "created_at": cert.created_at,
                "difficulty_level": getattr(cert, 'difficulty_level', 'Intermediate'),
                "duration_hours": getattr(cert, 'duration_hours', 40)
            }
            for cert in available_certs
        ]
    }


@router.post("/mark-read/{notification_id}")
def mark_notification_read(
    notification_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Mark notification as read"""
    # This is a placeholder - in a real implementation, you'd store notifications in DB
    return {"message": "Notification marked as read"}
