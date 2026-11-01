"""Checklist item 9: disallowed AI.

Unclear use, such as a passive enhancement, is an escalate candidate.
It does not get a silent band.
"""

from __future__ import annotations

from autoqc.audio.transcribe import Transcript
from autoqc.checks.common import TITLES, finish
from autoqc.context import ReviewContext
from autoqc.models import CheckResult, Evidence, Finding


def _corpus(ctx: ReviewContext) -> list[tuple[float, str]]:
    rows: list[tuple[float, str]] = []
    for obs in ctx.observations:
        chunks = [obs.ocr_text]
        chunks.extend(f"{window.app} {window.title} {window.text}" for window in obs.windows)
        text = " ".join(chunk for chunk in chunks if chunk).strip()
        if text:
            rows.append((obs.t, text))
    transcript = ctx.transcript
    if isinstance(transcript, Transcript) and transcript.text:
        rows.append((transcript.words[0].start if transcript.words else 0.0, transcript.text))
    return rows


def _contains(text: str, phrase: str) -> bool:
    return phrase.casefold() in text.casefold()


def score_ai_use(ctx: ReviewContext) -> CheckResult:
    rows = _corpus(ctx)
    if not rows and not ctx.observations:
        return finish(
            CheckResult(
                item=9,
                key="ai_use",
                title=TITLES[9],
                band=None,
                confidence=0.34,
                summary="No screen text or transcript was available to check AI use.",
            ),
            ctx.rules,
        )
    disallowed = [str(item) for item in ctx.rules.get("ai.disallowed_phrases", [])]
    uncertain = [str(item) for item in ctx.rules.get("ai.uncertain_phrases", [])]
    allowed = [item.name for item in ctx.rules.allowed_ai]
    coding = {str(item).casefold() for item in ctx.rules.get("ai.coding_task_types", [])}
    task_is_code = ctx.submission.task_type.casefold() in coding

    bad: list[tuple[float, str]] = []
    soft: list[tuple[float, str]] = []
    ok: list[tuple[float, str]] = []
    for stamp, text in rows:
        folded = text.casefold()
        for phrase in disallowed:
            if _contains(folded, phrase):
                bad.append((stamp, phrase))
        if "ai overview" in folded and "follow" in folded:
            bad.append((stamp, "AI Overview follow-up"))
        for phrase in uncertain:
            if _contains(folded, phrase):
                soft.append((stamp, phrase))
        for phrase in allowed:
            if _contains(folded, phrase):
                if phrase.casefold() == "code assistant" and not task_is_code:
                    bad.append((stamp, phrase))
                else:
                    ok.append((stamp, phrase))
        if task_is_code and ("code completion" in folded or "autocomplete" in folded):
            ok.append((stamp, "autocomplete"))

    if bad:
        stamp, phrase = bad[0]
        return finish(
            CheckResult(
                item=9,
                key="ai_use",
                title=TITLES[9],
                band=3,
                confidence=0.88,
                summary=f"Disallowed AI is in use ({phrase}).",
                evidence=[Evidence(text=phrase, start=stamp)],
                details={"phrase": phrase, "escalate": False},
            ),
            ctx.rules,
        )
    if soft and not ok:
        stamp, phrase = soft[0]
        finding = Finding(
            id="ai-uncertain",
            category="unclear_ai",
            action="ESCALATE",
            confidence=0.74,
            summary=f"AI use is unclear ({phrase}). A human should look before a band is chosen.",
            evidence=[Evidence(text=phrase, start=stamp)],
            checklist_item=9,
            drives_verdict=True,
            data={"phrase": phrase},
        )
        ctx.findings.append(finding)
        return CheckResult(
            item=9,
            key="ai_use",
            title=TITLES[9],
            band=None,
            confidence=0.74,
            summary=finding.summary,
            evidence=list(finding.evidence),
            drives_verdict=True,
            details={"escalate": True, "phrase": phrase},
        )
    if ok:
        return finish(
            CheckResult(
                item=9,
                key="ai_use",
                title=TITLES[9],
                band=2,
                confidence=0.8,
                summary="Only allowed AI is visible (" + ok[0][1] + ").",
                evidence=[Evidence(text=ok[0][1], start=ok[0][0])],
                details={"escalate": False},
            ),
            ctx.rules,
        )
    return finish(
        CheckResult(
            item=9,
            key="ai_use",
            title=TITLES[9],
            band=1,
            confidence=0.78 if rows else 0.6,
            summary="No AI tool or AI prompt is visible.",
            details={"escalate": False},
        ),
        ctx.rules,
    )
