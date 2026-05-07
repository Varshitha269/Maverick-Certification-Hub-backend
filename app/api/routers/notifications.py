import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.core.config import settings
from app.db.session import get_db
from app.models.notification import Notification, NotificationType
from app.models.user import User, UserRole
from app.services.audit_service import log_audit
from app.services.email_service import render_simple_email, send_email
from app.services.message_formatting import message_to_html
from app.services.notification_service import create_notification, mark_read


router = APIRouter()


@router.get("/me")
def my_notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    now = dt.datetime.now(dt.timezone.utc)
    rows = (
        db.query(Notification)
        .filter(
            Notification.user_id == user.id,
            (Notification.scheduled_at.is_(None)) | (Notification.scheduled_at <= now),
            (Notification.expires_at.is_(None)) | (Notification.expires_at > now),
        )
        .order_by(Notification.created_at.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "id": n.id,
            "type": n.type,
            "title": n.title,
            "message": n.message,
            "link_url": n.link_url,
            "priority": n.priority,
            "image_url": n.image_url,
            "icon": n.icon,
            "scheduled_at": n.scheduled_at,
            "expires_at": n.expires_at,
            "push_enabled": n.push_enabled,
            "email_enabled": n.email_enabled,
            "audience": n.audience,
            "content_format": n.content_format,
            "read_at": n.read_at,
            "email_sent_at": n.email_sent_at,
            "created_at": n.created_at,
        }
        for n in rows
    ]


@router.post("/me/{notification_id}/read")
def read_notification(notification_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ok = mark_read(db, user_id=user.id, notification_id=notification_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"ok": True}

@router.post("/me/read-all")
def read_all_notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.query(Notification).filter(
        Notification.user_id == user.id, 
        Notification.read_at.is_(None)
    ).update({"read_at": func.now()})
    db.commit()
    return {"ok": True}

@router.delete("/me/{notification_id}")
def delete_notification(notification_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.query(Notification).filter(Notification.id == notification_id, Notification.user_id == user.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Notification not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/broadcast")
def admin_broadcast(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    title = (payload.get("title") or "").strip()
    message = (payload.get("message") or "").strip()
    link_url = (payload.get("link_url") or "/home")
    priority = (payload.get("priority") or "medium").strip().lower()
    if priority not in {"high", "medium", "low"}:
        raise HTTPException(status_code=400, detail="priority must be high, medium, or low")
    image_url = (payload.get("image_url") or None)
    icon = (payload.get("icon") or None)
    audience = (payload.get("audience") or "active_users").strip()
    content_format = (payload.get("content_format") or "plain").strip()
    if content_format not in {"plain", "markdown", "rich_text"}:
        raise HTTPException(status_code=400, detail="content_format must be plain, markdown, or rich_text")
    push_enabled = bool(payload.get("push_enabled", True))
    email_enabled = bool(payload.get("email_enabled", True))
    scheduled_at = _parse_dt(payload.get("scheduled_at"))
    expires_at = _parse_dt(payload.get("expires_at"))
    if not title or not message:
        raise HTTPException(status_code=400, detail="title and message are required")
    if expires_at and scheduled_at and expires_at <= scheduled_at:
        raise HTTPException(status_code=400, detail="Expiry date must be after scheduled date")

    users = _with_active_admins(db, _audience_users(db, audience))
    created_notifications = []
    for u in users:
        created_notifications.append(create_notification(
            db,
            user_id=u.id,
            type=NotificationType.system,
            title=title,
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
        ))

    emails_attempted = 0
    emails_sent = 0
    now = dt.datetime.now(dt.timezone.utc)
    if email_enabled and (scheduled_at is None or scheduled_at <= now):
        html = render_simple_email(
            title,
            message_to_html(message, content_format),
            action_url=_absolute_frontend_url(link_url),
            action_text="Open",
            preheader=f"{priority.title()} priority broadcast",
        )
        for u, notification in zip(users, created_notifications):
            result = send_email(db, to_email=u.email, subject=title, html_content=html, user_id=u.id)
            if result.success:
                notification.email_sent_at = now
                db.add(notification)
                emails_sent += 1
            emails_attempted += 1
        db.commit()

    log_audit(
        db,
        actor=admin,
        action="notification.broadcast",
        entity="notification",
        entity_id="bulk",
        request=request,
        details={
            "sent": len(users),
            "audience": audience,
            "priority": priority,
            "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "push_enabled": push_enabled,
            "email_enabled": email_enabled,
            "emails_attempted": emails_attempted,
            "emails_sent": emails_sent,
        },
    )
    return {
        "sent": len(users),
        "emails_attempted": emails_attempted,
        "emails_sent": emails_sent,
        "emails_failed": max(0, emails_attempted - emails_sent),
        "scheduled": bool(scheduled_at and scheduled_at > now),
    }


def _parse_dt(value):
    if not value:
        return None
    if isinstance(value, dt.datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid datetime: {value}") from exc


def _audience_users(db: Session, audience: str):
    q = db.query(User)
    if audience == "active_users":
        return q.filter(User.is_active.is_(True)).all()
    if audience == "all_users":
        return q.all()
    if audience == "learners":
        return q.filter(User.role == UserRole.user, User.is_active.is_(True)).all()
    if audience == "admins":
        return q.filter(User.role == UserRole.admin, User.is_active.is_(True)).all()
    raise HTTPException(status_code=400, detail="Invalid audience")


def _with_active_admins(db: Session, users: list[User]):
    rows = {user.id: user for user in users}
    for admin in db.query(User).filter(User.role == UserRole.admin, User.is_active.is_(True)).all():
        rows[admin.id] = admin
    return list(rows.values())


def _absolute_frontend_url(link_url: str | None) -> str | None:
    if not link_url:
        return None
    if link_url.startswith("http://") or link_url.startswith("https://"):
        return link_url
    base = settings.FRONTEND_BASE_URL.rstrip("/")
    path = link_url if link_url.startswith("/") else f"/{link_url}"
    return f"{base}{path}"

