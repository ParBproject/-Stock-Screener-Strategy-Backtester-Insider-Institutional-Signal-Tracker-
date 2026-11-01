"""Checklist item 2: working content stays visible.

Two tabs of one window are one rectangle, so they are not compared as
separate windows. A cover is counted only from the front window onto the
one behind it.
"""

from __future__ import annotations

from autoqc.checks.common import TITLES, finish
from autoqc.context import ReviewContext
from autoqc.models import CheckResult, Evidence, WindowBox
from autoqc.timefmt import fmt_ts
from autoqc.vision.screen import median_dt
from autoqc.vision.theme import TITLE_PX


def _intersection(a: WindowBox, b: WindowBox) -> int:
    x0, y0 = max(a.x, b.x), max(a.y, b.y)
    x1, y1 = min(a.x + a.w, b.x + b.w), min(a.y + a.h, b.y + b.h)
    if x1 <= x0 or y1 <= y0:
        return 0
    return (x1 - x0) * (y1 - y0)


def _body(window: WindowBox) -> WindowBox:
    top = TITLE_PX + 2
    return WindowBox(
        app=window.app,
        title=window.title,
        window_id=window.window_id,
        x=window.x + 2,
        y=window.y + top,
        w=max(1, window.w - 4),
        h=max(1, window.h - top - 2),
        z=window.z,
    )


def _pair_events(obs) -> list[dict]:
    events = []
    for front in obs.windows:
        for back in obs.windows:
            if front.window_id == back.window_id or front.z <= back.z:
                continue
            area = back.area or 1
            fraction = _intersection(front, back) / area
            body = _body(back)
            body_fraction = _intersection(front, body) / (body.area or 1)
            if fraction <= 0 and body_fraction <= 0:
                continue
            events.append(
                {
                    "t": obs.t,
                    "fraction": fraction,
                    "body_fraction": body_fraction if back.is_content else 0.0,
                    "front": front.label,
                    "back": back.label,
                    "content": back.is_content,
                }
            )
    return events


def _runs(samples: list[dict], predicate) -> list[list[dict]]:
    runs: list[list[dict]] = []
    current: list[dict] = []
    last_t = None
    for sample in samples:
        if not predicate(sample):
            if current:
                runs.append(current)
                current = []
            last_t = sample["t"]
            continue
        if current and last_t is not None and sample["t"] - last_t > 2.5:
            runs.append(current)
            current = []
        current.append(sample)
        last_t = sample["t"]
    if current:
        runs.append(current)
    return runs


def _duration(run: list[dict], step: float) -> float:
    if not run:
        return 0.0
    if len(run) == 1:
        return step
    return float(run[-1]["t"] - run[0]["t"]) + step


def score_visibility(ctx: ReviewContext) -> CheckResult:
    cover = float(ctx.rules.get("overlap.cover_fraction", 0.25))
    band2_over = float(ctx.rules.get("overlap.band2_over_seconds", 6))
    band3_over = float(ctx.rules.get("overlap.band3_over_seconds", 30))
    content_frac = float(ctx.rules.get("overlap.working_content_fraction", 0.15))
    minor_frac = float(ctx.rules.get("overlap.minor_overlap_fraction", 0.05))
    observations = ctx.observations
    if not observations:
        return finish(
            CheckResult(
                item=2,
                key="visibility",
                title=TITLES[2],
                band=None,
                confidence=0.3,
                summary="No frames were available to judge window overlap.",
            ),
            ctx.rules,
        )

    samples = []
    for obs in observations:
        events = _pair_events(obs)
        heavy = [event for event in events if event["fraction"] > cover]
        content = [event for event in events if event["content"] and event["body_fraction"] > content_frac]
        minor = [event for event in events if minor_frac <= event["fraction"] <= cover and not content]
        samples.append(
            {
                "t": obs.t,
                "heavy": heavy,
                "content": content,
                "minor": minor,
                "heavy_on": bool(heavy),
            }
        )

    step = median_dt([obs.t for obs in observations])
    heavy_runs = _runs(samples, lambda sample: sample["heavy_on"])
    longest = max((_duration(run, step) for run in heavy_runs), default=0.0)
    content_hits = [sample for sample in samples if sample["content"]]
    minor_hits = [sample for sample in samples if sample["minor"]]

    evidence: list[Evidence] = []
    for run in heavy_runs:
        event = run[0]["heavy"][0]
        evidence.append(
            Evidence(
                text=f"{event['front']} covered {event['back']}.",
                start=run[0]["t"],
                end=run[-1]["t"],
                windows=[event["front"], event["back"]],
            )
        )
    for sample in content_hits:
        event = sample["content"][0]
        evidence.append(
            Evidence(
                text=f"{event['front']} covered working content in {event['back']}.",
                start=sample["t"],
                end=sample["t"],
                windows=[event["front"], event["back"]],
            )
        )

    if content_hits or longest > band3_over:
        band = 3
        if content_hits:
            summary = "A window covers working content."
        else:
            summary = f"A window covers more than {cover:.0%} of another for {longest:.0f}s."
        confidence = 0.9
    elif longest > band2_over:
        band = 2
        summary = (
            f"A window covers more than {cover:.0%} of another for {longest:.0f}s "
            "(between 6 and 30 seconds) without covering working content."
        )
        confidence = 0.9
    else:
        band = 1
        if minor_hits:
            summary = "Only minor overlap, and working content stays visible."
        elif longest > 0:
            summary = f"Overlap above {cover:.0%} lasts {longest:.0f}s, which is within 6 seconds."
        else:
            summary = "No window covers more than a quarter of another, and working content stays visible."
        confidence = 0.88 if any(obs.windows for obs in observations) else 0.7

    return finish(
        CheckResult(
            item=2,
            key="visibility",
            title=TITLES[2],
            band=band,
            confidence=confidence,
            summary=summary,
            evidence=evidence,
            details={
                "longest_cover_seconds": longest,
                "content_covered": bool(content_hits),
                "minor_overlap": bool(minor_hits),
                "minor_at": [sample["t"] for sample in minor_hits],
            },
        ),
        ctx.rules,
    )
