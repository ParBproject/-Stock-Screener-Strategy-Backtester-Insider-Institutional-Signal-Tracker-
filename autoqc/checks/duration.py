"""Recording length. Outside 15:00–54:59 is a send-back once the rubric runs."""

from __future__ import annotations

from autoqc.rules.loader import RuleSet
from autoqc.timefmt import fmt_ts


def duration_status(duration: float, rules: RuleSet) -> str:
    """``in_range``, ``long`` (50:59–54:59), or ``out_of_range``.

    The maximum is the end of the 54:59 second, so a probe value under 55:00
    is still inside the window.
    """
    low = float(rules.get("video.min_seconds", 900))
    high = float(rules.get("video.max_seconds", 3299))
    long_at = float(rules.get("video.long_notice_seconds", 3059))
    if duration < low or duration >= high + 1:
        return "out_of_range"
    if duration >= long_at:
        return "long"
    return "in_range"


def duration_report(duration: float, rules: RuleSet) -> dict:
    status = duration_status(duration, rules)
    return {
        "duration_seconds": duration,
        "duration_hms": fmt_ts(duration),
        "duration_status": status,
        "min_seconds": float(rules.get("video.min_seconds", 900)),
        "max_seconds": float(rules.get("video.max_seconds", 3299)),
        "long_notice_seconds": float(rules.get("video.long_notice_seconds", 3059)),
    }
