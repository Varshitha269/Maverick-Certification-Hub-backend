from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.user import User


def log_audit(
    db: Session,
    *,
    actor: User | None,
    action: str,
    entity: str,
    entity_id: str | int | None = None,
    request: Request | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    row = AuditLog(
        actor_user_id=(actor.id if actor else None),
        action=action,
        entity=entity,
        entity_id=(str(entity_id) if entity_id is not None else None),
        ip=(request.client.host if request and request.client else None),
        user_agent=(request.headers.get("user-agent") if request else None),
        details_json=(json.dumps(details, ensure_ascii=False) if details else None),
    )
    db.add(row)
    db.commit()

