import datetime as dt

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.user import User
from app.services.email_service import render_simple_email, send_email
from app.services.notification_service import create_notification
from app.models.notification import NotificationType


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def send_pending_and_overdue_reminders(db: Session) -> dict:
    """
    Hackathon-friendly reminder job.
    - pending: selected/in_progress with low progress
    - overdue: created long ago OR target date passed (if provided)
    """
    overdue_after = dt.timedelta(days=settings.OVERDUE_AFTER_DAYS)
    now = _utcnow()

    enrollments = (
        db.query(Enrollment)
        .filter(Enrollment.status.in_([EnrollmentStatus.selected, EnrollmentStatus.in_progress]))
        .all()
    )

    sent = 0
    errors = 0
    for e in enrollments:
        user: User | None = db.query(User).filter(User.id == e.user_id).first()
        if not user or not user.is_active:
            continue

        overdue = False
        if e.created_at and (now - e.created_at) > overdue_after and (e.progress_percent or 0) < 100:
            overdue = True

        if e.target_completion_date:
            try:
                target = dt.datetime.fromisoformat(e.target_completion_date.replace("Z", "+00:00"))
                if target.tzinfo is None:
                    target = target.replace(tzinfo=dt.timezone.utc)
                if now > target and (e.progress_percent or 0) < 100:
                    overdue = True
            except Exception:  # noqa: BLE001
                pass

        if overdue:
            subject = "Certification overdue — action required"
            body = (
                "Your selected certification is still pending completion. "
                "Please update your progress or complete pending steps."
            )
        elif (e.progress_percent or 0) < 20:
            subject = "Reminder: start your selected certification"
            body = "You selected a certification but progress is still low. Start today and update your progress."
        else:
            continue

        create_notification(
            db,
            user_id=user.id,
            type=NotificationType.reminder,
            title=subject,
            message=body,
            link_url=f"{settings.FRONTEND_BASE_URL}/dashboard",
        )
        html = render_simple_email(
            subject,
            body,
            action_url=f"{settings.FRONTEND_BASE_URL}/dashboard",
            action_text="Open dashboard",
            preheader=subject,
        )
        result = send_email(db, to_email=user.email, subject=subject, html_content=html, user_id=user.id)
        if result.success:
            sent += 1
        else:
            errors += 1

    return {"sent": sent, "errors": errors, "checked": len(enrollments)}

