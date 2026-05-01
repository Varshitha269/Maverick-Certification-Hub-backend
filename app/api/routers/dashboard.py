from fastapi import APIRouter, Depends
from sqlalchemy import func, and_, extract
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.task import Task, TaskStatus
from app.models.upload import UploadedFile
from app.models.user import User
from app.models.certification import Certification


router = APIRouter()


@router.get("/me")
def my_dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Basic stats
    enrollments_total = db.query(func.count(Enrollment.id)).filter(Enrollment.user_id == user.id).scalar() or 0
    enrollments_active = (
        db.query(func.count(Enrollment.id))
        .filter(
            Enrollment.user_id == user.id,
            Enrollment.status.in_([EnrollmentStatus.selected, EnrollmentStatus.in_progress]),
        )
        .scalar()
        or 0
    )
    tasks_total = db.query(func.count(Task.id)).filter(Task.user_id == user.id).scalar() or 0
    tasks_open = (
        db.query(func.count(Task.id))
        .filter(Task.user_id == user.id, Task.status.in_([TaskStatus.todo, TaskStatus.doing, TaskStatus.blocked]))
        .scalar()
        or 0
    )
    uploads_total = db.query(func.count(UploadedFile.id)).filter(UploadedFile.user_id == user.id).scalar() or 0

    # Chart data - User certification status distribution
    completed_certs = (
        db.query(func.count(Enrollment.id))
        .filter(
            Enrollment.user_id == user.id,
            Enrollment.status == EnrollmentStatus.completed
        )
        .scalar() or 0
    )
    pending_certs = (
        db.query(func.count(Enrollment.id))
        .filter(
            Enrollment.user_id == user.id,
            Enrollment.status == EnrollmentStatus.selected
        )
        .scalar() or 0
    )
    in_progress_certs = (
        db.query(func.count(Enrollment.id))
        .filter(
            Enrollment.user_id == user.id,
            Enrollment.status == EnrollmentStatus.in_progress
        )
        .scalar() or 0
    )
    not_started = enrollments_total - completed_certs - pending_certs - in_progress_certs

    # Weekly progress (last 7 days)
    week_ago = datetime.now() - timedelta(days=7)
    weekly_progress = (
        db.query(func.count(Enrollment.id))
        .filter(
            Enrollment.user_id == user.id,
            Enrollment.created_at >= week_ago
        )
        .scalar() or 0
    )

    # Monthly progress (last 30 days)
    month_ago = datetime.now() - timedelta(days=30)
    monthly_progress = (
        db.query(func.count(Enrollment.id))
        .filter(
            Enrollment.user_id == user.id,
            Enrollment.created_at >= month_ago
        )
        .scalar() or 0
    )

    # Task completion data
    completed_tasks = (
        db.query(func.count(Task.id))
        .filter(
            Task.user_id == user.id,
            Task.status == TaskStatus.done
        )
        .scalar() or 0
    )

    return {
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role},
        "enrollments": {"total": enrollments_total, "active": enrollments_active},
        "tasks": {"total": tasks_total, "open": tasks_open, "completed": completed_tasks},
        "uploads": {"total": uploads_total},
        "charts": {
            "certification_status": {
                "completed": completed_certs,
                "pending": pending_certs,
                "in_progress": in_progress_certs,
                "not_started": max(0, not_started)
            },
            "progress": {
                "weekly": weekly_progress,
                "monthly": monthly_progress
            }
        }
    }


@router.get("/charts")
def get_charts(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Get detailed chart data for dashboard"""
    
    # Monthly progress for the last 6 months
    six_months_ago = datetime.now() - timedelta(days=180)
    monthly_data = []
    
    for i in range(6):
        month_start = datetime.now() - timedelta(days=30 * (i + 1))
        month_end = datetime.now() - timedelta(days=30 * i)
        
        enrollments_count = (
            db.query(func.count(Enrollment.id))
            .filter(
                Enrollment.user_id == user.id,
                Enrollment.created_at >= month_start,
                Enrollment.created_at < month_end
            )
            .scalar() or 0
        )
        
        completed_count = (
            db.query(func.count(Enrollment.id))
            .filter(
                Enrollment.user_id == user.id,
                Enrollment.status == EnrollmentStatus.completed,
                Enrollment.created_at >= month_start,
                Enrollment.created_at < month_end
            )
            .scalar() or 0
        )
        
        monthly_data.append({
            "month": month_start.strftime("%b"),
            "enrollments": enrollments_count,
            "completed": completed_count
        })
    
    # Weekly activity (last 7 days)
    weekly_activity = []
    for i in range(7):
        day_start = datetime.now() - timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        
        hours_spent = (
            db.query(func.count(Task.id))
            .filter(
                Task.user_id == user.id,
                Task.created_at >= day_start,
                Task.created_at < day_end
            )
            .scalar() or 0
        )
        
        weekly_activity.append({
            "day": day_start.strftime("%a")[:3],
            "hours": hours_spent * 2  # Assuming each task takes ~2 hours
        })
    
    return {
        "monthly_progress": list(reversed(monthly_data)),
        "weekly_activity": list(reversed(weekly_activity))
    }

