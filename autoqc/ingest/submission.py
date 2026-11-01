"""Assemble one submission folder into a Submission."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from autoqc.errors import AutoQCError
from autoqc.ingest.frames import (
    FrameRef,
    extract_video_frames,
    infer_duration,
    load_frames_csv,
)
from autoqc.ingest.parsers import (
    MetadataDoc,
    StudioDoc,
    TaskRecorderDoc,
    ZipInventory,
    parse_approved_at,
    parse_metadata_file,
    parse_studio_file,
    parse_taskrecorder_file,
    parse_zip,
)
from autoqc.ingest.probe import MediaInfo, probe_video
from autoqc.rules.loader import RuleSet

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm"}
_PREFERRED_RECORDINGS = {"recording", "screen", "video"}


@dataclass
class Submission:
    root: Path
    media: MediaInfo
    frames: list[FrameRef] = field(default_factory=list)
    scene_times: list[float] = field(default_factory=list)
    recording: Path | None = None
    metadata: MetadataDoc | None = None
    metadata_path: Path | None = None
    taskrecorder: TaskRecorderDoc | None = None
    taskrecorder_path: Path | None = None
    studio: StudioDoc | None = None
    studio_path: Path | None = None
    zip_inventory: ZipInventory | None = None
    zip_path: Path | None = None
    transcript_path: Path | None = None
    task_type: str = "other"
    review_number: int = 1
    idea_first_approved_at: datetime | None = None
    prior_notes: str = ""
    prior_root: Path | None = None
    prior: Submission | None = None
    locked_fields: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    manifest: dict = field(default_factory=dict)


def _files(root: Path) -> dict[str, Path]:
    return {path.name.lower(): path for path in root.iterdir() if path.is_file()}


def _find(files: dict[str, Path], names: list[str]) -> Path | None:
    for name in names:
        hit = files.get(name.lower())
        if hit is not None:
            return hit
    return None


def find_recording(root: Path) -> Path | None:
    candidates = [path for path in root.iterdir() if path.is_file() and path.suffix.lower() in VIDEO_EXTS]
    if not candidates:
        return None
    preferred = [path for path in candidates if path.stem.lower() in _PREFERRED_RECORDINGS]
    pool = preferred or candidates
    return sorted(pool, key=lambda path: path.name.lower())[0]


def _load_manifest(path: Path, issues: list[str]) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        issues.append(f"unreadable submission.json: {exc}")
        return {}
    if not isinstance(payload, dict):
        issues.append("submission.json must be an object")
        return {}
    return payload


def _review_number(value, issues: list[str]) -> int:
    if value is None:
        return 1
    try:
        number = int(value)
    except (TypeError, ValueError):
        issues.append("review_number is not an integer; defaulting to 1")
        return 1
    if number < 1:
        issues.append("review_number must be at least 1; defaulting to 1")
        return 1
    return number


def _empty_media() -> MediaInfo:
    return MediaInfo(
        path=None,
        duration=0.0,
        width=None,
        height=None,
        fps=None,
        video_codec=None,
        audio_codec=None,
        has_audio=False,
        sample_rate=None,
        source="missing",
    )


def load_submission(folder: Path, rules: RuleSet, *, load_prior: bool = True) -> Submission:
    root = Path(folder)
    if not root.is_dir():
        raise AutoQCError(f"submission folder not found: {root}")

    issues: list[str] = []
    notices: list[str] = []
    files = _files(root)
    manifest_path = _find(files, ["submission.json"])
    manifest = _load_manifest(manifest_path, issues) if manifest_path else {}

    metadata_path = _find(files, ["Metadata.rtf", "metadata.rtf", "Metadata.txt"])
    task_path = _find(
        files,
        ["TaskRecorder.txt", "TaskRecorder.json", "taskrecorder.txt", "task_recorder.txt", "task_recorder.json"],
    )
    studio_path = _find(files, ["StudioGoal.txt", "StudioGoal.json", "studio_goal.txt", "studio.txt", "Goal.txt"])
    zip_path = _find(files, ["deliverables.zip", "Deliverables.zip"])
    transcript_path = _find(files, ["transcript.json", "narration.json"])
    notes_path = _find(files, ["prior_notes.txt", "PriorReview.txt", "prior_review.txt"])

    metadata = None
    if metadata_path is None:
        issues.append("missing Metadata.rtf")
    else:
        try:
            metadata = parse_metadata_file(metadata_path)
        except AutoQCError as exc:
            issues.append(f"Metadata.rtf: {exc}")

    taskrecorder = None
    if task_path is None:
        issues.append("missing TaskRecorder description")
    else:
        try:
            taskrecorder = parse_taskrecorder_file(task_path)
        except AutoQCError as exc:
            issues.append(f"TaskRecorder: {exc}")

    studio = None
    if studio_path is None:
        issues.append("missing Studio goal")
    else:
        try:
            studio = parse_studio_file(studio_path)
        except AutoQCError as exc:
            issues.append(f"Studio goal: {exc}")

    inventory = None
    if zip_path is None:
        issues.append("missing deliverables.zip")
    else:
        try:
            inventory = parse_zip(zip_path)
        except AutoQCError as exc:
            issues.append(f"deliverables.zip: {exc}")

    recording = find_recording(root)
    csv_path = _find(files, ["frames.csv"])
    if csv_path is None and (root / "frames" / "frames.csv").is_file():
        csv_path = root / "frames" / "frames.csv"

    frames: list[FrameRef] = []
    scene_times: list[float] = []
    if recording is not None:
        media = probe_video(recording)
        frames, scene_times = extract_video_frames(recording, root / ".autoqc" / "frames", media.duration, rules)
        if csv_path is not None:
            notices.append("frames.csv ignored because a recording is present; ffprobe duration is used")
        override = manifest.get("duration_seconds")
        if override is not None:
            notices.append("submission.json duration_seconds ignored because ffprobe duration is authoritative")
    elif csv_path is not None:
        frames = load_frames_csv(root, csv_path)
        override = _optional_float(manifest.get("duration_seconds"), issues)
        duration = infer_duration(frames, override)
        media = MediaInfo(
            path=None,
            duration=duration,
            width=None,
            height=None,
            fps=None,
            video_codec=None,
            audio_codec=None,
            has_audio=False,
            sample_rate=None,
            source="frames",
        )
    else:
        issues.append("missing recording")
        media = _empty_media()

    approved = None
    if manifest.get("idea_first_approved_at"):
        try:
            approved = parse_approved_at(str(manifest["idea_first_approved_at"]))
        except AutoQCError as exc:
            issues.append(str(exc))
    elif studio and studio.first_approved_at:
        approved = studio.first_approved_at

    prior_notes = ""
    if isinstance(manifest.get("prior_notes"), str) and manifest["prior_notes"].strip():
        prior_notes = manifest["prior_notes"].strip()
    elif notes_path is not None:
        try:
            prior_notes = notes_path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError as exc:
            issues.append(f"unreadable prior notes: {exc}")

    locked = manifest.get("locked_fields") or []
    if not isinstance(locked, list):
        issues.append("locked_fields must be a list")
        locked = []

    prior_root = None
    if manifest.get("prior_submission"):
        candidate = Path(str(manifest["prior_submission"]))
        if not candidate.is_absolute():
            candidate = root / candidate
        prior_root = candidate
    elif (root / "prior").is_dir():
        prior_root = root / "prior"

    submission = Submission(
        root=root,
        media=media,
        frames=frames,
        scene_times=scene_times,
        recording=recording,
        metadata=metadata,
        metadata_path=metadata_path,
        taskrecorder=taskrecorder,
        taskrecorder_path=task_path,
        studio=studio,
        studio_path=studio_path,
        zip_inventory=inventory,
        zip_path=zip_path,
        transcript_path=transcript_path,
        task_type=str(manifest.get("task_type") or "other"),
        review_number=_review_number(manifest.get("review_number", 1), issues),
        idea_first_approved_at=approved,
        prior_notes=prior_notes,
        prior_root=prior_root,
        locked_fields=[str(item) for item in locked],
        issues=issues,
        notices=notices,
        manifest=manifest,
    )
    if load_prior and prior_root is not None:
        if not prior_root.is_dir():
            submission.issues.append(f"prior submission not found: {prior_root}")
        else:
            try:
                submission.prior = load_submission(prior_root, rules, load_prior=False)
            except AutoQCError as exc:
                submission.issues.append(f"prior submission: {exc}")
    return submission


def _optional_float(value, issues: list[str]) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        issues.append("duration_seconds is not a number and was ignored")
        return None
