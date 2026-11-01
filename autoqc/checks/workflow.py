"""Checklist item 4: the recording shows the workflow and the zip has the files."""

from __future__ import annotations

import re

from autoqc.audio.transcribe import Transcript
from autoqc.checks.common import TITLES, finish
from autoqc.checks.textutil import content_tokens
from autoqc.context import ReviewContext
from autoqc.models import CheckResult, Evidence

_FILENAME = re.compile(r"\b[\w.-]+\.(?:pdf|png|jpg|jpeg|xlsx|csv|txt|docx|pptx|py|md|mov|mp4|zip|fig|psd)\b", re.IGNORECASE)
_STEP = re.compile(r"(?m)^\s*(\d+)[.)]\s+(.+)$")


def levenshtein(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for i, lchar in enumerate(left, start=1):
        current = [i]
        for j, rchar in enumerate(right, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (lchar != rchar)))
        previous = current
    return previous[-1]


def _haystack(ctx: ReviewContext) -> str:
    parts = []
    for obs in ctx.observations:
        parts.append(obs.ocr_text)
        for window in obs.windows:
            if window.is_goal:
                continue
            parts.append(f"{window.app} {window.title} {window.text}")
    for action in ctx.actions:
        parts.append(f"{action.kind} {action.target} {action.detail}")
    transcript = ctx.transcript
    if isinstance(transcript, Transcript):
        parts.append(transcript.text)
    return " ".join(part for part in parts if part)


def _zip_names(ctx: ReviewContext) -> list[str]:
    inventory = ctx.submission.zip_inventory
    if not inventory:
        return []
    return list(inventory.basenames)


def _near_misses(expected: list[str], actual: list[str], limit: int) -> list[dict]:
    misses = []
    actual_cf = {name.casefold(): name for name in actual}
    for name in expected:
        if name.casefold() in actual_cf:
            continue
        best = None
        best_distance = limit + 1
        for candidate in actual:
            distance = levenshtein(name.casefold(), candidate.casefold())
            if distance < best_distance:
                best = candidate
                best_distance = distance
        if best is not None and best_distance <= limit:
            misses.append({"expected": name, "actual": best, "distance": best_distance})
    return misses


def score_workflow(ctx: ReviewContext) -> CheckResult:
    description = ctx.submission.taskrecorder.description if ctx.submission.taskrecorder else ""
    goal = ctx.submission.studio.goal if ctx.submission.studio else ""
    haystack = _haystack(ctx)
    zip_names = _zip_names(ctx)
    limit = int(ctx.rules.get("workflow.filename_near_distance", 3))
    named = []
    for source in (description, goal):
        named.extend(_FILENAME.findall(source or ""))
    for obs in ctx.observations:
        for window in obs.windows:
            if window.is_goal:
                continue
            named.extend(_FILENAME.findall(f"{window.title} {window.text}"))
    expected = []
    for name in named:
        if name not in expected:
            expected.append(name)

    missing = [name for name in expected if name.casefold() not in {item.casefold() for item in zip_names}]
    near = _near_misses(missing, zip_names, limit)
    near_expected = {item["expected"].casefold() for item in near}
    really_missing = [name for name in missing if name.casefold() not in near_expected]

    steps = _STEP.findall(description or "")
    missing_steps = []
    for number, step in steps:
        tokens = content_tokens(step)
        if not tokens:
            continue
        found = sum(1 for token in tokens if token in haystack.casefold())
        if found / len(tokens) < 0.5:
            missing_steps.append(f"{number}. {step.strip()}")

    evidence = []
    for name in really_missing:
        evidence.append(Evidence(text=f"{name} is not in deliverables.zip."))
    for step in missing_steps:
        evidence.append(Evidence(text=f"Numbered step not shown: {step}"))
    for item in near:
        evidence.append(Evidence(text=f"{item['expected']} is close to {item['actual']} in the zip."))

    if not ctx.observations and not description:
        return finish(
            CheckResult(
                item=4,
                key="workflow",
                title=TITLES[4],
                band=None,
                confidence=0.3,
                summary="Not enough information to compare the workflow with the zip.",
            ),
            ctx.rules,
        )
    if really_missing or missing_steps:
        return finish(
            CheckResult(
                item=4,
                key="workflow",
                title=TITLES[4],
                band=3,
                confidence=0.84,
                summary="The recording or deliverables.zip is missing part of the workflow.",
                evidence=evidence,
                details={"missing_files": really_missing, "missing_steps": missing_steps, "near_misses": near},
            ),
            ctx.rules,
        )
    summary = "The numbered steps and named files are accounted for."
    if near:
        summary = "Named files are present up to a small filename difference."
    return finish(
        CheckResult(
            item=4,
            key="workflow",
            title=TITLES[4],
            band=1,
            confidence=0.8,
            summary=summary,
            evidence=evidence,
            details={"missing_files": [], "missing_steps": [], "near_misses": near},
        ),
        ctx.rules,
    )
