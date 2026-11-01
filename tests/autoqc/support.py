"""Helpers for synthetic submissions. No models and no network."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

from autoqc.context import FrameImage, ReviewContext
from autoqc.ingest.parsers import MetadataDoc, TaskRecorderDoc, render_metadata_rtf
from autoqc.ingest.probe import MediaInfo
from autoqc.ingest.submission import Submission
from autoqc.rules.loader import RuleSet, load_rules
from autoqc.vision.font import draw_text, text_width
from autoqc.vision.layout import menu_and_dock
from autoqc.vision.ocr import GlyphOcr


def solid(width: int, height: int, color: tuple[int, int, int] = (28, 28, 32)) -> np.ndarray:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :] = color
    return image


def paint_menu_clock(image: np.ndarray, text: str, rules: RuleSet, body: str | None = None) -> np.ndarray:
    height, width = image.shape[:2]
    menu_h, _dock = menu_and_dock(height, rules)
    image[:menu_h, :] = (45, 45, 48)
    x = max(0, width - text_width(text) - 2)
    y = max(0, (menu_h - 7) // 2)
    draw_text(image, x, y, text, (255, 255, 255))
    if body:
        draw_text(image, 4, menu_h + 4, body, (250, 250, 250))
    return image


def save_png(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image, mode="RGB").save(path)


def media(duration: float, source: str = "frames") -> MediaInfo:
    return MediaInfo(
        path=None,
        duration=duration,
        width=None,
        height=None,
        fps=None,
        video_codec=None,
        audio_codec=None,
        has_audio=False,
        sample_rate=None,
        source=source,
    )


def make_context(
    frames: list[tuple[float, np.ndarray]] | None = None,
    duration: float = 1200,
    task_type: str = "other",
    metadata: MetadataDoc | None = None,
    taskrecorder: TaskRecorderDoc | None = None,
    rules: RuleSet | None = None,
) -> ReviewContext:
    rules = rules or load_rules()
    submission = Submission(
        root=Path("."),
        media=media(duration),
        task_type=task_type,
        metadata=metadata,
        taskrecorder=taskrecorder,
    )
    images = [FrameImage(t=t, path="", rgb=image) for t, image in frames or []]
    return ReviewContext(submission=submission, rules=rules, frames=images, ocr=GlyphOcr())


def write_bundle(
    root: Path,
    frames: list[tuple[float, np.ndarray]],
    request: str,
    apps: list[str],
    description: str | None = None,
    task_type: str = "other",
    review_number: int = 1,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    description = request if description is None else description
    (root / "Metadata.rtf").write_text(render_metadata_rtf(request, apps), encoding="utf-8")
    app_lines = "\n".join(f"- {app}" for app in apps)
    (root / "TaskRecorder.txt").write_text(
        f"Description:\n{description}\n\nApps:\n{app_lines}\n",
        encoding="utf-8",
    )
    (root / "StudioGoal.txt").write_text(f"Goal:\n{description}\n", encoding="utf-8")
    with zipfile.ZipFile(root / "deliverables.zip", "w") as archive:
        archive.writestr("budget.pdf", b"pdf")
        archive.writestr("notes/input.xlsx", b"sheet")
    rows = ["filename,t"]
    for index, (t, image) in enumerate(frames):
        relative = f"frames/f{index:03d}.png"
        save_png(root / relative, image)
        rows.append(f"{relative},{t}")
    (root / "frames.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    (root / "submission.json").write_text(
        json.dumps({"task_type": task_type, "review_number": review_number}),
        encoding="utf-8",
    )
