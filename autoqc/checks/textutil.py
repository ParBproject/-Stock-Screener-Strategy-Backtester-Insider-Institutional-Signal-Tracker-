"""Text comparisons used by the metadata check and later draft copy."""

from __future__ import annotations

import re

from autoqc.rules.loader import RuleSet

_STOP = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "to",
    "of",
    "for",
    "in",
    "on",
    "with",
    "this",
    "that",
    "is",
    "it",
    "be",
    "as",
    "at",
    "by",
    "from",
    "into",
    "using",
    "use",
    "via",
    "please",
}


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def word_for_word(left: str, right: str) -> bool:
    return normalize_ws(left) == normalize_ws(right)


def content_tokens(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9']+", (text or "").lower())
    return [word for word in words if word not in _STOP and len(word) > 1]


def numbers_in(text: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?", text or "")


def quoted_strings(text: str) -> list[str]:
    return re.findall(r'"([^"]+)"', text or "")


def key_idea_recall(reference: str, candidate: str) -> float:
    """Share of reference content-words that also appear in the candidate."""
    reference_tokens = list(dict.fromkeys(content_tokens(reference)))
    candidate_tokens = set(content_tokens(candidate))
    if not reference_tokens:
        return 1.0 if word_for_word(reference, candidate) else 0.0
    hits = sum(1 for token in reference_tokens if token in candidate_tokens)
    return hits / len(reference_tokens)


def ideas_kept(reference: str, candidate: str, recall_min: float) -> bool:
    if key_idea_recall(reference, candidate) < recall_min:
        return False
    if numbers_in(reference) != numbers_in(candidate):
        return False
    return all(phrase in (candidate or "") for phrase in quoted_strings(reference))


def normalize_app(name: str) -> str:
    return re.sub(r"\s+", " ", name or "").strip().casefold()


def canon_app(name: str, rules: RuleSet) -> str:
    normalized = normalize_app(name)
    groups = rules.get("app_aliases", []) or []
    for group in groups:
        forms = [normalize_app(str(item)) for item in group]
        if normalized in forms:
            return forms[0]
    return normalized


def app_set(names: list[str], rules: RuleSet) -> set[str]:
    return {canon_app(name, rules) for name in names if normalize_app(name)}
