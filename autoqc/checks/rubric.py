"""Rubric findings that are not one of the 14 checklist bands."""

from __future__ import annotations

import re

from autoqc.audio.transcribe import Transcript
from autoqc.checks.duration import duration_status
from autoqc.checks.textutil import app_set, canon_app, ideas_kept
from autoqc.context import ReviewContext
from autoqc.models import Finding
from autoqc.timefmt import fmt_ts


def rubric_findings(ctx: ReviewContext) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(_files(ctx))
    findings.extend(_duration(ctx))
    findings.extend(_restricted(ctx))
    findings.extend(_app_list(ctx))
    findings.extend(_accessibility(ctx))
    findings.extend(_banned_surfaces(ctx))
    findings.extend(_resubmit(ctx))
    findings.extend(_pacing(ctx))
    findings.extend(_taskrecorder_mismatch(ctx))
    return findings


def _files(ctx: ReviewContext) -> list[Finding]:
    found = []
    for issue in ctx.submission.issues:
        lowered = issue.lower()
        if "metadata" in lowered and "missing" in lowered:
            if ctx.submission.taskrecorder is not None:
                found.append(
                    Finding(
                        id="missing-metadata",
                        category="metadata_missing",
                        action="FIX + APPROVE",
                        confidence=0.9,
                        summary="Metadata.rtf is missing. A corrected file can be generated.",
                        drives_verdict=True,
                        checklist_item=1,
                    )
                )
            else:
                found.append(_send("missing-files", issue))
            continue
        if any(token in lowered for token in ("missing", "unreadable", "not a readable")):
            found.append(_send("missing-files", issue))
    return found


def _duration(ctx: ReviewContext) -> list[Finding]:
    duration = float(ctx.submission.media.duration or 0.0)
    status = duration_status(duration, ctx.rules)
    if status == "out_of_range" and duration > 0:
        return [
            _send(
                "duration",
                f"Video duration {fmt_ts(duration)} is outside 15:00–54:59.",
            )
        ]
    if status == "long":
        apps = {window.app for obs in ctx.observations for window in obs.windows if window.app}
        max_actions = int(ctx.rules.get("low_complexity.max_actions", 8))
        if len(apps) <= 1 and len(ctx.actions) <= max_actions:
            return [
                Finding(
                    id="long-simple",
                    category="long_simple_video",
                    action="NONE",
                    confidence=0.7,
                    summary=(
                        f"Video is {fmt_ts(duration)}, single-app, and low complexity. "
                        "That alone is not a deduction."
                    ),
                    drives_verdict=False,
                )
            ]
    return []


def _restricted(ctx: ReviewContext) -> list[Finding]:
    found = []
    for restricted in ctx.rules.restricted_apps:
        canonical = canon_app(restricted.name, ctx.rules)
        stamps = []
        for obs in ctx.observations:
            for window in obs.windows:
                if canon_app(window.app, ctx.rules) == canonical or canonical in window.app.casefold():
                    stamps.append(obs.t)
            if obs.frontmost_app and canon_app(obs.frontmost_app, ctx.rules) == canonical:
                stamps.append(obs.t)
        if not stamps:
            continue
        found.append(
            _send(
                f"restricted-{canonical}",
                (
                    f"{restricted.name} is a Writer Handbook violation ({restricted.prohibited_use}). "
                    f"Seen at {fmt_ts(min(stamps))}."
                ),
            )
        )
    return found


