from __future__ import annotations

import base64
import hashlib
import os
import secrets
from dataclasses import dataclass

from cryptography.fernet import Fernet

from app.core.config import settings


def mask_code(code: str) -> str:
    c = (code or "").strip()
    if len(c) <= 4:
        return "****"
    return ("*" * max(6, len(c) - 4)) + c[-4:]


def _derive_fernet_key(raw: str) -> bytes:
    """
    Accept either:
    - a valid Fernet key (urlsafe base64 32 bytes), OR
    - any passphrase/string, which we hash to 32 bytes and base64-url encode.
    """
    s = (raw or "").strip()
    if not s:
        raise RuntimeError("VOUCHER_ENCRYPTION_KEY is not configured")
    try:
        # If it's already a valid Fernet key, Fernet() will accept it.
        Fernet(s.encode("utf-8"))
        return s.encode("utf-8")
    except Exception:  # noqa: BLE001
        digest = hashlib.sha256(s.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)


def encrypt_code(code: str) -> str:
    f = Fernet(_derive_fernet_key(settings.VOUCHER_ENCRYPTION_KEY))
    return f.encrypt(code.encode("utf-8")).decode("utf-8")


def decrypt_code(token: str) -> str:
    f = Fernet(_derive_fernet_key(settings.VOUCHER_ENCRYPTION_KEY))
    return f.decrypt(token.encode("utf-8")).decode("utf-8")


@dataclass(frozen=True)
class DeliveryToken:
    id: str


def new_delivery_token() -> DeliveryToken:
    return DeliveryToken(id=secrets.token_urlsafe(24))

