"""Studio feedback, send-back, internal notes, Slack DM, and growth notes."""

from __future__ import annotations

from dataclasses import dataclass, field

from autoqc.checks.textutil import ideas_kept
from autoqc.ingest.parsers import render_metadata_rtf
from autoqc.ingest.submission import Submission
from autoqc.models import CheckResult
from autoqc.rules.engine import Decision
from autoqc.rules.loader import RuleSet
from autoqc.timefmt import fmt_ts


@dataclass
class DraftBundle:
    studio_feedback: str = ""
    send_back: str = ""
    internal_notes: str = ""
    slack_dm: str = ""
    growth_notes: str = ""
    corrected_metadata_rtf: str | None = None
    rename_suggestions: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict[str, str]:
        return {
            "studio_feedback": self.studio_feedback,
            "send_back": self.send_back,
            "internal_notes": self.internal_notes,
            "slack_dm": self.slack_dm,
            "growth_notes": self.growth_notes,
        }


def _correction(submission: Submission, rules: RuleSet) -> tuple[str, list[str], bool] | None:
    task = submission.taskrecorder
    if task is None or not task.description.strip():
        return None
    studio = submission.studio.goal if submission.studio else ""
    recall = float(rules.get("key_ideas.recall_min", 0.85))
    mismatch = bool(studio) and not ideas_kept(studio, task.description, recall)
    if mismatch:
        return studio, list(task.apps), True
    return task.description, list(task.apps), False


def compose_drafts(
    decision: Decision,
    checks: list[CheckResult],
    submission: Submission,
    rules: RuleSet,
) -> DraftBundle:
    bundle = DraftBundle()
    by_key = {check.key: check for check in checks}
    correction = _correction(submission, rules)
    metadata = by_key.get("metadata")
    needs_metadata_fix = (metadata is not None and metadata.band == 3 and metadata.drives_verdict) or any(
        "Metadata.rtf is missing" in reason or "TaskRecorder description does not match" in reason
        for reason in decision.reasons
    )
    if needs_metadata_fix and correction is not None:
        request, apps, mismatch = correction
        bundle.corrected_metadata_rtf = render_metadata_rtf(request, apps)
        if mismatch:
            bundle.studio_feedback = (
                "Draft only. Nothing has been sent.\n\n"
                "Metadata.rtf should match the approved Studio goal. I attached a corrected file. "
                "The TaskRecorder description does not match that goal, so this stays a fix on the "
                "reviewer side rather than a send-back. Please check the Edge Case box."
            )
            bundle.internal_notes = (
                "Edge case: TaskRecorder description does not match the Studio goal, and the "
                "corrected Metadata.rtf matches the Studio goal. Check the Edge Case checkbox."
            )
        else:
            bundle.studio_feedback = (
                "Draft only. Nothing has been sent.\n\n"
                "Metadata.rtf did not match the TaskRecorder description. The corrected file uses "
                "that description word for word and lists the same apps under Task Description and "
                "TOPOLOGY. Please replace Metadata.rtf. This is not a send-back for metadata alone."
            )
            bundle.slack_dm = (
                "Draft only. Nothing has been sent.\n\n"
                "Hi — the Metadata.rtf Request didn't match your TaskRecorder description, so I "
                "drafted a corrected file. Apps in TOPOLOGY are now: "
                + (", ".join(apps) or "(none)")
                + ". I'm not sending the task back for the metadata alone."
            )
    workflow = by_key.get("workflow")
    if workflow is not None:
        bundle.rename_suggestions = list(workflow.details.get("near_misses") or [])

    lines = ["Draft only. Nothing has been sent.", ""]
    for check in checks:
        if check.item is None or not (2 <= check.item <= 13) or check.band != 3:
            continue
        if not check.drives_verdict:
            continue
        lines.append(f"- Item {check.item} ({check.title}): {check.summary}")
        for evidence in check.evidence[:4]:
            when = ""
            if evidence.start is not None:
                when = fmt_ts(evidence.start)
                if evidence.end is not None and evidence.end != evidence.start:
                    when += f"–{fmt_ts(evidence.end)}"
                when = f" [{when}]"
            lines.append(f"  {evidence.text}{when}")
    for reason in decision.reasons:
        if reason not in "\n".join(lines):
            lines.append(f"- {reason}")
    if decision.action in {"SEND BACK", "REJECT"}:
        bundle.send_back = "\n".join(lines).strip() + "\n"

    extra_internal = list(decision.internal_notes)
    if bundle.internal_notes:
        extra_internal.insert(0, bundle.internal_notes)
    if extra_internal:
        bundle.internal_notes = "Draft only. Nothing has been sent.\n\n" + "\n".join(
            f"- {note}" for note in extra_internal
        )

    growth = list(decision.growth)
    narration = by_key.get("narration")
    if narration is not None and narration.band == 2:
        growth.append("Narration usually says what and where. Adding why on the important steps would help.")
    if growth:
        bundle.growth_notes = "Draft only. Nothing has been sent.\n\n" + "\n".join(f"- {note}" for note in growth)

    if decision.feedback and decision.action == "APPROVE":
        feedback = "Draft only. Nothing has been sent.\n\nOptional feedback:\n" + "\n".join(
            f"- {note}" for note in decision.feedback
        )
        bundle.studio_feedback = (bundle.studio_feedback + "\n\n" + feedback).strip() if bundle.studio_feedback else feedback
    elif decision.feedback and decision.action == "FIX + APPROVE" and bundle.studio_feedback:
        bundle.studio_feedback += "\n\nOptional feedback:\n" + "\n".join(f"- {note}" for note in decision.feedback)

    if decision.action == "ESCALATE":
        bundle.internal_notes = (
            (bundle.internal_notes + "\n\n") if bundle.internal_notes else "Draft only. Nothing has been sent.\n\n"
        ) + "Escalate. Suggested channel: #odin-reviewers-hub.\n" + "\n".join(f"- {reason}" for reason in decision.reasons)
    return bundle
