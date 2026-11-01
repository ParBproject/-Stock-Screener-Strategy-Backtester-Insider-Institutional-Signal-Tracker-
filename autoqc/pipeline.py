"""Run the checks that exist so far and export a Review.

The recommended action stays empty until the decision engine is attached.
Nothing in this pipeline sends mail, Slack, or Studio comments.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from autoqc.checks.clock import score_clock
from autoqc.checks.duration import duration_report
from autoqc.checks.environment import environment_findings
from autoqc.checks.goal_doc import score_goal_doc
from autoqc.checks.metadata_match import score_metadata
from autoqc.checks.typing_share import score_typing
from autoqc.checks.visibility import score_visibility
from autoqc.context import FrameImage, ReviewContext
from autoqc.errors import AutoQCError
from autoqc.ingest.submission import Submission, load_submission
from autoqc.models import Review
from autoqc.rules.loader import RuleSet, load_rules
from autoqc.vision.ocr import build_ocr
from autoqc.vision.screen import build_actions, observe_frames

DRAFTS = {
    "studio_feedback": "",
    "send_back": "",
    "internal_notes": "",
    "slack_dm": "",
    "growth_notes": "",
}


def load_frame_image(path: str, max_width: int) -> np.ndarray:
    try:
        image = Image.open(path).convert("RGB")
    except OSError as exc:
        raise AutoQCError(f"unreadable frame: {path}") from exc
    if max_width and image.width > max_width:
        height = max(1, int(round(image.height * (max_width / image.width))))
        image = image.resize((max_width, height), Image.Resampling.BOX)
    return np.asarray(image)


def build_context(submission: Submission, rules: RuleSet) -> ReviewContext:
    max_width = int(rules.get("ingest.analysis_max_width", 640))
    frames = [
        FrameImage(t=ref.t, path=ref.path, rgb=load_frame_image(ref.path, max_width))
        for ref in submission.frames
    ]
    ocr = build_ocr(str(rules.get("ocr_engine", "auto")))
    return ReviewContext(submission=submission, rules=rules, frames=frames, ocr=ocr)


def prepare_screen(ctx: ReviewContext) -> None:
    goal = ctx.submission.studio.goal if ctx.submission.studio else ""
    ctx.observations = observe_frames(ctx.frames, ctx.rules, ctx.ocr, goal)
    ctx.actions = build_actions(ctx.observations)


def run_checks(ctx: ReviewContext):
    prepare_screen(ctx)
    return [
        score_metadata(ctx),
        score_visibility(ctx),
        score_clock(ctx),
        score_goal_doc(ctx),
        score_typing(ctx),
    ]


def _parsed(submission: Submission) -> dict:
    approved = None
    if submission.idea_first_approved_at is not None:
        approved = submission.idea_first_approved_at.isoformat()
    meta = submission.metadata
    task = submission.taskrecorder
    studio = submission.studio
    inventory = submission.zip_inventory
    return {
        "request": meta.request if meta else "",
        "task_description": meta.task_description if meta else "",
        "metadata_apps": list(meta.apps) if meta else [],
        "topology_apps": list(meta.topology_apps) if meta else [],
        "task_description_apps": list(meta.task_description_apps) if meta else [],
        "taskrecorder_description": task.description if task else "",
        "taskrecorder_apps": list(task.apps) if task else [],
        "studio_goal": studio.goal if studio else "",
        "idea_first_approved_at": approved,
        "deliverable_entries": list(inventory.entries) if inventory else [],
        "deliverable_names": list(inventory.basenames) if inventory else [],
        "task_type": submission.task_type,
        "review_number": submission.review_number,
        "locked_fields": list(submission.locked_fields),
        "prior_notes": submission.prior_notes,
        "has_prior": submission.prior is not None,
    }


def review_submission(folder: Path | str, config_dir: Path | str | None = None) -> Review:
    rules = load_rules(Path(config_dir) if config_dir else None)
    submission = load_submission(Path(folder), rules)
    ctx = build_context(submission, rules)
    checks = run_checks(ctx)
    findings = [item.to_dict() for item in environment_findings(ctx)]
    stats = duration_report(submission.media.duration, rules)
    stats["frame_count"] = len(ctx.frames)
    stats["scene_times"] = list(submission.scene_times)
    stats["media_source"] = submission.media.source
    typing = next((check for check in checks if check.key == "typing"), None)
    if typing is not None:
        stats["typing_share"] = typing.details.get("share")
        stats["typing_percent"] = typing.details.get("percent")
        stats["typing_cap"] = typing.details.get("cap")
    needs = [
        {
            "key": check.key,
            "item": check.item,
            "summary": check.summary,
            "confidence": check.confidence,
        }
        for check in checks
        if not check.drives_verdict
    ]
    return Review(
        submission_path=str(submission.root),
        status="partial",
        recommended_action=None,
        reasons=[],
        needs_human=needs,
        checks=checks,
        findings=findings,
        stats=stats,
        drafts=dict(DRAFTS),
        notices=list(submission.notices),
        media=submission.media.to_dict(),
        parsed=_parsed(submission),
        issues=list(submission.issues),
        actions=[action.to_dict() for action in ctx.actions],
    )
