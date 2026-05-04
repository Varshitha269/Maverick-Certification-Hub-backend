from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.notification import Notification, NotificationType
from app.models.user import User, UserRole
from app.services.notification_service import create_notification, mark_read


router = APIRouter()


@router.get("/me")
def my_notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Notification).filter(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(200).all()
    return [
        {
            "id": n.id,
            "type": n.type,
            "title": n.title,
            "message": n.message,
            "link_url": n.link_url,
            "read_at": n.read_at,
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
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    title = (payload.get("title") or "").strip()
    message = (payload.get("message") or "").strip()
    link_url = (payload.get("link_url") or None)
    if not title or not message:
        raise HTTPException(status_code=400, detail="title and message are required")

    # broadcast to active users
    users = db.query(User).filter(User.is_active.is_(True)).all()
    for u in users:
        create_notification(db, user_id=u.id, type=NotificationType.system, title=title, message=message, link_url=link_url)
    return {"sent": len(users)}