def _app_list(ctx: ReviewContext) -> list[Finding]:
    task = ctx.submission.taskrecorder
    if task is None or not ctx.observations:
        return []
    listed = app_set(task.apps, ctx.rules)
    used: set[str] = set()
    for obs in ctx.observations:
        for window in obs.windows:
            if window.app and not window.is_goal:
                used.add(canon_app(window.app, ctx.rules))
        if obs.frontmost_app:
            used.add(canon_app(obs.frontmost_app, ctx.rules))
    restricted = {canon_app(item.name, ctx.rules) for item in ctx.rules.restricted_apps}
    ignored = {canon_app("Accessibility Inspector", ctx.rules), ""}
    used -= ignored
    extra = sorted(name for name in used - listed if name not in restricted)
    missing = sorted(listed - used)
    locked = "apps" in {item.casefold() for item in ctx.submission.locked_fields}
    action = "INTERNAL_NOTE" if locked else "FIX + APPROVE"
    found = []
    if extra:
        found.append(
            Finding(
                id="unlisted-apps",
                category="unlisted_app",
                action=action,
                confidence=0.78,
                summary="Non-restricted apps used but not listed: " + ", ".join(extra) + ".",
                drives_verdict=True,
            )
        )
    if missing:
        found.append(
            Finding(
                id="unused-apps",
                category="unused_listed_app",
                action=action,
                confidence=0.72,
                summary="Listed apps not seen in the recording: " + ", ".join(missing) + ".",
                drives_verdict=True,
            )
        )
    return found


def _accessibility(ctx: ReviewContext) -> list[Finding]:
    if not ctx.observations:
        return []
    seen = False
    texts = []
    for obs in ctx.observations:
        blob = obs.ocr_text or ""
        for window in obs.windows:
            blob += f" {window.app} {window.title} {window.text}"
            label = f"{window.app} {window.title}".casefold()
            if "accessibility inspector" in label:
                seen = True
        texts.append(re.sub(r"\d{1,2}:\d{2}:\d{2}", "", blob).strip())
    found = []
    if not seen:
        found.append(_send("accessibility-missing", "Accessibility Inspector is not running."))
    if len(ctx.observations) >= 2 and len(set(texts)) <= 1:
        found.append(_send("ui-static", "No UI element changed during the recording."))
    return found


def _banned_surfaces(ctx: ReviewContext) -> list[Finding]:
    found = []
    glimpse_seconds = 0.0
    last_glimpse = None
    for obs in ctx.observations:
        for window in obs.windows:
            blob = f"{window.app} {window.title} {window.text}".casefold()
            slack = "slack" in blob
            if "insightful" in blob or (window.app.casefold() == "studio") or (slack and "odin" in blob):
                found.append(
                    _send(
                        "banned-surface",
                        f"Studio, Insightful, or Odin Slack is on screen at {fmt_ts(obs.t)} ({window.label}).",
                    )
                )
            elif "mercor" in blob or ("odin" in blob and not slack):
                if last_glimpse is None or obs.t - last_glimpse > 2:
                    glimpse_seconds = 0.0
                glimpse_seconds += 1.0
                last_glimpse = obs.t
    limit = float(ctx.rules.get("ui_feedback.mercor_glimpse_max_seconds", 2))
    if glimpse_seconds > limit:
        found.append(
            Finding(
                id="mercor-long",
                category="mercor_visible",
                action="APPROVE_FEEDBACK",
                confidence=0.7,
                summary="Mercor or Odin is visible for longer than a brief glimpse.",
                drives_verdict=True,
            )
        )
    return found


def _resubmit(ctx: ReviewContext) -> list[Finding]:
    prior = ctx.submission.prior
    if ctx.submission.review_number < 2 or prior is None:
        return []
    current_names = set(ctx.submission.zip_inventory.basenames) if ctx.submission.zip_inventory else set()
    prior_names = set(prior.zip_inventory.basenames) if prior.zip_inventory else set()
    current_request = ctx.submission.metadata.request if ctx.submission.metadata else ""
    prior_request = prior.metadata.request if prior.metadata else ""
    current_desc = ctx.submission.taskrecorder.description if ctx.submission.taskrecorder else ""
    prior_desc = prior.taskrecorder.description if prior.taskrecorder else ""
    current_dur = float(ctx.submission.media.duration or 0)
    prior_dur = float(prior.media.duration or 0)
    tolerance = float(ctx.rules.get("workflow.resubmit_duration_tolerance", 0.02))
    duration_same = prior_dur == 0 or abs(current_dur - prior_dur) <= max(1.0, prior_dur * tolerance)
    if current_names == prior_names and current_request.strip() == prior_request.strip() and current_desc.strip() == prior_desc.strip() and duration_same:
        note = ctx.submission.prior_notes or "(no prior note text)"
        return [
            _send(
                "resubmit-unchanged",
                f"Resubmission shows no changes. Original note: {note}",
            )
        ]
    return []


