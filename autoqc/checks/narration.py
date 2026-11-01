"""Checklist item 3: narration says what and where, and why when it is useful."""

from __future__ import annotations

from autoqc.audio.narration import classify_utterance, utterance_for
from autoqc.audio.transcribe import Transcript
from autoqc.checks.common import TITLES, finish
from autoqc.context import ReviewContext
from autoqc.models import CheckResult, Evidence
from autoqc.timefmt import fmt_ts


def _transcript(ctx: ReviewContext) -> Transcript:
    current = ctx.transcript
    if isinstance(current, Transcript):
        return current
    return Transcript(language="", language_confidence=0.0, words=[], source="empty")


def score_narration(ctx: ReviewContext) -> CheckResult:
    actions = list(ctx.actions)
    if not actions:
        return finish(
            CheckResult(
                item=3,
                key="narration",
                title=TITLES[3],
                band=None,
                confidence=0.35,
                summary="No actions were detected, so narration coverage was not scored.",
            ),
            ctx.rules,
        )
    pre = float(ctx.rules.get("narration.pre_seconds", 1.5))
    post = float(ctx.rules.get("narration.post_seconds", 6.0))
    minimum = float(ctx.rules.get("narration.min_fraction", 0.70))
    words = _transcript(ctx).words
    rows = []
    for action in actions:
        utterance = utterance_for(words, action.t, pre, post)
        label = classify_utterance(action, utterance, ctx.rules)
        rows.append((action, label))
    total = len(rows)
    full = sum(1 for _action, label in rows if label.what and label.where and label.why)
    located = sum(1 for _action, label in rows if label.what and label.where)
    full_fraction = full / total
    where_fraction = located / total
    if full_fraction + 1e-9 >= minimum:
        band = 1
        summary = f"{full_fraction:.0%} of actions have what, where, and why."
    elif where_fraction + 1e-9 >= minimum:
        band = 2
        summary = f"{where_fraction:.0%} of actions have what and where. Fewer explain why."
    else:
        band = 3
        summary = (
            f"Only {where_fraction:.0%} of actions say what and where "
            f"(need {minimum:.0%}). What and why without a place does not count."
        )
    evidence = []
    for action, label in rows:
        if label.what and label.where and (band == 2 or label.why):
            continue
        missing = []
        if not label.what:
            missing.append("what")
        if not label.where:
            missing.append("where")
        if band == 1 and not label.why:
            missing.append("why")
        if not missing:
            continue
        evidence.append(
            Evidence(
                text=f"At {fmt_ts(action.t)} {action.kind} {action.target}: missing {', '.join(missing)}. Heard: {label.utterance or '(silence)'}",
                start=action.t,
                windows=[action.window] if action.window else [],
            )
        )
    return finish(
        CheckResult(
            item=3,
            key="narration",
            title=TITLES[3],
            band=band,
            confidence=0.84 if words else 0.55,
            summary=summary,
            evidence=evidence[:8],
            details={
                "full_fraction": full_fraction,
                "where_fraction": where_fraction,
                "actions": total,
                "threshold": minimum,
            },
        ),
        ctx.rules,
    )
