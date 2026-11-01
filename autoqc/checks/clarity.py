"""Checklist item 8: narration is understandable on a first listen at 1x."""

from __future__ import annotations

from autoqc.audio.transcribe import Transcript
from autoqc.checks.common import TITLES, finish
from autoqc.context import ReviewContext
from autoqc.models import CheckResult, Evidence
from autoqc.timefmt import fmt_ts


def _words(ctx: ReviewContext):
    transcript = ctx.transcript
    if isinstance(transcript, Transcript):
        return transcript.words
    return []


def _wpm(words) -> float | None:
    if len(words) < 8:
        return None
    speech = sum(max(0.05, word.end - word.start) for word in words)
    if speech <= 0:
        return None
    return len(words) / (speech / 60.0)


def _low_spans(words, ceiling: float, minimum: float) -> list[tuple[float, float]]:
    spans = []
    start = None
    last_end = None
    for word in words:
        if word.confidence < ceiling:
            if start is None:
                start = word.start
            last_end = word.end
        elif start is not None:
            if last_end is not None and last_end - start >= minimum:
                spans.append((start, last_end))
            start = None
            last_end = None
    if start is not None and last_end is not None and last_end - start >= minimum:
        spans.append((start, last_end))
    return spans


def score_clarity(ctx: ReviewContext) -> CheckResult:
    words = _words(ctx)
    if len(words) < 4:
        return finish(
            CheckResult(
                item=8,
                key="clarity",
                title=TITLES[8],
                band=None,
                confidence=0.32,
                summary="Not enough transcript to judge whether the narration is clear.",
            ),
            ctx.rules,
        )
    clear_at = float(ctx.rules.get("clarity.asr_clear_min_confidence", 0.80))
    flag_at = float(ctx.rules.get("clarity.span_flag_confidence", 0.60))
    wpm_min = float(ctx.rules.get("clarity.wpm_min", 110))
    wpm_max = float(ctx.rules.get("clarity.wpm_max", 190))
    inaudible = float(ctx.rules.get("clarity.inaudible_seconds", 4))
    mean = sum(word.confidence for word in words) / len(words)
    pace = _wpm(words)
    spans = _low_spans(words, flag_at, inaudible)
    flagged = [word for word in words if word.confidence < flag_at]
    problems = []
    if mean < clear_at:
        problems.append(f"mean ASR confidence is {mean:.2f}")
    if spans:
        problems.append(f"{len(spans)} low-confidence span(s) of at least {inaudible:.0f}s")
    if pace is not None and (pace < wpm_min or pace > wpm_max):
        problems.append(f"pace is {pace:.0f} words per minute")
    evidence = [
        Evidence(
            text=f"Low-confidence words from {fmt_ts(word.start)} ({word.word}, {word.confidence:.2f}).",
            start=word.start,
            end=word.end,
        )
        for word in flagged[:6]
    ]
    for start, end in spans:
        evidence.append(Evidence(text="Low-confidence span to replay.", start=start, end=end))
    if problems:
        band = 3
        summary = "Narration likely needs a replay: " + "; ".join(problems) + "."
    else:
        band = 1
        pace_text = f"{pace:.0f} wpm" if pace is not None else "pace not estimated"
        summary = f"Narration looks clear ({mean:.2f} mean confidence, {pace_text})."
        if flagged:
            summary += " A few low-confidence words are flagged for a human listen."
    return finish(
        CheckResult(
            item=8,
            key="clarity",
            title=TITLES[8],
            band=band,
            confidence=0.8,
            summary=summary,
            evidence=evidence,
            details={
                "mean_confidence": round(mean, 4),
                "wpm": None if pace is None else round(pace, 1),
                "low_span_count": len(spans),
                "flagged_words": len(flagged),
            },
        ),
        ctx.rules,
    )
