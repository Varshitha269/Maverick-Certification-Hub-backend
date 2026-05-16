from __future__ import annotations

import datetime as dt
import re

from sqlalchemy.orm import Session

from app.models.notification import Notification, NotificationType
from app.models.user import User, UserRole
from app.core.config import settings
from app.services.email_service import EmailResult, render_simple_email, send_email
from app.services.message_formatting import message_to_html


def create_notification(
    db: Session,
    *,
    user_id: int,
    type: NotificationType,
    title: str,
    message: str,
    link_url: str | None = None,
    priority: str | None = None,
    image_url: str | None = None,
    icon: str | None = None,
    scheduled_at: dt.datetime | None = None,
    expires_at: dt.datetime | None = None,
    push_enabled: bool = True,
    email_enabled: bool = False,
    audience: str | None = None,
    content_format: str = "plain",
    deliver_email_now: bool = True,
) -> Notification:
    row = Notification(
        user_id=user_id,
        type=type,
        title=title[:200],
        message=message,
        link_url=link_url,
        priority=priority,
        image_url=image_url,
        icon=icon,
        scheduled_at=scheduled_at,
        expires_at=expires_at,
        push_enabled=push_enabled,
        email_enabled=email_enabled,
        audience=audience,
        content_format=content_format,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    if deliver_email_now:
        _deliver_notification_email(db, row, dt.datetime.now(dt.timezone.utc))
    return row


def mark_read(db: Session, *, user_id: int, notification_id: int) -> bool:
    row = db.query(Notification).filter(Notification.id == notification_id, Notification.user_id == user_id).first()
    if not row:
        return False
    if row.read_at is None:
        row.read_at = dt.datetime.now(dt.timezone.utc)
        db.add(row)
        db.commit()
    return True


def deliver_due_notification_emails(db: Session) -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    rows = (
        db.query(Notification)
        .filter(
            Notification.email_enabled.is_(True),
            Notification.email_sent_at.is_(None),
            (Notification.scheduled_at.is_(None)) | (Notification.scheduled_at <= now),
            (Notification.expires_at.is_(None)) | (Notification.expires_at > now),
        )
        .order_by(Notification.created_at.asc())
        .limit(max(1, settings.EMAIL_DELIVERY_BATCH_SIZE))
        .all()
    )
    sent = 0
    errors = 0
    for notification in rows:
        result = _deliver_notification_email(db, notification, now)
        if result.success:
            sent += 1
        else:
            errors += 1
    db.commit()
    return {"checked": len(rows), "sent": sent, "errors": errors}


def notify_admins(
    db: Session,
    *,
    title: str,
    message: str,
    link_url: str | None = None,
    priority: str = "medium",
    icon: str = "admin",
    exclude_user_id: int | None = None,
) -> int:
    admins = (
        db.query(User)
        .filter(User.role == UserRole.admin, User.is_active.is_(True))
        .all()
    )
    sent = 0
    for admin in admins:
        if exclude_user_id is not None and admin.id == exclude_user_id:
            continue
        create_notification(
            db,
            user_id=admin.id,
            type=NotificationType.system,
            title=title,
            message=message,
            link_url=link_url or "/dashboard",
            priority=priority,
            icon=icon,
            audience="admins",
            email_enabled=True,
        )
        sent += 1
    return sent


def _deliver_notification_email(db: Session, notification: Notification, now: dt.datetime) -> EmailResult:
    if not notification.email_enabled or notification.email_sent_at is not None:
        return EmailResult(success=True)
    if notification.scheduled_at and notification.scheduled_at > now:
        return EmailResult(success=True)
    if notification.expires_at and notification.expires_at <= now:
        notification.email_sent_at = now
        db.add(notification)
        db.commit()
        return EmailResult(success=True)

    user = db.query(User).filter(User.id == notification.user_id, User.is_active.is_(True)).first()
    if not user:
        notification.email_sent_at = now
        db.add(notification)
        db.commit()
        return EmailResult(success=True)
    html = render_simple_email(
        notification.title,
        message_to_html(notification.message or "", notification.content_format),
        action_url=_absolute_frontend_url(notification.link_url),
        action_text="Open",
        preheader=f"{(notification.priority or 'medium').title()} priority notification",
    )
    result = send_email(db, to_email=user.email, subject=notification.title, html_content=html, user_id=user.id)
    if result.success:
        notification.email_sent_at = now
        db.add(notification)
        db.commit()
    else:
        retry_after = _retry_after(result.error)
        notification.scheduled_at = now + dt.timedelta(seconds=retry_after)
        db.add(notification)
        db.commit()
    return result


def _retry_after(error: str | None) -> int:
    default_retry = max(60, settings.EMAIL_RETRY_AFTER_SECONDS)
    if not error:
        return default_retry
    match = re.search(r"after\s+(\d+)\s+seconds", error, flags=re.IGNORECASE)
    if not match:
        return default_retry
    seconds = int(match.group(1))
    return max(60, seconds or settings.EMAIL_RETRY_AFTER_SECONDS)


def _absolute_frontend_url(link_url: str | None) -> str | None:
    if not link_url:
        return None
    if link_url.startswith("http://") or link_url.startswith("https://"):
        return link_url
    base = settings.FRONTEND_BASE_URL.rstrip("/")
    path = link_url if link_url.startswith("/") else f"/{link_url}"
    return f"{base}{path}"

