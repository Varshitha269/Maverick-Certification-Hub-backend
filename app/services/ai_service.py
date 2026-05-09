from __future__ import annotations

import json
import re
from dataclasses import dataclass

import httpx
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


def _provider() -> str:
    provider = (settings.AI_PROVIDER or "azure_openai").strip().lower()
    if provider not in {"azure_openai", "ollama"}:
        raise RuntimeError(f"Unsupported AI_PROVIDER: {settings.AI_PROVIDER}")
    return provider


def _azure_client() -> AzureOpenAI:
    if not settings.AZURE_OPENAI_ENDPOINT or not settings.AZURE_OPENAI_API_KEY:
        raise RuntimeError("Azure OpenAI is not configured")
    return AzureOpenAI(
        api_key=settings.AZURE_OPENAI_API_KEY,
        api_version=settings.AZURE_OPENAI_API_VERSION,
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
    )


def _extract_json_object(content: str) -> dict:
    try:
        parsed = json.loads(content or "{}")
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content or "", re.DOTALL)
        parsed = json.loads(match.group(0)) if match else {}
    return parsed if isinstance(parsed, dict) else {}


def _ollama_chat(messages: list[dict], *, temperature: float, json_mode: bool) -> str:
    if not settings.OLLAMA_BASE_URL or not settings.OLLAMA_MODEL:
        raise RuntimeError("Ollama is not configured")
    url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    body = {
        "model": settings.OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": 512},
    }
    if json_mode:
        body["format"] = "json"
    try:
        resp = httpx.post(url, json=body, timeout=settings.AI_REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
    except httpx.ConnectError as exc:
        raise RuntimeError(
            f"Could not connect to Ollama at {settings.OLLAMA_BASE_URL}. Start Ollama and run: ollama pull {settings.OLLAMA_MODEL}"
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"Ollama request failed: {exc.response.status_code} {exc.response.text}") from exc

    data = resp.json()
    message = data.get("message") or {}
    return message.get("content") or data.get("response") or ""


def _chat_completion(messages: list[dict], *, temperature: float = 0.2, json_mode: bool = False) -> str:
    provider = _provider()
    if provider == "ollama":
        return _ollama_chat(messages, temperature=temperature, json_mode=json_mode)

    client = _azure_client()
    kwargs = {
        "model": settings.AZURE_OPENAI_DEPLOYMENT,
        "temperature": temperature,
        "messages": messages,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or "{}"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def extract_certificate_text_info(text: str) -> CertificateExtraction:
    """
    Lightweight AI helper: given OCR/extracted text, return structured fields.
    Designed to be robust; if AI_DISABLED, caller should handle.
    """
    prompt = f"""
Extract certificate info from the text below. Return JSON with keys:
candidate_name, certification_title, provider, issued_on, credential_id, confidence (0-1).

Text:
{text}
""".strip()

    content = _chat_completion(
        [
            {"role": "system", "content": "You extract structured certificate info. Output ONLY valid JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        json_mode=True,
    )
    data = _extract_json_object(content)
    return CertificateExtraction(
        candidate_name=data.get("candidate_name"),
        certification_title=data.get("certification_title"),
        provider=data.get("provider"),
        issued_on=data.get("issued_on"),
        credential_id=data.get("credential_id"),
        confidence=float(data.get("confidence") or 0.0),
    )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def generate_task_plan(*, certification_title: str, weeks: int = 6, hours_per_week: int = 6) -> list[dict]:
    prompt = f"""
Create a study plan as a list of tasks to prepare for the certification "{certification_title}".
Constraints:
- Duration: {weeks} weeks
- Time: {hours_per_week} hours/week
- Output JSON object with a single key "tasks" that is an array of objects.
- Each task object keys: title, description, due_offset_days (int), priority (1-5)
""".strip()

    content = _chat_completion(
        [
            {"role": "system", "content": "You generate concise, practical study tasks. Output ONLY valid JSON object with key 'tasks'."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        json_mode=True,
    )
    parsed = _extract_json_object(content)
    tasks = parsed.get("tasks", []) if isinstance(parsed, dict) else []
    if not isinstance(tasks, list):
        return []
    return [t for t in tasks if isinstance(t, dict)]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def extract_skills_from_text(*, text: str) -> dict:
    """
    BRD AI: resume/profile skill extraction (no training; Azure OpenAI).
    Returns JSON: { "skills": [{ "name": str, "level": str|None, "evidence": str|None }], "summary": str }
    """
    prompt = f"""
Extract professional skills from the text below.
Return JSON with keys:
- skills: array of {{name, level(optional: beginner/intermediate/advanced), evidence(optional short quote)}}
- summary: 1-2 sentence summary of the profile

Text:
{text}
""".strip()
    content = _chat_completion(
        [
            {"role": "system", "content": "You extract skills into structured JSON. Output ONLY valid JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        json_mode=True,
    )
    parsed = _extract_json_object(content)
    if not isinstance(parsed, dict):
        return {"skills": [], "summary": ""}
    return {"skills": parsed.get("skills") or [], "summary": parsed.get("summary") or ""}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def generate_drive_exec_summary(*, drive_name: str, stats: dict) -> dict:
    """
    BRD AI: admin-friendly executive summary for a drive.
    Input stats should be small JSON.
    """
    prompt = f"""
Write an executive-ready summary for the certification drive.
Return JSON with keys: summary (string), risks (array of strings), next_actions (array of strings).

Drive: {drive_name}
Stats JSON:
{stats}
""".strip()
    content = _chat_completion(
        [
            {"role": "system", "content": "You produce concise leadership summaries. Output ONLY valid JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        json_mode=True,
    )
    parsed = _extract_json_object(content)
    if not isinstance(parsed, dict):
        return {"summary": "", "risks": [], "next_actions": []}
    return {
        "summary": parsed.get("summary") or "",
        "risks": parsed.get("risks") or [],
        "next_actions": parsed.get("next_actions") or [],
    }

