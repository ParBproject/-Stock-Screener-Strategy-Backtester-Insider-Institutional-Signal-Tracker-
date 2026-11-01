"""Classify whether an utterance says what, where, and why.

The deterministic rules are the default. An HTTP classifier is used only
when ``narration.endpoint`` is set, and any failure falls back here.
"""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass

from autoqc.models import Action
from autoqc.rules.loader import RuleSet

_WHAT = re.compile(
    r"\b(click|clicks|clicking|open|opens|opening|type|types|typing|select|selects|"
    r"press|scroll|drag|enter|save|export|choose|move|close|minimize|write|draw|"
    r"highlight|copy|paste|rename|delete|create|upload|download|adjust|set|change|tap)\b",
    re.IGNORECASE,
)
_WHERE = re.compile(
    r"\b(top|bottom|left|right|menu|button|sidebar|dock|toolbar|window|field|tab|"
    r"panel|corner|dialog|folder|bar)\b",
    re.IGNORECASE,
)
_WHY = re.compile(r"\b(to|so|because|so that|in order to)\b", re.IGNORECASE)
_VAGUE = re.compile(r"\b(here|there)\b", re.IGNORECASE)


@dataclass
class NarrationLabel:
    what: bool
    where: bool
    why: bool
    utterance: str
    source: str = "deterministic"


def utterance_for(words, t: float, pre: float, post: float) -> str:
    start, end = t - pre, t + post
    chosen = [word.word for word in words if word.end >= start and word.start <= end]
    return " ".join(chosen).strip()


def _deterministic(action: Action, utterance: str) -> NarrationLabel:
    text = utterance or ""
    target = (action.target or "").strip()
    has_what = bool(_WHAT.search(text))
    mentions_target = len(target) > 2 and target.casefold() in text.casefold()
    has_landmark = bool(_WHERE.search(text)) or mentions_target
    if _VAGUE.search(text) and not has_landmark:
        has_where = False
    else:
        has_where = has_landmark
    has_why = bool(_WHY.search(text))
    return NarrationLabel(what=has_what, where=has_where, why=has_why, utterance=text)


def _remote(endpoint: str, action: Action, utterance: str, rules: RuleSet) -> NarrationLabel | None:
    payload = json.dumps(
        {
            "model": rules.get("vision_llm.model", ""),
            "action": action.to_dict(),
            "utterance": utterance,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            body = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    if not isinstance(body, dict):
        return None
    return NarrationLabel(
        what=bool(body.get("what")),
        where=bool(body.get("where")),
        why=bool(body.get("why")),
        utterance=utterance,
        source="llm",
    )


def classify_utterance(action: Action, utterance: str, rules: RuleSet) -> NarrationLabel:
    endpoint = str(rules.get("narration.endpoint", "") or "")
    if endpoint:
        remote = _remote(endpoint, action, utterance, rules)
        if remote is not None:
            return remote
    return _deterministic(action, utterance)
