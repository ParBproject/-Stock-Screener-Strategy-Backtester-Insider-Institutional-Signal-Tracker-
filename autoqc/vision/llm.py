"""Optional vision-LLM adapter. Disabled unless an endpoint is configured."""

from __future__ import annotations

import json
import os
import urllib.request

import numpy as np

from autoqc.rules.loader import RuleSet


def understand_frame(image: np.ndarray, rules: RuleSet) -> dict | None:
    """Ask a configured endpoint to describe a frame. Failures return None."""
    if not bool(rules.get("vision_llm.enabled", False)):
        return None
    endpoint = str(rules.get("vision_llm.endpoint", "") or "")
    if not endpoint:
        return None
    key_env = str(rules.get("vision_llm.api_key_env", "AUTOQC_VISION_API_KEY"))
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get(key_env, "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = json.dumps(
        {
            "model": rules.get("vision_llm.model", ""),
            "width": int(image.shape[1]),
            "height": int(image.shape[0]),
        }
    ).encode("utf-8")
    request = urllib.request.Request(endpoint, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            body = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    return body if isinstance(body, dict) else None
