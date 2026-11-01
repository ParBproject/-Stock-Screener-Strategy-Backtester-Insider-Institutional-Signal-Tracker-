"""Phase 5: action rubric, drafts, and JSON export."""

from __future__ import annotations

import json
from pathlib import Path

from autoqc.checks.workflow import score_workflow
from autoqc.cli import main
from autoqc.drafts.compose import compose_drafts
from autoqc.ingest.parsers import MetadataDoc, StudioDoc, TaskRecorderDoc, ZipInventory
from autoqc.ingest.submission import Submission
from autoqc.models import CheckResult, Finding, FrameObservation, WindowBox
from autoqc.rules.engine import choose_action
from autoqc.rules.loader import load_rules
from tests.autoqc.support import make_context, media, paint_menu_clock, solid, write_bundle


def _check(item: int, band: int | None, *, key: str | None = None, confidence: float = 0.9, drives: bool = True, **details) -> CheckResult:
    return CheckResult(
        item=item,
        key=key or f"item-{item}",
        title=f"item {item}",
        band=band,
        confidence=confidence,
        summary=f"item {item} band {band}",
        drives_verdict=drives,
        details=details,
    )


def _submission(review_number: int = 1, duration: float = 1200) -> Submission:
    return Submission(
        root=Path("."),
        media=media(duration),
        review_number=review_number,
        taskrecorder=TaskRecorderDoc("Export the budget.pdf from Numbers", ["Numbers"], "mem"),
        studio=StudioDoc("Export the budget.pdf from Numbers", None),
        metadata=MetadataDoc(
            request="Export the budget.pdf from Numbers",
            task_description="",
            task_description_apps=["Numbers"],
            topology_apps=["Numbers"],
            apps=["Numbers"],
            plain_text="",
        ),
    )


def test_priority_and_low_confidence():
    rules = load_rules()
    submission = _submission()
    metadata = _check(1, 3, key="metadata")
    only_meta = choose_action([metadata], [], submission, rules)
    assert only_meta.action == "FIX + APPROVE"
    drafts = compose_drafts(only_meta, [metadata], submission, rules)
    assert drafts.corrected_metadata_rtf is not None
    assert "Export the budget.pdf from Numbers" in drafts.corrected_metadata_rtf
    assert "not sending the task back" in drafts.slack_dm
    assert "word for word" in drafts.studio_feedback

    send = choose_action([metadata, _check(2, 3, key="visibility")], [], submission, rules)
    assert send.action == "SEND BACK"
    assert compose_drafts(send, [metadata, _check(2, 3, key="visibility")], submission, rules).send_back

    quiet = choose_action([_check(2, 3, confidence=0.4, drives=False, key="visibility")], [], submission, rules)
    assert quiet.action == "APPROVE"
    assert quiet.needs_human

    escalate = Finding(
        id="ai",
        category="unclear_ai",
        action="ESCALATE",
        confidence=0.74,
        summary="AI use is unclear.",
        drives_verdict=True,
        checklist_item=9,
    )
    assert choose_action([_check(2, 3)], [escalate], submission, rules).action == "ESCALATE"

    third = _submission(review_number=3)
    rejected = choose_action([_check(2, 3)], [], third, rules)
    assert rejected.action == "REJECT"
    assert "Review #3" in rejected.reasons[0]


