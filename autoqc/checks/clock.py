"""Checklist item 5: the menu-bar clock shows seconds at the start and the end."""

from __future__ import annotations

import re

from autoqc.checks.common import TITLES, finish
from autoqc.context import ReviewContext
from autoqc.models import CheckResult, Evidence
from autoqc.timefmt import fmt_ts
from autoqc.vision.layout import menu_and_dock
from autoqc.vision.ocr import GlyphOcr

_HMS = re.compile(r"\d{1,2}:\d{2}:\d{2}")
_HM = re.compile(r"\d{1,2}:\d{2}")


def clock_box(image, rules) -> tuple[int, int, int, int]:
    height, width = image.shape[:2]
    menu_h, _dock = menu_and_dock(height, rules)
    fraction = float(rules.get("clock.right_fraction", 0.5))
    x0 = int(width * (1.0 - fraction))
    return x0, 0, width, max(menu_h, 1)


def classify_clock_text(text: str) -> str:
    if _HMS.search(text or ""):
        return "hms"
    if _HM.search(text or ""):
        return "hm"
    if (text or "").strip():
        return "other"
    return "empty"


def read_clock_text(image, ocr, rules) -> str:
    box = clock_box(image, rules)
    text = ocr.read(image, box, polarity="auto") if ocr is not None else ""
    if classify_clock_text(text) == "hms":
        return text
    if not isinstance(ocr, GlyphOcr):
        alt = GlyphOcr().read(image, box, polarity="auto")
        if classify_clock_text(alt) in {"hms", "hm"}:
            return alt
    return text or ""


def _window_status(samples: list[tuple[float, str]]) -> str:
    if not samples:
        return "missing"
    kinds = [classify_clock_text(text) for _t, text in samples]
    if "hms" in kinds:
        return "seconds"
    if "hm" in kinds:
        return "no_seconds"
    return "unreadable"


def score_clock(ctx: ReviewContext) -> CheckResult:
    edge = float(ctx.rules.get("clock.edge_seconds", 10))
    duration = float(ctx.submission.media.duration or 0.0)
    ocr = ctx.ocr if ctx.ocr is not None else GlyphOcr()
    start_samples: list[tuple[float, str]] = []
    end_samples: list[tuple[float, str]] = []
    for frame in ctx.frames:
        text = read_clock_text(frame.rgb, ocr, ctx.rules)
        if frame.t <= edge + 1e-6:
            start_samples.append((frame.t, text))
        if duration <= 0 or frame.t >= duration - edge - 1e-6:
            end_samples.append((frame.t, text))

    start = _window_status(start_samples)
    end = _window_status(end_samples)
    evidence = [
        Evidence(
            text=f"Start window ({fmt_ts(0)}–{fmt_ts(edge)}): {start}.",
            start=0.0,
            end=edge,
        ),
        Evidence(
            text=f"End window (last {edge:.0f}s, duration {fmt_ts(duration)}): {end}.",
            start=max(0.0, duration - edge),
            end=duration or None,
        ),
    ]
    for t, text in (start_samples[:1] + end_samples[-1:]):
        if text:
            evidence.append(Evidence(text=f"OCR at {fmt_ts(t)}: {text}", start=t))

    clear_fail = start in {"missing", "no_seconds"} or end in {"missing", "no_seconds"}
    both_seconds = start == "seconds" and end == "seconds"
    if both_seconds:
        band: int | None = 1
        confidence = 0.95
        summary = "The menu-bar clock shows seconds in the opening seconds and the closing seconds."
    elif clear_fail:
        band = 3
        confidence = 0.92
        summary = "The menu-bar clock does not show seconds at both the start and the end."
    else:
        band = None
        confidence = 0.42
        summary = "The menu-bar clock could not be read confidently at the start or the end."

    return finish(
        CheckResult(
            item=5,
            key="clock",
            title=TITLES[5],
            band=band,
            confidence=confidence,
            summary=summary,
            evidence=evidence,
            details={"start": start, "end": end, "edge_seconds": edge},
        ),
        ctx.rules,
    )
