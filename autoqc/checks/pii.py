"""Checklist item 10: PII on screen or in the narration.

Confident identifiers are band 3. Partial or name-like hits escalate
instead of failing quietly.
"""

from __future__ import annotations

import re

from autoqc.audio.transcribe import Transcript
from autoqc.checks.common import TITLES, finish
from autoqc.context import ReviewContext
from autoqc.models import CheckResult, Evidence, Finding
from autoqc.timefmt import fmt_ts


def _luhn(number: str) -> bool:
    digits = [int(char) for char in number if char.isdigit()]
    if not 13 <= len(digits) <= 16:
        return False
    total = 0
    alternate = False
    for digit in reversed(digits):
        if alternate:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
        alternate = not alternate
    return total % 10 == 0


def _scrub(text: str, rules) -> str:
    cleaned = text
    for skip in rules.pii.get("ignore_contains", []) or []:
        cleaned = re.sub(re.escape(str(skip)), " ", cleaned, flags=re.IGNORECASE)
    return cleaned


def _corpus(ctx: ReviewContext) -> list[tuple[float, str]]:
    rows = []
    for obs in ctx.observations:
        chunks = [obs.ocr_text]
        chunks.extend(f"{window.title} {window.text}" for window in obs.windows)
        text = " ".join(chunk for chunk in chunks if chunk).strip()
        if text:
            rows.append((obs.t, text))
    transcript = ctx.transcript
    if isinstance(transcript, Transcript) and transcript.text:
        stamp = transcript.words[0].start if transcript.words else 0.0
        rows.append((stamp, transcript.text))
    return rows


def score_pii(ctx: ReviewContext) -> CheckResult:
    rows = _corpus(ctx)
    if not rows:
        return finish(
            CheckResult(
                item=10,
                key="pii",
                title=TITLES[10],
                band=None,
                confidence=0.34,
                summary="No screen text or transcript was available to check for PII.",
            ),
            ctx.rules,
        )
    patterns = ctx.rules.pii.get("patterns", {}) or {}
    uncertain = ctx.rules.pii.get("uncertain_patterns", {}) or {}
    hard: list[tuple[float, str, str]] = []
    soft: list[tuple[float, str, str]] = []
    for stamp, raw in rows:
        text = _scrub(raw, ctx.rules)
        for name, pattern in patterns.items():
            try:
                match = re.search(str(pattern), text)
            except re.error:
                continue
            if match:
                hard.append((stamp, str(name), match.group(0)))
        for match in re.finditer(r"\b(?:\d[ -]?){13,16}\b", text):
            if _luhn(match.group(0)):
                hard.append((stamp, "credit_card", match.group(0)))
        for name, pattern in uncertain.items():
            try:
                match = re.search(str(pattern), text)
            except re.error:
                continue
            if match:
                soft.append((stamp, str(name), match.group(0)))

    if hard:
        stamp, name, value = hard[0]
        return finish(
            CheckResult(
                item=10,
                key="pii",
                title=TITLES[10],
                band=3,
                confidence=0.9,
                summary=f"PII is visible ({name}).",
                evidence=[Evidence(text=f"{name} at {fmt_ts(stamp)}.", start=stamp)],
                details={"kind": name, "escalate": False},
            ),
            ctx.rules,
        )
    if soft:
        stamp, name, _value = soft[0]
        finding = Finding(
            id="pii-uncertain",
            category="unclear_pii",
            action="ESCALATE",
            confidence=0.73,
            summary=f"Possible PII ({name}) needs a human before it is treated as a failure.",
            evidence=[Evidence(text=name, start=stamp)],
            checklist_item=10,
            drives_verdict=True,
        )
        ctx.findings.append(finding)
        return CheckResult(
            item=10,
            key="pii",
            title=TITLES[10],
            band=None,
            confidence=0.73,
            summary=finding.summary,
            evidence=list(finding.evidence),
            drives_verdict=True,
            details={"escalate": True, "kind": name},
        )
    return finish(
        CheckResult(
            item=10,
            key="pii",
            title=TITLES[10],
            band=1,
            confidence=0.8,
            summary="No PII pattern was found on screen or in the narration.",
            details={"escalate": False},
        ),
        ctx.rules,
    )