def test_rubric_signals():
    rules = load_rules()
    short = make_context(duration=100)
    short.submission.issues.append("missing deliverables.zip")
    from autoqc.checks.rubric import rubric_findings

    kinds = {item.action for item in rubric_findings(short)}
    assert "SEND BACK" in kinds

    banned = make_context(duration=1200)
    banned.observations = [
        FrameObservation(
            t=1,
            width=10,
            height=10,
            dock_visible=True,
            dock_position="bottom",
            frontmost_app="Slack",
            frontmost_title="odin",
            windows=[
                WindowBox("Slack", "odin-reviewers", "slack", 0, 0, 10, 10, 1, text="Odin Slack huddle")
            ],
            cursor=None,
            cursor_default=None,
            mouse_moving=False,
            click=False,
            click_target=None,
            ocr_text="Odin Slack",
            wallpaper_default=True,
        )
    ]
    assert any(item.action == "SEND BACK" and "Odin Slack" in item.summary for item in rubric_findings(banned))

    torrent = make_context(duration=1200)
    torrent.observations = [
        FrameObservation(
            t=2,
            width=10,
            height=10,
            dock_visible=True,
            dock_position="bottom",
            frontmost_app="uTorrent",
            frontmost_title="download",
            windows=[WindowBox("uTorrent", "download", "ut", 0, 0, 10, 10, 1, text="")],
            cursor=None,
            cursor_default=None,
            mouse_moving=False,
            click=False,
            click_target=None,
            ocr_text="",
            wallpaper_default=True,
        )
    ]
    assert any("uTorrent" in item.summary for item in rubric_findings(torrent))

    glimpse = make_context(duration=1200)
    glimpse.observations = [
        FrameObservation(
            t=1,
            width=10,
            height=10,
            dock_visible=True,
            dock_position="bottom",
            frontmost_app="Safari",
            frontmost_title="home",
            windows=[WindowBox("Safari", "home", "s", 0, 0, 10, 10, 1, text="mercor homepage")],
            cursor=None,
            cursor_default=None,
            mouse_moving=False,
            click=False,
            click_target=None,
            ocr_text="mercor",
            wallpaper_default=True,
        )
    ]
    assert not any(item.category == "mercor_visible" for item in rubric_findings(glimpse))


def test_filename_near_miss_is_a_fix():
    rules = load_rules()
    ctx = make_context(duration=1200)
    ctx.submission.taskrecorder = TaskRecorderDoc("1. Export budget.pdf", ["Numbers"], "mem")
    ctx.submission.studio = StudioDoc("Export budget.pdf", None)
    ctx.submission.zip_inventory = ZipInventory(entries=["budgett.pdf"], basenames=["budgett.pdf"])
    ctx.observations = [
        FrameObservation(
            t=0,
            width=10,
            height=10,
            dock_visible=True,
            dock_position="bottom",
            frontmost_app="Numbers",
            frontmost_title="budget.pdf",
            windows=[
                WindowBox("Numbers", "budget.pdf", "n", 0, 0, 10, 10, 1, is_content=True, text="Export budget.pdf")
            ],
            cursor=None,
            cursor_default=None,
            mouse_moving=False,
            click=False,
            click_target=None,
            ocr_text="Export budget.pdf",
            wallpaper_default=True,
        )
    ]
    workflow = score_workflow(ctx)
    assert workflow.band == 1
    assert workflow.details["near_misses"]
    decision = choose_action([workflow], [], ctx.submission, rules)
    assert decision.action == "FIX + APPROVE"
    drafts = compose_drafts(decision, [workflow], ctx.submission, rules)
    assert drafts.rename_suggestions[0]["actual"] == "budgett.pdf"


def test_typing_cap_feedback_does_not_send_back():
    rules = load_rules()
    typing = _check(7, 1, key="typing", exactly_at_cap=True, longest_segment_seconds=10)
    decision = choose_action([typing], [], _submission(), rules)
    assert decision.action == "APPROVE"
    assert any("cap" in note for note in decision.feedback)


def test_cli_exports_action_and_keeps_human_gate(tmp_path: Path):
    rules = load_rules()
    frames = []
    for stamp in (0, 1, 2):
        image = solid(180, 80)
        paint_menu_clock(image, "09:15:07", rules)
        frames.append((float(stamp), image))
    folder = tmp_path / "submission"
    write_bundle(
        folder,
        frames,
        "Export the quarterly budget as a PDF from Numbers",
        ["Numbers", "Preview"],
        description="Export a different quarterly poster",
    )
    out = tmp_path / "review.json"
    assert main(["review", str(folder), "--json", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["status"] == "complete"
    assert data["recommended_action"] in {"APPROVE", "FIX + APPROVE", "SEND BACK", "REJECT", "ESCALATE"}
    assert data["auto_send"] is False
    assert data["human_review_required"] is True
    assert data["corrected_metadata_rtf"]
    assert "Export a different quarterly poster" in data["corrected_metadata_rtf"] or "quarterly" in data["corrected_metadata_rtf"]
    assert "Draft only" in data["drafts"]["studio_feedback"] or data["drafts"]["send_back"] or data["drafts"]["slack_dm"]
