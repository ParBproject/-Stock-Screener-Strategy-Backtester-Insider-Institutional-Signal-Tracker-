"""Phase 1: parsers, duration, menu-bar clock, typing share, CLI."""

from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from autoqc.checks.clock import score_clock
from autoqc.checks.duration import duration_status
from autoqc.checks.metadata_match import score_metadata
from autoqc.checks.textutil import word_for_word
from autoqc.checks.typing_share import band_for_share, exactly_at_cap, score_typing
from autoqc.cli import main
from autoqc.ingest.frames import extract_video_frames, scene_change_times
from autoqc.ingest.parsers import (
    MetadataDoc,
    TaskRecorderDoc,
    parse_approved_at,
    parse_metadata_file,
    parse_studio_file,
    parse_taskrecorder_file,
    parse_zip,
    render_metadata_rtf,
)
from autoqc.ingest.probe import probe_video
from autoqc.rules.loader import load_rules
from autoqc.vision.font import FONT, draw_text, text_width
from autoqc.vision.ocr import GlyphOcr
from tests.autoqc.support import make_context, paint_menu_clock, solid, write_bundle

ROOT = Path(__file__).resolve().parents[2]


def test_glyph_font_roundtrip():
    ocr = GlyphOcr()
    samples = [
        "".join(FONT),
        "12:34:56",
        "12:34 PM",
        "Preview - Budget.pdf",
        "Accessibility Inspector",
        "Content & Writing",
    ]
    for text in samples:
        image = solid(text_width(text) + 8, 24, (16, 16, 18))
        draw_text(image, 2, 4, text, (255, 255, 255))
        assert ocr.read(image) == text


def test_metadata_rtf_roundtrip(tmp_path: Path):
    request = "Export the quarterly budget as a PDF from Numbers."
    apps = ["Numbers", "Preview"]
    path = tmp_path / "Metadata.rtf"
    path.write_text(render_metadata_rtf(request, apps), encoding="utf-8")
    doc = parse_metadata_file(path)
    assert doc.request == request
    assert set(doc.topology_apps) == set(apps)
    assert set(doc.task_description_apps) == set(apps)
    assert set(doc.apps) == set(apps)


def test_metadata_bands_and_aliases():
    rules = load_rules()
    request = "Export the quarterly budget as a PDF from Numbers"
    apps = ["Numbers", "Preview"]

    def meta(text: str, meta_apps: list[str]):
        return MetadataDoc(
            request=text,
            task_description=text,
            task_description_apps=list(meta_apps),
            topology_apps=list(meta_apps),
            apps=list(meta_apps),
            plain_text=text,
        )

    task = TaskRecorderDoc(description=request, apps=list(apps), source="mem")
    exact = make_context(metadata=meta(request, apps), taskrecorder=task, rules=rules)
    assert score_metadata(exact).band == 1

    softer = "Please export the quarterly budget as a PDF from Numbers today"
    band2 = make_context(metadata=meta(softer, apps), taskrecorder=task, rules=rules)
    result = score_metadata(band2)
    assert result.band == 2
    assert result.details["ideas_kept"] is True
    assert result.details["word_for_word"] is False

    cased = make_context(
        metadata=meta(request.lower(), apps),
        taskrecorder=task,
        rules=rules,
    )
    assert score_metadata(cased).band == 2

    missing_idea = make_context(
        metadata=meta("Export the quarterly budget as a PDF", apps),
        taskrecorder=task,
        rules=rules,
    )
    assert score_metadata(missing_idea).band == 3

    wrong_apps = make_context(
        metadata=meta(request, ["Keynote"]),
        taskrecorder=task,
        rules=rules,
    )
    assert score_metadata(wrong_apps).band == 3
    assert score_metadata(wrong_apps).details["apps_match"] is False

    numbered = TaskRecorderDoc(description="Export 2 charts from Numbers", apps=["Numbers"], source="mem")
    changed_number = make_context(
        metadata=meta("Export 3 charts from Numbers", ["Numbers"]),
        taskrecorder=numbered,
        rules=rules,
    )
    assert score_metadata(changed_number).band == 3

    quoted = TaskRecorderDoc(description='Save the file as "Final.pdf"', apps=["Preview"], source="mem")
    # The filename is still present, so the key idea is kept (band 2).
    unquoted = make_context(
        metadata=meta("Save the file as Final.pdf", ["Preview"]),
        taskrecorder=quoted,
        rules=rules,
    )
    assert score_metadata(unquoted).band == 2
    missing_name = make_context(
        metadata=meta("Save the file as requested", ["Preview"]),
        taskrecorder=quoted,
        rules=rules,
    )
    assert score_metadata(missing_name).band == 3

    alias = make_context(
        metadata=meta(request, ["Google Chrome"]),
        taskrecorder=TaskRecorderDoc(description=request, apps=["Chrome"], source="mem"),
        rules=rules,
    )
    assert score_metadata(alias).band == 1

    assert word_for_word("Export  a\nbudget", "Export a budget")


