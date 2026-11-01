"""Dock, cursor, and TaskRecorder signals.

These are rubric notes, not checklist bands. The decision engine decides
whether they become feedback or an internal note.
"""

from __future__ import annotations

from autoqc.context import ReviewContext
from autoqc.models import Evidence, Finding


def environment_findings(ctx: ReviewContext) -> list[Finding]:
    observations = ctx.observations
    if not observations:
        return []
    findings: list[Finding] = []
    positions = {obs.dock_position for obs in observations}
    if positions == {"absent"}:
        findings.append(
            Finding(
                id="dock-hidden",
                category="dock_not_visible",
                action="APPROVE_FEEDBACK",
                confidence=0.8,
                summary="The Dock is not visible.",
                drives_verdict=False,
            )
        )
    elif "bottom" not in positions and "absent" not in positions:
        place = next(iter(positions))
        findings.append(
            Finding(
                id="dock-position",
                category="dock_not_bottom",
                action="APPROVE_FEEDBACK",
                confidence=0.75,
                summary=f"The Dock is on the {place}, not the bottom.",
                drives_verdict=False,
            )
        )

    custom = [obs for obs in observations if obs.cursor_default is False]
    if custom:
        findings.append(
            Finding(
                id="cursor-custom",
                category="cursor_not_default",
                action="APPROVE_FEEDBACK",
                confidence=0.86,
                summary="The cursor is not the default size and colour.",
                evidence=[Evidence(text="Non-default cursor.", start=custom[0].t)],
                drives_verdict=False,
            )
        )

    recorder = []
    for obs in observations:
        for window in obs.windows:
            if window.app.casefold().replace(" ", "") in {"taskrecorder", "taskrecorder"}:
                recorder.append((obs.t, window))
            elif "taskrecorder" in f"{window.app} {window.title}".casefold().replace(" ", ""):
                recorder.append((obs.t, window))
    if recorder:
        t, window = recorder[0]
        findings.append(
            Finding(
                id="taskrecorder-visible",
                category="taskrecorder_visible",
                action="APPROVE_FEEDBACK",
                confidence=0.9,
                summary="The TaskRecorder window is visible.",
                evidence=[Evidence(text=window.label, start=t, windows=[window.label])],
                drives_verdict=False,
            )
        )
    start_limit = 10.0
    shown_at_start = any(t <= start_limit for t, _window in recorder)
    if observations and observations[0].t <= start_limit and not shown_at_start:
        findings.append(
            Finding(
                id="taskrecorder-start",
                category="taskrecorder_not_at_start",
                action="INTERNAL_NOTE",
                confidence=0.55,
                summary="TaskRecorder is not shown at the start (possible recorder bug).",
                evidence=[Evidence(text="No TaskRecorder window in the opening seconds.", start=0.0)],
                drives_verdict=False,
            )
        )
    return findings
