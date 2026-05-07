from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.models.notification import Notification, NotificationType
from app.models.user import User
from app.core.config import settings
from app.services.email_service import render_simple_email, send_email
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
        .limit(200)
        .all()
    )
    sent = 0
    for notification in rows:
        user = db.query(User).filter(User.id == notification.user_id, User.is_active.is_(True)).first()
        if not user:
            notification.email_sent_at = now
            db.add(notification)
            continue
        html = render_simple_email(
            notification.title,
            message_to_html(notification.message or "", notification.content_format),
            action_url=_absolute_frontend_url(notification.link_url),
            action_text="Open",
            preheader=f"{(notification.priority or 'medium').title()} priority broadcast",
        )
        result = send_email(db, to_email=user.email, subject=notification.title, html_content=html, user_id=user.id)
        if result.success:
            notification.email_sent_at = now
            db.add(notification)
        sent += 1
    db.commit()
    return {"checked": len(rows), "sent": sent}


def _absolute_frontend_url(link_url: str | None) -> str | None:
    if not link_url:
        return None
    if link_url.startswith("http://") or link_url.startswith("https://"):
        return link_url
    base = settings.FRONTEND_BASE_URL.rstrip("/")
    path = link_url if link_url.startswith("/") else f"/{link_url}"
    return f"{base}{path}"

