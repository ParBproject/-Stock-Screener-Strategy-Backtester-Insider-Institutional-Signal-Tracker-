"""Checklist item 12: profanity said, typed, or shown."""

from __future__ import annotations

import re

from autoqc.audio.transcribe import Transcript
from autoqc.checks.common import TITLES, finish
from autoqc.context import ReviewContext
from autoqc.models import CheckResult, Evidence
from autoqc.timefmt import fmt_ts


def _hits(text: str, terms) -> list:
    found = []
    for term in terms:
        if re.search(rf"\b{re.escape(term.term)}\b", text or "", flags=re.IGNORECASE):
            found.append(term)
    return found


def score_profanity(ctx: ReviewContext) -> CheckResult:
    terms = ctx.rules.profanity
    transcript = ctx.transcript if isinstance(ctx.transcript, Transcript) else None
    said = []
    if transcript:
        for word in transcript.words:
            for term in _hits(word.word, terms):
                said.append((word.start, term, word.word))
    typed = []
    shown = []
    for obs in ctx.observations:
        for window in obs.windows:
            blob = f"{window.app} {window.title} {window.text}"
            matches = _hits(blob, terms)
            for term in matches:
                row = (obs.t, term, window.label or window.app)
                if window.is_content:
                    typed.append(row)
                else:
                    shown.append(row)
    major_shown = [row for row in shown if row[1].severity == "major"]
    minor_shown = [row for row in shown if row[1].severity != "major"]
    evidence: list[Evidence] = []
    if said or typed or major_shown:
        band = 3
        if said:
            summary = "Profanity is in the narration."
        elif typed:
            summary = "Profanity is typed in the working document."
        else:
            summary = "Major profanity is on screen."
        for start, term, label in (said + typed + major_shown)[:6]:
            evidence.append(
                Evidence(
                    text=f"{term.severity} term at {fmt_ts(start)} ({label}).",
                    start=start,
                )
            )
        confidence = 0.9
    elif minor_shown:
        band = 2
        summary = "Minor profanity is on screen but not said or typed by the writer."
        start, term, label = minor_shown[0]
        evidence.append(Evidence(text=f"On screen in {label}, not in the narration.", start=start))
        confidence = 0.86
    else:
        band = 1
        summary = "No profanity in the narration or on screen."
        confidence = 0.8 if (transcript and transcript.words) or ctx.observations else 0.55
    return finish(
        CheckResult(
            item=12,
            key="profanity",
            title=TITLES[12],
            band=band,
            confidence=confidence,
            summary=summary,
            evidence=evidence,
            details={
                "said": len(said),
                "typed": len(typed),
                "on_screen": len(shown),
            },
        ),
        ctx.rules,
    )
