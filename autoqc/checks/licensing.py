"""Checklist item 11: deliverable licensing.

A trademarked logo on a site being browsed does not fail. An unclear
rights marker escalates instead of choosing a band.
"""

from __future__ import annotations

import zipfile

from autoqc.checks.common import TITLES, finish
from autoqc.context import ReviewContext
from autoqc.models import CheckResult, Evidence, Finding
from autoqc.timefmt import fmt_ts


def _markers(rules, key: str) -> list[str]:
    return [str(item) for item in (rules.licensing.get(key) or [])]


def _browser_names(rules) -> set[str]:
    return {str(name).casefold() for name in _markers(rules, "browser_apps")}


def _deliverable_text(ctx: ReviewContext) -> str:
    chunks: list[str] = []
    inventory = ctx.submission.zip_inventory
    if inventory:
        chunks.extend(inventory.entries)
    path = ctx.submission.zip_path
    if path is None or not path.exists():
        return " ".join(chunks)
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        return " ".join(chunks)
    with archive:
        for info in archive.infolist():
            if info.is_dir() or not info.filename.lower().endswith((".txt", ".md", ".csv", ".html")):
                continue
            try:
                chunks.append(archive.read(info).decode("utf-8", errors="ignore")[:20000])
            except OSError:
                continue
    return " ".join(chunks)


def score_licensing(ctx: ReviewContext) -> CheckResult:
    fail = [item.casefold() for item in _markers(ctx.rules, "fail_markers")]
    allowed = [item.casefold() for item in _markers(ctx.rules, "allowed_markers")]
    uncertain = [item.casefold() for item in _markers(ctx.rules, "uncertain_markers")]
    logos = [item.casefold() for item in _markers(ctx.rules, "logo_brands")]
    browsers = _browser_names(ctx.rules)
    deliverable = _deliverable_text(ctx).casefold()

    content_fail: list[tuple[float, str]] = []
    browser_fail: list[tuple[float, str]] = []
    soft: list[tuple[float, str]] = []
    allowed_hit = False
    logo_only = False

    for obs in ctx.observations:
        for window in obs.windows:
            blob = f"{window.app} {window.title} {window.text}".casefold()
            browser = window.app.casefold() in browsers and not window.is_content
            for phrase in fail:
                if phrase in blob:
                    if browser:
                        browser_fail.append((obs.t, phrase))
                    else:
                        content_fail.append((obs.t, phrase))
            for phrase in uncertain:
                if phrase in blob:
                    soft.append((obs.t, phrase))
            if any(phrase in blob for phrase in allowed):
                allowed_hit = True
            if browser and any(logo in blob for logo in logos) and not any(phrase in blob for phrase in fail):
                logo_only = True
    for phrase in fail:
        if phrase in deliverable:
            content_fail.append((0.0, phrase))
    for phrase in uncertain:
        if phrase in deliverable:
            soft.append((0.0, phrase))
    if any(phrase in deliverable for phrase in allowed):
        allowed_hit = True

    if content_fail:
        stamp, phrase = content_fail[0]
        return finish(
            CheckResult(
                item=11,
                key="licensing",
                title=TITLES[11],
                band=3,
                confidence=0.86,
                summary=f"A deliverable or the working file trips a licensing rule ({phrase}).",
                evidence=[Evidence(text=phrase, start=stamp)],
                details={"escalate": False, "phrase": phrase},
            ),
            ctx.rules,
        )
    if soft and not content_fail:
        stamp, phrase = soft[0]
        finding = Finding(
            id="license-uncertain",
            category="unclear_licensing",
            action="ESCALATE",
            confidence=0.73,
            summary=f"Licensing is unclear ({phrase}). Suggest #odin-reviewers-hub rather than a band.",
            evidence=[Evidence(text=phrase, start=stamp)],
            checklist_item=11,
            drives_verdict=True,
        )
        ctx.findings.append(finding)
        return CheckResult(
            item=11,
            key="licensing",
            title=TITLES[11],
            band=None,
            confidence=0.73,
            summary=finding.summary,
            evidence=list(finding.evidence),
            drives_verdict=True,
            details={"escalate": True, "phrase": phrase},
        )
    note = ""
    if browser_fail or logo_only:
        note = " A logo or stock site was only browsed, so it is not a failure."
    if allowed_hit:
        note = " An allowed-license marker is present." + note
    return finish(
        CheckResult(
            item=11,
            key="licensing",
            title=TITLES[11],
            band=1,
            confidence=0.8 if ctx.observations or deliverable else 0.45,
            summary="No licensing problem in the working files." + note,
            details={"escalate": False, "browsing_only": bool(browser_fail or logo_only)},
        ),
        ctx.rules,
    )
