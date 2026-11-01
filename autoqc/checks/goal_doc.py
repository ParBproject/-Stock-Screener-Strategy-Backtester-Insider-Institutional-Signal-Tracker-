"""Checklist item 6: the goal document is shown, then minimized, and not in Notes or TextEdit."""

from __future__ import annotations

from autoqc.checks.common import TITLES, finish
from autoqc.checks.textutil import canon_app
from autoqc.context import ReviewContext
from autoqc.models import CheckResult, Evidence
from autoqc.timefmt import fmt_ts


def score_goal_doc(ctx: ReviewContext) -> CheckResult:
    goal = ctx.submission.studio.goal if ctx.submission.studio else ""
    if not goal.strip():
        return finish(
            CheckResult(
                item=6,
                key="goal_doc",
                title=TITLES[6],
                band=None,
                confidence=0.35,
                summary="No Studio goal was provided, so the goal document cannot be checked.",
            ),
            ctx.rules,
        )
    if not ctx.observations:
        return finish(
            CheckResult(
                item=6,
                key="goal_doc",
                title=TITLES[6],
                band=None,
                confidence=0.3,
                summary="No frames were available to look for the goal document.",
            ),
            ctx.rules,
        )

    limit = float(ctx.rules.get("goal_doc.promptly_within_seconds", 10))
    disallowed = {canon_app(str(name), ctx.rules) for name in ctx.rules.get("goal_doc.disallowed_apps", [])}
    showings = []
    for obs in ctx.observations:
        for window in obs.windows:
            if window.is_goal:
                showings.append((obs.t, window))

    if not showings:
        return finish(
            CheckResult(
                item=6,
                key="goal_doc",
                title=TITLES[6],
                band=3,
                confidence=0.86,
                summary="The goal document is not shown at the start.",
                evidence=[Evidence(text="No goal window in the sampled frames.", start=0.0)],
            ),
            ctx.rules,
        )

    bad_app = [(t, window) for t, window in showings if canon_app(window.app, ctx.rules) in disallowed]
    if bad_app:
        t, window = bad_app[0]
        return finish(
            CheckResult(
                item=6,
                key="goal_doc",
                title=TITLES[6],
                band=3,
                confidence=0.93,
                summary=f"The goal document is open in {window.app}, which is not allowed.",
                evidence=[
                    Evidence(
                        text=f"{window.label} at {fmt_ts(t)}.",
                        start=t,
                        windows=[window.label],
                    )
                ],
                details={"app": window.app},
            ),
            ctx.rules,
        )

    first = min(t for t, _window in showings)
    late = [(t, window) for t, window in showings if t > limit]
    if first > 3:
        return finish(
            CheckResult(
                item=6,
                key="goal_doc",
                title=TITLES[6],
                band=3,
                confidence=0.84,
                summary="The goal document is not on screen at the start.",
                evidence=[Evidence(text=f"First seen at {fmt_ts(first)}.", start=first)],
            ),
            ctx.rules,
        )
    if late:
        t, window = late[0]
        return finish(
            CheckResult(
                item=6,
                key="goal_doc",
                title=TITLES[6],
                band=3,
                confidence=0.9,
                summary=f"The goal document is still up after {limit:.0f}s.",
                evidence=[Evidence(text=f"{window.label} still visible at {fmt_ts(t)}.", start=t, windows=[window.label])],
            ),
            ctx.rules,
        )

    last = max(t for t, _window in showings)
    return finish(
        CheckResult(
            item=6,
            key="goal_doc",
            title=TITLES[6],
            band=1,
            confidence=0.9,
            summary=f"The goal document is shown at the start and gone after {fmt_ts(last)}.",
            evidence=[Evidence(text=showings[0][1].label, start=first, end=last, windows=[showings[0][1].label])],
            details={"first": first, "last": last, "app": showings[0][1].app},
        ),
        ctx.rules,
    )
