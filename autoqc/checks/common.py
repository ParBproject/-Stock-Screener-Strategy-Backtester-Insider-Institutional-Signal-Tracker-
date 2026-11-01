"""Shared checklist titles and the confidence gate."""

from __future__ import annotations

from autoqc.models import CheckResult
from autoqc.rules.loader import RuleSet

TITLES: dict[int, str] = {
    1: "Metadata.rtf matches TaskRecorder",
    2: "Working content stays visible",
    3: "Narration says what and where",
    4: "Recording shows the workflow",
    5: "Menu bar clock shows seconds",
    6: "Goal document shown then minimized",
    7: "Typing share",
    8: "Narration understandable at 1x",
    9: "No disallowed AI",
    10: "No PII on screen or in audio",
    11: "Deliverable licensing",
    12: "Profanity",
    13: "English narration and deliverables",
    14: "Epilogue",
}


def finish(check: CheckResult, rules: RuleSet) -> CheckResult:
    """Low-confidence and unscored results never drive the verdict."""
    if check.unscored_reason or check.band is None or check.confidence < rules.low_confidence:
        check.drives_verdict = False
    else:
        check.drives_verdict = True
    return check
