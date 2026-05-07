from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.email_log import EmailLog

PROVIDER = "azure_communication"


def _html_to_plain(html: str) -> str:
    """Minimal HTML → plain text for ACS content.plainText."""
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:8000] if len(text) > 8000 else text


@dataclass(frozen=True)
class EmailResult:
    success: bool
    provider_message_id: str | None = None
    error: str | None = None


def send_email(db: Session, *, to_email: str, subject: str, html_content: str, user_id: int | None = None) -> EmailResult:
    log = EmailLog(
        user_id=user_id,
        to_email=to_email,
        subject=subject,
        body_preview=(html_content[:800] if html_content else None),
        provider=PROVIDER,
        success=False,
    )
    try:
        if not settings.ACS_EMAIL_CONNECTION_STRING:
            raise RuntimeError("ACS_EMAIL_CONNECTION_STRING is not configured")
        if not settings.EMAIL_FROM:
            raise RuntimeError("EMAIL_FROM is not configured (verified sender in Azure Communication Services)")

        from azure.communication.email import EmailClient

        client = EmailClient.from_connection_string(settings.ACS_EMAIL_CONNECTION_STRING)
        message = {
            "senderAddress": settings.EMAIL_FROM,
            "recipients": {"to": [{"address": to_email}]},
            "content": {
                "subject": subject,
                "html": html_content,
                "plainText": _html_to_plain(html_content) or subject,
            },
        }
        poller = client.begin_send(message)
        result = poller.result(timeout=15.0)

        provider_message_id = None
        status = None
        if isinstance(result, dict):
            provider_message_id = result.get("id")
            status = result.get("status")
        else:
            provider_message_id = getattr(result, "id", None)
            status = getattr(result, "status", None)

        if status and str(status).lower() not in ("succeeded", "success"):
            err = result.get("error") if isinstance(result, dict) else getattr(result, "error", None)
            raise RuntimeError(str(err or result))

        log.success = True
        log.provider_message_id = str(provider_message_id)[:200] if provider_message_id else None
        db.add(log)
        db.commit()
        return EmailResult(success=True, provider_message_id=log.provider_message_id)
    except Exception as e:  # noqa: BLE001
        log.success = False
        log.error = str(e)
        db.add(log)
        db.commit()
        return EmailResult(success=False, error=str(e))


def render_simple_email(
    title: str,
    body: str,
    action_url: str | None = None,
    action_text: str = "Open",
    *,
    preheader: str | None = None,
) -> str:
    button = ""
    if action_url:
        button = f"""
          <p style="margin-top:16px">
            <a href="{action_url}" style="background:#2563eb;color:#fff;text-decoration:none;padding:10px 14px;border-radius:8px;display:inline-block;">
              {action_text}
            </a>
          </p>
        """
    hidden_preheader = ""
    if preheader:
        hidden_preheader = f"""<div style="display:none;max-height:0;overflow:hidden;color:transparent;opacity:0">{preheader}</div>"""
    return f"""
    <div style="background:#f3f4f6;padding:22px 0">
      <div style="font-family:Segoe UI,Arial,sans-serif;max-width:680px;margin:0 auto;background:#ffffff;border-radius:14px;overflow:hidden;border:1px solid #e5e7eb">
        {hidden_preheader}
        <div style="background:linear-gradient(90deg,#1d4ed8,#2563eb);padding:16px 18px;color:#fff">
          <div style="font-size:14px;opacity:0.9">{settings.APP_NAME}</div>
          <div style="font-size:20px;font-weight:700;margin-top:4px">{title}</div>
        </div>
        <div style="padding:18px;color:#111827;line-height:1.55">
          {body}
          {button}
          <hr style="margin:18px 0;border:none;border-top:1px solid #e5e7eb"/>
          <div style="color:#6b7280;font-size:12px">Automated message. If you didn’t request this, you can ignore it.</div>
        </div>
      </div>
    </div>
    """.strip()

