"""Checklist item 7: typing share. The computed ratio is authoritative."""

from __future__ import annotations

from autoqc.checks.common import TITLES, finish
from autoqc.context import ReviewContext
from autoqc.models import CheckResult, Evidence
from autoqc.timefmt import fmt_ts
from autoqc.vision.activity import frame_intervals, typing_share


def relaxed_cap(task_type: str, rules) -> float:
    names = {str(item).casefold() for item in rules.get("typing.relaxed_task_types", [])}
    if task_type.casefold() in names:
        return float(rules.get("typing.max_share_coding_writing", 0.35))
    return float(rules.get("typing.max_share", 0.25))


def band_for_share(share: float, cap: float) -> int:
    if share <= cap + 1e-12:
        return 1
    return 3


def exactly_at_cap(share: float, cap: float) -> bool:
    """True when the reported percent rounds to the cap (optional feedback, still band 1)."""
    return round(share * 100, 2) == round(cap * 100, 2)


def score_typing(ctx: ReviewContext) -> CheckResult:
    cap = relaxed_cap(ctx.submission.task_type, ctx.rules)
    pairs = [(frame.t, frame.rgb) for frame in ctx.frames]
    intervals = frame_intervals(pairs, ctx.rules)
    if not intervals:
        return finish(
            CheckResult(
                item=7,
                key="typing",
                title=TITLES[7],
                band=None,
                confidence=0.34,
                summary="Not enough frames to compute a typing share.",
                details={"share": None, "cap": cap, "task_type": ctx.submission.task_type},
            ),
            ctx.rules,
        )

    share, typing_seconds, compared = typing_share(intervals)
    band = band_for_share(share, cap)
    at_cap = exactly_at_cap(share, cap)
    percent = share * 100
    cap_percent = cap * 100
    if band == 1:
        summary = f"Typing share is {percent:.2f}% (cap {cap_percent:.2f}%)."
    else:
        summary = f"Typing share is {percent:.2f}%, above the {cap_percent:.2f}% cap."

    segments = [row for row in intervals if row["typing"]]
    evidence = [
        Evidence(
            text=(
                f"{typing_seconds:.2f}s of typing across {compared:.2f}s of compared frames "
                f"({percent:.2f}%)."
            )
        )
    ]
    if segments:
        evidence.append(
            Evidence(
                text="Typing detected",
                start=segments[0]["start"],
                end=segments[-1]["end"],
            )
        )
    longest = _longest_run(intervals)
    return finish(
        CheckResult(
            item=7,
            key="typing",
            title=TITLES[7],
            band=band,
            confidence=0.97,
            summary=summary,
            evidence=evidence,
            details={
                "share": share,
                "percent": round(percent, 4),
                "cap": cap,
                "exactly_at_cap": at_cap,
                "typing_seconds": typing_seconds,
                "compared_seconds": compared,
                "task_type": ctx.submission.task_type,
                "longest_segment_seconds": longest,
                "longest_segment_label": fmt_ts(longest),
                "intervals": [
                    {
                        "start": row["start"],
                        "end": row["end"],
                        "typing": row["typing"],
                        "changed_pixels": row["changed_pixels"],
                    }
                    for row in intervals
                ],
            },
        ),
        ctx.rules,
    )


def _longest_run(intervals: list[dict]) -> float:
    best = 0.0
    current = 0.0
    for row in intervals:
        if row["typing"]:
            current += float(row["dt"])
            best = max(best, current)
        else:
            current = 0.0
    return best
