"""Checklist item 1: Metadata.rtf against the TaskRecorder description and apps."""

from __future__ import annotations

from autoqc.checks.common import TITLES, finish
from autoqc.checks.textutil import app_set, ideas_kept, key_idea_recall, word_for_word
from autoqc.context import ReviewContext
from autoqc.models import CheckResult, Evidence


def score_metadata(ctx: ReviewContext) -> CheckResult:
    meta = ctx.submission.metadata
    task = ctx.submission.taskrecorder
    if meta is None or task is None:
        return finish(
            CheckResult(
                item=1,
                key="metadata",
                title=TITLES[1],
                band=None,
                confidence=0.35,
                summary="Metadata.rtf or the TaskRecorder description is missing, so they cannot be compared.",
                evidence=[Evidence(text="Provide both files to score this item.")],
            ),
            ctx.rules,
        )

    recall_min = float(ctx.rules.get("key_ideas.recall_min", 0.85))
    same_words = word_for_word(meta.request, task.description)
    recall = key_idea_recall(task.description, meta.request)
    kept = ideas_kept(task.description, meta.request, recall_min)
    meta_apps = app_set(meta.apps, ctx.rules)
    task_apps = app_set(task.apps, ctx.rules)
    apps_match = meta_apps == task_apps

    if same_words and apps_match:
        band = 1
        summary = "Request matches the TaskRecorder description word for word, and the apps match."
    elif kept and apps_match:
        band = 2
        summary = "Wording differs, but every key idea is still there and the apps match."
    else:
        band = 3
        reasons = []
        if not kept:
            reasons.append("key ideas differ")
        if not apps_match:
            reasons.append("apps do not match")
        summary = "Metadata.rtf needs a corrected file (" + " and ".join(reasons) + ")."

    evidence = [
        Evidence(text=f"TaskRecorder apps: {', '.join(task.apps) or '(none)'}"),
        Evidence(text=f"Metadata apps (Task Description + TOPOLOGY): {', '.join(meta.apps) or '(none)'}"),
    ]
    if band != 1:
        evidence.append(Evidence(text="TaskRecorder: " + task.description))
        evidence.append(Evidence(text="Metadata Request: " + meta.request))

    return finish(
        CheckResult(
            item=1,
            key="metadata",
            title=TITLES[1],
            band=band,
            confidence=0.96,
            summary=summary,
            evidence=evidence,
            details={
                "word_for_word": same_words,
                "key_idea_recall": round(recall, 4),
                "ideas_kept": kept,
                "apps_match": apps_match,
                "metadata_apps": sorted(meta_apps),
                "taskrecorder_apps": sorted(task_apps),
            },
        ),
        ctx.rules,
    )
