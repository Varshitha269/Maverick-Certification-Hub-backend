from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from azure.storage.blob import BlobServiceClient, ContentSettings, generate_blob_sas
from azure.storage.blob._shared.base_client import parse_connection_str  # type: ignore

from app.core.config import settings


@dataclass(frozen=True)
class StorageObject:
    blob_path: str
    size_bytes: int
    sha256: str


def _get_client() -> BlobServiceClient:
    if not settings.AZURE_STORAGE_CONNECTION_STRING:
        raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING is not configured")
    return BlobServiceClient.from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)


def ensure_container() -> None:
    client = _get_client()
    container = client.get_container_client(settings.AZURE_STORAGE_CONTAINER)
    try:
        container.create_container()
    except Exception:  # noqa: BLE001
        # container likely exists
        return


def upload_bytes(*, data: bytes, content_type: str | None, filename: str, user_id: int, purpose: str) -> StorageObject:
    ensure_container()
    sha = hashlib.sha256(data).hexdigest()
    safe_name = os.path.basename(filename).replace(" ", "_")
    ts = int(time.time())
    blob_path = f"{purpose}/user-{user_id}/{ts}-{sha[:12]}-{safe_name}"

    client = _get_client()
    blob_client = client.get_blob_client(container=settings.AZURE_STORAGE_CONTAINER, blob=blob_path)
    blob_client.upload_blob(
        data,
        overwrite=True,
        content_settings=ContentSettings(content_type=content_type or "application/octet-stream"),
    )
    return StorageObject(blob_path=blob_path, size_bytes=len(data), sha256=sha)


def get_blob_url(blob_path: str) -> str:
    client = _get_client()
    blob_client = client.get_blob_client(container=settings.AZURE_STORAGE_CONTAINER, blob=blob_path)
    return blob_client.url


def try_generate_sas_url(blob_path: str, *, expires_in_minutes: int = 30) -> str | None:
    """
    Best-effort SAS URL generator. Requires account key to be present in the connection string.
    """
    try:
        conn = parse_connection_str(settings.AZURE_STORAGE_CONNECTION_STRING)
        account_name = conn.get("AccountName")
        account_key = conn.get("AccountKey")
        if not account_name or not account_key:
            return None
        sas = generate_blob_sas(
            account_name=account_name,
            container_name=settings.AZURE_STORAGE_CONTAINER,
            blob_name=blob_path,
            account_key=account_key,
            permission="r",
            expiry=datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes),
        )
        return f"https://{account_name}.blob.core.windows.net/{settings.AZURE_STORAGE_CONTAINER}/{blob_path}?{sas}"
    except Exception:  # noqa: BLE001
        return None