def test_taskrecorder_and_studio_and_zip(tmp_path: Path):
    recorder = tmp_path / "TaskRecorder.txt"
    recorder.write_text(
        "Description:\nBuild a one-page budget.\n\nApps:\n- Numbers\n- Preview\n",
        encoding="utf-8",
    )
    parsed = parse_taskrecorder_file(recorder)
    assert parsed.description == "Build a one-page budget."
    assert parsed.apps == ["Numbers", "Preview"]

    payload = tmp_path / "TaskRecorder.json"
    payload.write_text(
        json.dumps({"description": "Write the post.", "apps": ["Safari", "Notes"]}),
        encoding="utf-8",
    )
    parsed_json = parse_taskrecorder_file(payload)
    assert parsed_json.apps == ["Safari", "Notes"]

    studio = tmp_path / "StudioGoal.txt"
    studio.write_text(
        "First-Approved: 2026-10-01T18:00:00-07:00\n\nGoal:\nBuild a one-page budget.\n",
        encoding="utf-8",
    )
    goal = parse_studio_file(studio)
    assert goal.goal == "Build a one-page budget."
    assert goal.first_approved_at is not None
    assert goal.first_approved_at.utcoffset() is not None

    naive = parse_approved_at("2026-10-19T18:00:00")
    assert naive is not None
    assert naive.utcoffset().total_seconds() == -7 * 3600

    archive_path = tmp_path / "deliverables.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("budget.xlsx", b"x")
        archive.writestr("nested/out.pdf", b"y")
        archive.writestr("nested/", b"")
    inventory = parse_zip(archive_path)
    assert "nested/out.pdf" in inventory.entries
    assert "out.pdf" in inventory.basenames
    assert "budget.xlsx" in inventory.basenames
    assert all(not name.endswith("/") for name in inventory.entries)


def test_duration_boundaries():
    rules = load_rules()
    assert duration_status(900, rules) == "in_range"
    assert duration_status(899, rules) == "out_of_range"
    assert duration_status(3058.9, rules) == "in_range"
    assert duration_status(3059, rules) == "long"
    assert duration_status(3299.9, rules) == "long"
    assert duration_status(3300, rules) == "out_of_range"


