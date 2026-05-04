from fastapi import APIRouter, Depends
from sqlalchemy import func, and_, extract
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.task import Task, TaskStatus
from app.models.upload import UploadedFile
from app.models.user import User
from app.models.certification import Certification
from app.models.voucher import Voucher
from collections import defaultdict


router = APIRouter()


@router.get("/heatmap")
def get_activity_heatmap(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Get activity for the last 365 days for the contribution calendar"""
    year_ago = datetime.now(timezone.utc) - timedelta(days=365)
    
    # Store aggregated activities by YYYY-MM-DD string
    activity_map = defaultdict(list)
    
    # 1. Enrollments (Created)
    enrollments = db.query(Enrollment).filter(
        Enrollment.user_id == user.id,
        Enrollment.created_at >= year_ago
    ).all()
    
    for enr in enrollments:
        c = db.query(Certification).filter(Certification.id == enr.certification_id).first()
        if not c: continue
        date_str = enr.created_at.strftime("%Y-%m-%d")
        
        # Determine specific action
        action_text = "Started" if enr.status != EnrollmentStatus.saved_for_later else "Saved"
        
        activity_map[date_str].append({
            "id": f"enr_{enr.id}",
            "type": "enrollment",
            "title": f"{action_text} {c.title}",
            "time": enr.created_at.isoformat(),
            "url": f"/learning/{enr.id}"
        })
        
        # If completed, add an event for completion
        if enr.status == EnrollmentStatus.completed and enr.updated_at and enr.updated_at >= year_ago:
            completed_str = enr.updated_at.strftime("%Y-%m-%d")
            activity_map[completed_str].append({
                "id": f"comp_{enr.id}",
                "type": "completion",
                "title": f"Completed {c.title}!",
                "time": enr.updated_at.isoformat(),
                "url": "/certifications"
            })
            
    # 2. Tasks (Completed)
    completed_tasks = db.query(Task).filter(
        Task.user_id == user.id,
        Task.status == TaskStatus.done,
        Task.updated_at >= year_ago
    ).all()
    
    for task in completed_tasks:
        if not task.updated_at: continue
        date_str = task.updated_at.strftime("%Y-%m-%d")
        activity_map[date_str].append({
            "id": f"task_{task.id}",
            "type": "task",
            "title": f"Completed task: {task.title}",
            "time": task.updated_at.isoformat(),
            "url": f"/learning/{task.enrollment_id}" if task.enrollment_id else "/dashboard"
        })
        
    # 3. Vouchers
    vouchers = db.query(Voucher).filter(
        Voucher.user_id == user.id,
        Voucher.created_at >= year_ago
    ).all()
    
    for v in vouchers:
        date_str = v.created_at.strftime("%Y-%m-%d")
        c = db.query(Certification).filter(Certification.id == v.certification_id).first() if v.certification_id else None
        cert_title = c.title if c else "a certification"
        activity_map[date_str].append({
            "id": f"vouch_{v.id}",
            "type": "voucher",
            "title": f"Received voucher for {cert_title}",
            "time": v.created_at.isoformat(),
            "url": "/dashboard"
        })
        
        # If redeemed
        if v.status == "redeemed" and v.updated_at and v.updated_at >= year_ago:
            red_str = v.updated_at.strftime("%Y-%m-%d")
            activity_map[red_str].append({
                "id": f"vouch_red_{v.id}",
                "type": "voucher",
                "title": f"Redeemed voucher for {cert_title}",
                "time": v.updated_at.isoformat(),
                "url": "/dashboard"
            })
            
    # Sort activities within each day by time descending
    for day in activity_map:
        activity_map[day] = sorted(activity_map[day], key=lambda x: x["time"], reverse=True)
            
    return {
        "heatmap": {k: v for k, v in activity_map.items()}
    }

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

    # Current active certifications with progress
    active_enrollments = (
        db.query(Enrollment)
        .filter(
            Enrollment.user_id == user.id,
            Enrollment.status.in_([EnrollmentStatus.selected, EnrollmentStatus.in_progress])
        )
        .order_by(Enrollment.updated_at.desc())
        .limit(3)
        .all()
    )
    
    current_certs = []
    for enr in active_enrollments:
        c = db.query(Certification).filter(Certification.id == enr.certification_id).first()
        if c:
            # calculate a mock due date based on created_at or updated_at
            # assuming duration is ~30 days
            due_date = (enr.created_at + timedelta(days=30)).strftime("%m/%d/%Y")
            current_certs.append({
                "id": c.id,
                "title": c.title,
                "provider": c.provider,
                "status": "In Progress" if enr.status == EnrollmentStatus.in_progress else "Enrolled",
                "progress": enr.progress_percent or 0,
                "due_date": due_date
            })

    return {
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role},
        "enrollments": {"total": enrollments_total, "active": enrollments_active},
        "tasks": {"total": tasks_total, "open": tasks_open, "completed": completed_tasks},
        "uploads": {"total": uploads_total},
        "current_certifications": current_certs,
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

