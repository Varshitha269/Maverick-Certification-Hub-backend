from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.models.notification import Notification, NotificationType


def create_notification(
    db: Session,
    *,
    user_id: int,
    type: NotificationType,
    title: str,
    message: str,
    link_url: str | None = None,
) -> Notification:
    row = Notification(user_id=user_id, type=type, title=title[:200], message=message, link_url=link_url)
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

