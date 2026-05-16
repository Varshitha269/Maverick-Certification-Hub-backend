import datetime as dt

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.user import User
from app.services.notification_service import create_notification
from app.models.notification import Notification, NotificationType


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def send_pending_and_overdue_reminders(
    db: Session,
    *,
    user_scope: str = "active",
    user_id: int | None = None,
    enrollment_status: str = "pending",
    include_broadcast_expiry: bool = False,
    broadcast_expiry_days: int = 7,
) -> dict:
    """
    Hackathon-friendly reminder job.
    - pending: selected/in_progress with low progress
    - overdue: created long ago OR target date passed (if provided)
    """
    overdue_after = dt.timedelta(days=settings.OVERDUE_AFTER_DAYS)
    now = _utcnow()

    q = db.query(Enrollment)
    if user_id is not None:
        q = q.filter(Enrollment.user_id == user_id)

    if enrollment_status == "pending":
        q = q.filter(Enrollment.status.in_([EnrollmentStatus.selected, EnrollmentStatus.in_progress]))
    elif enrollment_status == "all":
        q = q.filter(
            Enrollment.status.in_(
                [EnrollmentStatus.saved_for_later, EnrollmentStatus.selected, EnrollmentStatus.in_progress]
            )
        )
    elif enrollment_status != "all":
        try:
            q = q.filter(Enrollment.status == EnrollmentStatus(enrollment_status))
        except ValueError:
            q = q.filter(Enrollment.status.in_([EnrollmentStatus.selected, EnrollmentStatus.in_progress]))

    enrollments = q.all()

    sent = 0
    errors = 0
    skipped_users = 0
    for e in enrollments:
        user: User | None = db.query(User).filter(User.id == e.user_id).first()
        if not user:
            skipped_users += 1
            continue
        if user_scope == "active" and not user.is_active:
            skipped_users += 1
            continue
        if user_scope == "inactive" and user.is_active:
            skipped_users += 1
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
        elif e.status == EnrollmentStatus.saved_for_later:
            subject = "Reminder: saved certification waiting"
            body = "You saved a certification for later. Enroll when you are ready to continue."
        elif (e.progress_percent or 0) < 20:
            subject = "Reminder: start your selected certification"
            body = "You selected a certification but progress is still low. Start today and update your progress."
        else:
            continue

        notification = create_notification(
            db,
            user_id=user.id,
            type=NotificationType.reminder,
            title=subject,
            message=body,
            link_url=f"{settings.FRONTEND_BASE_URL}/dashboard",
            email_enabled=True,
        )
        if notification.email_sent_at:
            sent += 1
        else:
            errors += 1

    broadcast_reminders = 0
    if include_broadcast_expiry:
        broadcast_reminders = _send_broadcast_expiry_reminders(
            db,
            user_scope=user_scope,
            user_id=user_id,
            within_days=broadcast_expiry_days,
        )

    return {
        "sent": sent,
        "errors": errors,
        "checked": len(enrollments),
        "skipped_users": skipped_users,
        "broadcast_expiry_reminders": broadcast_reminders,
    }


def _send_broadcast_expiry_reminders(
    db: Session,
    *,
    user_scope: str,
    user_id: int | None,
    within_days: int,
) -> int:
    now = _utcnow()
    until = now + dt.timedelta(days=max(1, min(within_days, 60)))
    q = db.query(Notification).filter(
        Notification.type == NotificationType.system,
        Notification.expires_at.isnot(None),
        Notification.expires_at > now,
        Notification.expires_at <= until,
    )
    if user_id is not None:
        q = q.filter(Notification.user_id == user_id)

    sent = 0
    for notification in q.limit(500).all():
        user = db.query(User).filter(User.id == notification.user_id).first()
        if not user:
            continue
        if user_scope == "active" and not user.is_active:
            continue
        if user_scope == "inactive" and user.is_active:
            continue
        create_notification(
            db,
            user_id=user.id,
            type=NotificationType.reminder,
            title=f"Reminder: {notification.title}",
            message=f"This broadcast expires on {notification.expires_at.date()}. Please review it before it closes.",
            link_url=notification.link_url or f"{settings.FRONTEND_BASE_URL}/notifications",
            priority=notification.priority or "medium",
            icon=notification.icon or "announcement",
            email_enabled=True,
        )
        sent += 1
    return sent

