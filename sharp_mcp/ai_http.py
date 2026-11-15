"""Shared error handling for Gemini and OpenRouter JSON responses."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp


class AIRequestError(ValueError):
    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def redact_error(text: str, api_key: str) -> str:
    return text.replace(api_key, "[REDACTED]") if api_key else text


async def post_json(
    url: str, *, headers: dict[str, str], payload: dict[str, Any], api_key: str, timeout_sec: float,
) -> dict[str, Any]:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_sec)) as session:
            async with session.post(url, json=payload, headers=headers) as response:
                raw = await response.text()
                if response.status >= 400:
                    raise AIRequestError(f"HTTP {response.status}: {redact_error(raw, api_key)[:400]}", status=response.status)
                try:
                    data = json.loads(raw)
                except ValueError:
                    raise AIRequestError("Provider returned invalid JSON.") from None
                if not isinstance(data, dict):
                    raise AIRequestError("Provider returned a non-object response.")
                if data.get("error"):
                    raise AIRequestError(f"Provider error: {redact_error(json.dumps(data['error']), api_key)[:400]}")
                return data
    except (aiohttp.ClientError, asyncio.TimeoutError):
        raise AIRequestError("Provider request failed or timed out.") from None


def response_content(data: dict[str, Any], provider: str) -> dict[str, Any]:
    if provider == "gemini":
        if (data.get("promptFeedback") or {}).get("blockReason"):
            raise AIRequestError("Gemini blocked the prompt.")
        candidates = data.get("candidates") or []
        if not candidates:
            raise AIRequestError("Gemini returned no candidates.")
        candidate = candidates[0]
        if candidate.get("finishReason") not in (None, "STOP"):
            raise AIRequestError("Gemini response was blocked or incomplete.")
        return candidate.get("content") or {}
    choices = data.get("choices") or []
    if not choices:
        raise AIRequestError("OpenRouter returned no choices.")
    choice = choices[0]
    if choice.get("finish_reason") not in (None, "stop"):
        raise AIRequestError("OpenRouter response was blocked or incomplete.")
    message = choice.get("message") or {}
    if message.get("refusal"):
        raise AIRequestError("OpenRouter refused the request.")
    return message


def response_text(data: dict[str, Any], provider: str) -> str:
    content = response_content(data, provider)
    parts = content.get("parts") if provider == "gemini" else content.get("content")
    if isinstance(parts, str):
        text = parts.strip()
    else:
        text = "\n".join(str(p["text"]) for p in (parts or []) if isinstance(p, dict) and p.get("text")).strip()
    if not text:
        raise AIRequestError("Provider returned no text content.")
    return text
