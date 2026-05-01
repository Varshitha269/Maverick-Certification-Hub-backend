from __future__ import annotations

from dataclasses import dataclass

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.email_log import EmailLog


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
        provider="sendgrid",
        success=False,
    )
    try:
        if not settings.SENDGRID_API_KEY:
            raise RuntimeError("SENDGRID_API_KEY is not configured")
        client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        message = Mail(from_email=settings.EMAIL_FROM, to_emails=to_email, subject=subject, html_content=html_content)
        resp = client.send(message)
        provider_message_id = None
        # SendGrid returns message id in headers sometimes; keep best-effort
        if resp and hasattr(resp, "headers"):
            provider_message_id = resp.headers.get("X-Message-Id") or resp.headers.get("x-message-id")
        log.success = True
        log.provider_message_id = provider_message_id
        db.add(log)
        db.commit()
        return EmailResult(success=True, provider_message_id=provider_message_id)
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

