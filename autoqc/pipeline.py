"""Run the checks that exist so far and export a Review.

The recommended action stays empty until the decision engine is attached.
Nothing in this pipeline sends mail, Slack, or Studio comments.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from autoqc.audio.transcribe import Transcript, load_transcript
from autoqc.checks.ai_use import score_ai_use
from autoqc.checks.clarity import score_clarity
from autoqc.checks.clock import score_clock
from autoqc.checks.duration import duration_report
from autoqc.checks.english import score_english
from autoqc.checks.environment import environment_findings
from autoqc.checks.epilogue import score_epilogue
from autoqc.checks.goal_doc import score_goal_doc
from autoqc.checks.licensing import score_licensing
from autoqc.checks.pii import score_pii
from autoqc.checks.metadata_match import score_metadata
from autoqc.checks.narration import score_narration
from autoqc.checks.profanity import score_profanity
from autoqc.checks.typing_share import score_typing
from autoqc.checks.rubric import rubric_findings
from autoqc.checks.visibility import score_visibility
from autoqc.checks.workflow import score_workflow
from autoqc.drafts.compose import compose_drafts
from autoqc.rules.engine import choose_action
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


def prepare_audio(ctx: ReviewContext) -> None:
    ctx.transcript = load_transcript(ctx.submission, ctx.rules)


def run_checks(ctx: ReviewContext):
    prepare_screen(ctx)
    prepare_audio(ctx)
    return [
        score_metadata(ctx),
        score_visibility(ctx),
        score_narration(ctx),
        score_workflow(ctx),
        score_clock(ctx),
        score_goal_doc(ctx),
        score_typing(ctx),
        score_clarity(ctx),
        score_ai_use(ctx),
        score_pii(ctx),
        score_licensing(ctx),
        score_profanity(ctx),
        score_english(ctx),
        score_epilogue(ctx),
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
    finding_models = [*environment_findings(ctx), *ctx.findings, *rubric_findings(ctx)]
    decision = choose_action(checks, finding_models, submission, rules)
    drafts = compose_drafts(decision, checks, submission, rules)
    findings = [item.to_dict() for item in finding_models]
    stats = duration_report(submission.media.duration, rules)
    stats["frame_count"] = len(ctx.frames)
    stats["scene_times"] = list(submission.scene_times)
    stats["media_source"] = submission.media.source
    by_key = {check.key: check for check in checks}
    typing = by_key.get("typing")
    if typing is not None:
        stats["typing_share"] = typing.details.get("share")
        stats["typing_percent"] = typing.details.get("percent")
        stats["typing_cap"] = typing.details.get("cap")
    narration = by_key.get("narration")
    if narration is not None:
        stats["narration_coverage"] = narration.details.get("where_fraction")
        stats["narration_why_coverage"] = narration.details.get("full_fraction")
    clarity = by_key.get("clarity")
    if clarity is not None:
        stats["wpm"] = clarity.details.get("wpm")
        stats["asr_confidence"] = clarity.details.get("mean_confidence")
    english = by_key.get("english")
    if english is not None:
        stats["language"] = english.details.get("language")
    notices = list(submission.notices)
    if isinstance(ctx.transcript, Transcript) and ctx.transcript.notice:
        notices.append(ctx.transcript.notice)
    needs = list(decision.needs_human)
    for check in checks:
        if not check.drives_verdict and check.band == 3:
            needs.append(
                {
                    "key": check.key,
                    "item": check.item,
                    "summary": check.summary,
                    "confidence": check.confidence,
                }
            )
    return Review(
        submission_path=str(submission.root),
        status="complete",
        recommended_action=decision.action,
        reasons=list(decision.reasons),
        needs_human=needs,
        checks=checks,
        findings=findings,
        stats=stats,
        drafts=drafts.as_dict(),
        notices=notices,
        media=submission.media.to_dict(),
        parsed=_parsed(submission),
        issues=list(submission.issues),
        actions=[action.to_dict() for action in ctx.actions],
        corrected_metadata_rtf=drafts.corrected_metadata_rtf,
        rename_suggestions=drafts.rename_suggestions,
    )