def test_packaged_threshold_defaults():
    rules = load_rules()
    assert rules.low_confidence == 0.6
    assert rules.get("typing.max_share") == 0.25
    assert rules.get("typing.max_share_coding_writing") == 0.35
    assert rules.get("typing.segment_feedback_seconds") == 45
    assert rules.get("overlap.cover_fraction") == 0.25
    assert rules.get("overlap.band2_over_seconds") == 6
    assert rules.get("overlap.band3_over_seconds") == 30
    assert rules.get("narration.min_fraction") == 0.7
    assert rules.get("video.min_seconds") == 900
    assert rules.get("video.max_seconds") == 3299
    assert rules.get("video.long_notice_seconds") == 3059
    assert rules.get("epilogue.max_seconds") == 240
    assert rules.get("epilogue.not_required_before") == "2026-10-19T18:00:00-07:00"
    assert rules.get("ui_feedback.intro_seconds") == 20
    assert rules.get("ui_feedback.silence_seconds") == 45
    assert rules.get("goal_doc.promptly_within_seconds") == 10
    assert rules.get("clock.edge_seconds") == 10
    assert rules.get("ingest.edge_seconds") == 10
    assert rules.restricted_apps
    assert rules.allowed_ai
    assert any(term.severity == "major" for term in rules.profanity)
    assert "email" in rules.pii["patterns"]
    assert rules.licensing["fail_markers"]


def test_rules_override_merges(tmp_path: Path):
    config = tmp_path / "cfg"
    config.mkdir()
    (config / "rules.yaml").write_text("typing:\n  max_share: 0.5\n", encoding="utf-8")
    rules = load_rules(config)
    assert rules.get("typing.max_share") == 0.5
    assert rules.get("typing.max_share_coding_writing") == 0.35
    assert rules.profanity  # inherited lexicon


def _typing_frames(steps: list[bool]):
    """One frame per step, plus the opening frame. True marks a typing interval."""
    base = solid(80, 64, (12, 12, 14))
    frames = [(0.0, base.copy())]
    current = base.copy()
    for index, typing in enumerate(steps, start=1):
        if typing:
            current = base.copy()
            shade = 40 + (index * 30) % 200
            current[24:26, 16:31] = shade
        frames.append((float(index), current.copy()))
    return frames


def test_typing_share_thresholds():
    assert band_for_share(0.25, 0.25) == 1
    assert band_for_share(0.26, 0.25) == 3
    assert band_for_share(0.35, 0.35) == 1
    assert band_for_share(0.36, 0.35) == 3
    assert exactly_at_cap(0.25, 0.25)
    assert not exactly_at_cap(0.26, 0.25)

    quarter = score_typing(make_context(frames=_typing_frames([True, False, False, False])))
    assert quarter.details["share"] == pytest.approx(0.25)
    assert quarter.band == 1
    assert quarter.details["exactly_at_cap"] is True

    over = score_typing(make_context(frames=_typing_frames([True, True, False, False])))
    assert over.details["share"] == pytest.approx(0.5)
    assert over.band == 3

    coding_steps = [True] * 7 + [False] * 13
    coding = score_typing(
        make_context(frames=_typing_frames(coding_steps), task_type="Coding")
    )
    assert coding.details["share"] == pytest.approx(0.35)
    assert coding.band == 1
    assert coding.details["cap"] == pytest.approx(0.35)

    writing = score_typing(
        make_context(frames=_typing_frames(coding_steps), task_type="Content & Writing")
    )
    assert writing.band == 1

    too_much_code = score_typing(
        make_context(frames=_typing_frames([True] * 8 + [False] * 12), task_type="Coding")
    )
    assert too_much_code.details["share"] == pytest.approx(0.4)
    assert too_much_code.band == 3

    loose = load_rules()
    # 40% fails the packaged 25% cap and passes a loosened override.
    forty = [True, True, False, False, False]
    assert score_typing(make_context(frames=_typing_frames(forty), rules=loose)).band == 3


def test_typing_cap_override(tmp_path: Path):
    config = tmp_path / "cfg"
    config.mkdir()
    (config / "rules.yaml").write_text("typing:\n  max_share: 0.5\n", encoding="utf-8")
    rules = load_rules(config)
    result = score_typing(make_context(frames=_typing_frames([True, True, False, False, False]), rules=rules))
    assert result.details["share"] == pytest.approx(0.4)
    assert result.band == 1