def _pacing(ctx: ReviewContext) -> list[Finding]:
    found = []
    if ctx.actions and ctx.actions[0].t > float(ctx.rules.get("ui_feedback.intro_seconds", 20)):
        found.append(
            Finding(
                id="intro-long",
                category="intro_over_20s",
                action="APPROVE_FEEDBACK",
                confidence=0.8,
                summary=f"The first action is at {fmt_ts(ctx.actions[0].t)}, after a long intro.",
                drives_verdict=True,
            )
        )
    transcript = ctx.transcript if isinstance(ctx.transcript, Transcript) else None
    if transcript and len(transcript.words) >= 2:
        silence = float(ctx.rules.get("ui_feedback.silence_seconds", 45))
        ordered = sorted(transcript.words, key=lambda word: word.start)
        for earlier, later in zip(ordered, ordered[1:]):
            gap = later.start - earlier.end
            if gap > silence:
                found.append(
                    Finding(
                        id="silence",
                        category="silence",
                        action="APPROVE_FEEDBACK",
                        confidence=0.8,
                        summary=f"Narration is silent for {gap:.0f}s at {fmt_ts(earlier.end)}.",
                        drives_verdict=True,
                    )
                )
                break
    clicks = sorted(action for action in ctx.actions if action.kind == "click")
    gap_limit = float(ctx.rules.get("ui_feedback.rushed_click_gap_seconds", 0.4))
    need = int(ctx.rules.get("ui_feedback.rushed_click_min_count", 5))
    streak = 1
    for earlier, later in zip(clicks, clicks[1:]):
        if later.t - earlier.t < gap_limit:
            streak += 1
        else:
            streak = 1
        if streak >= need:
            found.append(
                Finding(
                    id="rushed-clicks",
                    category="rushed_clicks",
                    action="APPROVE_FEEDBACK",
                    confidence=0.75,
                    summary=f"Clicks are rushed around {fmt_ts(later.t)}.",
                    drives_verdict=True,
                )
            )
            break
    inactive = float(ctx.rules.get("ui_feedback.mouse_inactivity_seconds", 30))
    still_since = None
    for obs in ctx.observations:
        if obs.click or obs.mouse_moving:
            still_since = None
            continue
        if still_since is None:
            still_since = obs.t
        elif obs.t - still_since > inactive:
            found.append(
                Finding(
                    id="mouse-idle",
                    category="mouse_inactivity",
                    action="INTERNAL_NOTE",
                    confidence=0.7,
                    summary=f"Mouse inactivity from {fmt_ts(still_since)} to {fmt_ts(obs.t)}.",
                    drives_verdict=True,
                )
            )
            break
    return found


def _taskrecorder_mismatch(ctx: ReviewContext) -> list[Finding]:
    task = ctx.submission.taskrecorder
    studio = ctx.submission.studio
    if task is None or studio is None or not studio.goal.strip() or not task.description.strip():
        return []
    recall = float(ctx.rules.get("key_ideas.recall_min", 0.85))
    if ideas_kept(studio.goal, task.description, recall):
        return []
    return [
        Finding(
            id="taskrecorder-mismatch",
            category="taskrecorder_mismatch",
            action="FIX + APPROVE",
            confidence=0.8,
            summary=(
                "TaskRecorder description does not match the Studio goal. "
                "Once Metadata matches the Studio goal, check the Edge Case box. Internal note only."
            ),
            drives_verdict=True,
            checklist_item=1,
        )
    ]


def _send(identifier: str, summary: str) -> Finding:
    return Finding(
        id=identifier,
        category=identifier,
        action="SEND BACK",
        confidence=0.9,
        summary=summary,
        drives_verdict=True,
    )
