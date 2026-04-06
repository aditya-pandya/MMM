from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from mmm_common import ValidationError

OPENAI_API_BASE = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/")


def resolve_openai_api_key() -> str:
    for env_name in ("MMM_OPENAI_API_KEY", "OPENAI_API_KEY"):
        value = os.environ.get(env_name, "").strip()
        if value:
            return value
    raise RuntimeError("Missing OpenAI API key. Set MMM_OPENAI_API_KEY or OPENAI_API_KEY.")


def post_openai_json(
    endpoint: str,
    payload: dict[str, Any],
    *,
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{OPENAI_API_BASE}{endpoint}",
        data=body,
        headers={
            "Authorization": f"Bearer {resolve_openai_api_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API request failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI API request failed: {exc.reason}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError("OpenAI API returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ValidationError("OpenAI API response must be a JSON object")
    return payload
