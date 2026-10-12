"""Shared helpers for the JSON objects the model is asked to return."""

from __future__ import annotations

import json


def strip_code_fence(text: str) -> str:
    """Remove a surrounding markdown code fence that models add habitually.

    Tolerates a language tag (```` ```json ````) and a trailing fence.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    body = stripped.split("\n", 1)[1] if "\n" in stripped else ""
    if body.rstrip().endswith("```"):
        body = body.rstrip()[:-3]
    return body.strip()


def load_json_object(text: str) -> dict:
    """Parse one JSON object, tolerating a code fence. Raises ValueError."""
    try:
        data = json.loads(strip_code_fence(text))
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("返回内容不是合法 JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("返回内容不是 JSON 对象")
    return data
