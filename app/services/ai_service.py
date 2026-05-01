from __future__ import annotations

from dataclasses import dataclass

from openai import AzureOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings


@dataclass(frozen=True)
class CertificateExtraction:
    candidate_name: str | None
    certification_title: str | None
    provider: str | None
    issued_on: str | None
    credential_id: str | None
    confidence: float


def _client() -> AzureOpenAI:
    if not settings.AZURE_OPENAI_ENDPOINT or not settings.AZURE_OPENAI_API_KEY:
        raise RuntimeError("Azure OpenAI is not configured")
    return AzureOpenAI(
        api_key=settings.AZURE_OPENAI_API_KEY,
        api_version=settings.AZURE_OPENAI_API_VERSION,
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
    )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def extract_certificate_text_info(text: str) -> CertificateExtraction:
    """
    Lightweight AI helper: given OCR/extracted text, return structured fields.
    Designed to be robust; if AI_DISABLED, caller should handle.
    """
    client = _client()
    prompt = f"""
Extract certificate info from the text below. Return JSON with keys:
candidate_name, certification_title, provider, issued_on, credential_id, confidence (0-1).

Text:
{text}
""".strip()

    resp = client.chat.completions.create(
        model=settings.AZURE_OPENAI_DEPLOYMENT,
        temperature=0.1,
        messages=[
            {"role": "system", "content": "You extract structured certificate info. Output ONLY valid JSON."},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content or "{}"
    # Pydantic-free parse to keep deps minimal
    import json  # noqa: PLC0415

    data = json.loads(content)
    return CertificateExtraction(
        candidate_name=data.get("candidate_name"),
        certification_title=data.get("certification_title"),
        provider=data.get("provider"),
        issued_on=data.get("issued_on"),
        credential_id=data.get("credential_id"),
        confidence=float(data.get("confidence") or 0.0),
    )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def generate_task_plan(*, certification_title: str, weeks: int = 6, hours_per_week: int = 6) -> list[dict]:
    client = _client()
    prompt = f"""
Create a study plan as a list of tasks to prepare for the certification "{certification_title}".
Constraints:
- Duration: {weeks} weeks
- Time: {hours_per_week} hours/week
- Output JSON object with a single key "tasks" that is an array of objects.
- Each task object keys: title, description, due_offset_days (int), priority (1-5)
""".strip()

    resp = client.chat.completions.create(
        model=settings.AZURE_OPENAI_DEPLOYMENT,
        temperature=0.3,
        messages=[
            {"role": "system", "content": "You generate concise, practical study tasks. Output ONLY valid JSON object with key 'tasks'."},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content or "{}"
    import json  # noqa: PLC0415

    parsed = json.loads(content)
    tasks = parsed.get("tasks", []) if isinstance(parsed, dict) else []
    if not isinstance(tasks, list):
        return []
    return [t for t in tasks if isinstance(t, dict)]

