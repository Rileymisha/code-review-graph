"""Open WebUI chat completions client (stdlib urllib, no deps)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "http://localhost:3000"
DEFAULT_MODEL = "minimax"
DEFAULT_TIMEOUT_S = 30

SYSTEM_INTERPRET = "你是 shell 输出解读助手。只基于用户给你的数据描述,不要臆测。用 1-2 句话总结。"


def summarize_with_llm(
    prompt: str,
    system: str,
    *,
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> str | None:
    """POST Open WebUI /api/chat/completions; return assistant content, or None on any failure."""
    key = api_key or os.environ.get("OPENWEBUI_SMART_KEY")
    if not key:
        return None
    url = (base_url or os.environ.get("OPENWEBUI_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    chosen_model = model or os.environ.get("OPENWEBUI_MODEL") or DEFAULT_MODEL
    payload = {
        "model": chosen_model,
        "messages": [
            {"role": "system", "content": system or SYSTEM_INTERPRET},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }
    req = urllib.request.Request(
        f"{url}/api/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            if resp.status != 200:
                return None
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None