"""Pick one recommended action. Low-confidence findings never decide it."""

from __future__ import annotations

from dataclasses import dataclass, field

from autoqc.ingest.submission import Submission
from autoqc.models import CheckResult, Finding
from autoqc.rules.loader import RuleSet

RANK = ("ESCALATE", "REJECT", "SEND BACK", "FIX + APPROVE", "APPROVE")


@dataclass
class Decision:
    action: str
    reasons: list[str]
    feedback: list[str] = field(default_factory=list)
    internal_notes: list[str] = field(default_factory=list)
    needs_human: list[dict] = field(default_factory=list)
    growth: list[str] = field(default_factory=list)


def _gate(confidence: float, drives: bool, rules: RuleSet) -> bool:
    return drives and confidence >= rules.low_confidence


def choose_action(
    checks: list[CheckResult],
    findings: list[Finding],
    submission: Submission,
    rules: RuleSet,
) -> Decision:
    buckets: dict[str, list[str]] = {name: [] for name in RANK}
    feedback: list[str] = []
    internal: list[str] = []
    growth: list[str] = []
    human: list[dict] = []

    def add_human(kind: str, summary: str, confidence: float, item: int | None) -> None:
        human.append({"key": kind, "item": item, "summary": summary, "confidence": confidence})

    def consider(action: str, summary: str, confidence: float, drives: bool, item: int | None = None) -> None:
        if not summary:
            return
        if not _gate(confidence, drives, rules):
            add_human(action or "check", summary, confidence, item)
            return
        if action in {"APPROVE_FEEDBACK", "NONE", ""}:
            if action == "APPROVE_FEEDBACK":
                feedback.append(summary)
            return
        if action == "INTERNAL_NOTE":
            internal.append(summary)
            return
        if action == "GROWTH":
            growth.append(summary)
            return
        if action in buckets:
            buckets[action].append(summary)

    for check in checks:
        item = check.item
        if check.unscored_reason:
            if item == 14:
                growth.append(check.unscored_reason)
            continue
        if check.details.get("escalate"):
            consider("ESCALATE", check.summary, check.confidence, check.drives_verdict, item)
            continue
        if not _gate(check.confidence, check.drives_verdict, rules):
            if check.band == 3:
                add_human(check.key, check.summary, check.confidence, item)
            continue
        if item == 1 and check.band == 3:
            consider("FIX + APPROVE", check.summary, check.confidence, True, item)
        elif item is not None and 2 <= item <= 13 and check.band == 3:
            consider("SEND BACK", check.summary, check.confidence, True, item)
        elif item == 14 and check.band == 2:
            growth.append(check.summary)
        elif item == 7 and check.details.get("exactly_at_cap"):
            feedback.append("Typing share is exactly at the cap.")
        if item == 2 and check.details.get("minor_overlap") and check.band == 1:
            feedback.append("Minor overlap only; working content stays visible.")
        if check.key == "workflow":
            for miss in check.details.get("near_misses") or []:
                consider(
                    "FIX + APPROVE",
                    f"Deliverable filename is slightly off: {miss.get('actual')} should be {miss.get('expected')}.",
                    check.confidence,
                    True,
                    4,
                )
        if item == 7 and float(check.details.get("longest_segment_seconds") or 0) > float(
            rules.get("typing.segment_feedback_seconds", 45)
        ):
            feedback.append("One typing segment runs longer than 45 seconds.")

    for finding in findings:
        consider(finding.action, finding.summary, finding.confidence, finding.drives_verdict, finding.checklist_item)

    reject_after = int(rules.get("review.reject_after_review_number", 3))
    if submission.review_number >= reject_after and buckets["SEND BACK"] and not buckets["ESCALATE"]:
        buckets["REJECT"].append(
            f"Review #{submission.review_number} still needs writer changes. "
            + " ".join(buckets["SEND BACK"])
        )

    for action in RANK:
        if buckets[action]:
            return Decision(action, buckets[action], feedback, internal, human, growth)
    return Decision("APPROVE", ["No blocking finding."], feedback, internal, human, growth)