def test_menu_clock_seconds_and_decoy():
    rules = load_rules()
    good = []
    for t in (0, 1, 2, 1190, 1195, 1199):
        frame = solid(180, 80)
        paint_menu_clock(frame, "12:34:56", rules, body="01:02:03")
        good.append((float(t), frame))
    # duration 1200 so the last frames sit in the closing 10s and the body
    # clock is a decoy that must not satisfy the menu-bar check.
    passed = score_clock(make_context(frames=good, duration=1200, rules=rules))
    assert passed.band == 1
    assert passed.details["start"] == "seconds"
    assert passed.details["end"] == "seconds"

    bad = []
    for t in (0, 1, 1198, 1199):
        frame = solid(180, 80)
        paint_menu_clock(frame, "12:34 PM", rules, body="01:02:03")
        bad.append((float(t), frame))
    failed = score_clock(make_context(frames=bad, duration=1200, rules=rules))
    assert failed.band == 3
    assert failed.drives_verdict is True


def test_clock_unreadable_does_not_drive():
    rules = load_rules()
    blank = [(0.0, solid(180, 80)), (1199.0, solid(180, 80))]
    result = score_clock(make_context(frames=blank, duration=1200, rules=rules))
    assert result.band is None
    assert result.drives_verdict is False


def test_cli_review_bundle(tmp_path: Path):
    rules = load_rules()
    frames = []
    for t in (0, 1, 2):
        image = solid(180, 80)
        paint_menu_clock(image, "09:15:07", rules)
        frames.append((float(t), image))
    folder = tmp_path / "submission"
    write_bundle(folder, frames, "Export the quarterly budget as a PDF from Numbers", ["Numbers", "Preview"])
    out = tmp_path / "review.json"
    code = main(["review", str(folder), "--json", str(out)])
    assert code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    by_key = {check["key"]: check for check in data["checks"]}
    assert by_key["metadata"]["band"] == 1
    assert by_key["clock"]["band"] == 1
    assert by_key["typing"]["band"] == 1
    assert data["stats"]["typing_share"] == pytest.approx(0.0)
    assert data["stats"]["duration_status"] == "out_of_range"
    assert data["parsed"]["request"].startswith("Export the quarterly")
    assert "budget.pdf" in data["parsed"]["deliverable_names"]
    assert "input.xlsx" in data["parsed"]["deliverable_names"]
    assert data["auto_send"] is False
    assert data["human_review_required"] is True
    assert set(data["drafts"]) >= {
        "studio_feedback",
        "send_back",
        "internal_notes",
        "slack_dm",
        "growth_notes",
    }
    assert main(["review", str(tmp_path / "missing")]) == 2


def test_ffprobe_scene_and_audio(tmp_path: Path):
    cut = tmp_path / "cut.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=64x64:d=1,format=rgb24",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x64:d=1,format=rgb24",
            "-filter_complex",
            "[0][1]concat=n=2:v=1:a=0",
            str(cut),
        ],
        check=True,
        timeout=60,
    )
    info = probe_video(cut)
    assert info.duration == pytest.approx(2.0, abs=0.15)
    assert info.width == 64
    assert info.has_audio is False
    times = scene_change_times(cut, 0.4)
    assert any(abs(stamp - 1.0) < 0.3 for stamp in times)

    frames, scenes = extract_video_frames(cut, tmp_path / "frames", info.duration, load_rules())
    assert len(frames) >= 2
    assert any(abs(stamp - 1.0) < 0.3 for stamp in scenes)

    with_audio = tmp_path / "audio.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=32x32:d=1",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=16000:cl=mono",
            "-shortest",
            "-t",
            "1",
            str(with_audio),
        ],
        check=True,
        timeout=60,
    )
    probed = probe_video(with_audio)
    assert probed.has_audio is True
    assert probed.sample_rate == 16000


def test_module_entrypoint_help():
    proc = subprocess.run(
        ["python3", "-m", "autoqc", "review", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "submission_folder" in proc.stdout
