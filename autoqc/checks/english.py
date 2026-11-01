"""Checklist item 13: narration is English and text deliverables are English.

Minor non-English text on screen is ignored. A missing optional transcript
does not by itself fail the item; that case stays low confidence for a human.
A text deliverable that cannot be decoded, or narration that is confidently
not English, is band 3.
"""

from __future__ import annotations

import re
import zipfile

from autoqc.audio.transcribe import Transcript
from autoqc.checks.common import TITLES, finish
from autoqc.context import ReviewContext
from autoqc.models import CheckResult, Evidence

_TEXT_EXT = {".txt", ".md", ".markdown", ".csv", ".html", ".py", ".js", ".ts", ".css", ".json"}
_COMMON = frozenset(
    """
    a about after all also an and any are as at be because been before but by can
    could did do does for from get go had has have he her here him his how i if in
    into is it its just like made make me more my no not now of on one or our out
    she so some than that the their them then there these they this to too up was
    we were what when where which who will with would you your
    the file document page chart table text image video code open save export
    click button budget final ready review complete next previous
    """.split()
)


def english_ratio(text: str) -> float | None:
    tokens = re.findall(r"[A-Za-z']{2,}", text.lower())
    if len(tokens) < 6:
        return None
    return sum(1 for token in tokens if token in _COMMON) / len(tokens)


def _deliverable_texts(ctx: ReviewContext) -> tuple[list[tuple[str, str]], list[str]]:
    path = ctx.submission.zip_path
    if path is None or not path.exists():
        return [], []
    texts = []
    unreadable = []
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        return [], ["deliverables.zip"]
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            suffix = "." + info.filename.rsplit(".", 1)[-1].lower() if "." in info.filename else ""
            if suffix not in _TEXT_EXT:
                continue
            raw = archive.read(info)
            try:
                texts.append((info.filename, raw.decode("utf-8")))
            except UnicodeDecodeError:
                unreadable.append(info.filename)
    return texts, unreadable


def score_english(ctx: ReviewContext) -> CheckResult:
    minimum = float(ctx.rules.get("english.min_language_confidence", 0.75))
    ratio_min = float(ctx.rules.get("english.min_word_ratio", 0.45))
    transcript = ctx.transcript if isinstance(ctx.transcript, Transcript) else None
    language = (transcript.language if transcript else "") or ""
    language_confidence = transcript.language_confidence if transcript else 0.0
    texts, unreadable = _deliverable_texts(ctx)
    evidence: list[Evidence] = []

    narration_bad = bool(language) and language.lower() not in {"en", "english"} and language_confidence >= minimum
    narration_ok = bool(language) and language.lower() in {"en", "english"} and language_confidence >= minimum
    narration_unknown = not narration_ok and not narration_bad

    bad_files = []
    for name, text in texts:
        ratio = english_ratio(text)
        if ratio is None or ratio < ratio_min:
            bad_files.append(name)
            evidence.append(Evidence(text=f"{name} does not look like English." if ratio is not None else f"{name} could not be checked."))
    for name in unreadable:
        bad_files.append(name)
        evidence.append(Evidence(text=f"{name} could not be decoded as text."))

    if narration_bad or bad_files or unreadable:
        summary = "Narration or a text deliverable is not English, or it could not be verified."
        if narration_bad:
            summary = f"Narration language is {language}, not English."
        elif bad_files:
            summary = "A text deliverable is not English or could not be verified: " + ", ".join(bad_files) + "."
        return finish(
            CheckResult(
                item=13,
                key="english",
                title=TITLES[13],
                band=3,
                confidence=0.84,
                summary=summary,
                evidence=evidence,
                details={"language": language, "language_confidence": language_confidence},
            ),
            ctx.rules,
        )

    if narration_unknown and not texts:
        return finish(
            CheckResult(
                item=13,
                key="english",
                title=TITLES[13],
                band=None,
                confidence=0.36,
                summary="English could not be verified because there is no transcript and no text deliverable.",
                details={"language": language, "language_confidence": language_confidence},
            ),
            ctx.rules,
        )

    if narration_unknown and texts:
        # Deliverable text passed the word-ratio check above (bad_files empty).
        return finish(
            CheckResult(
                item=13,
                key="english",
                title=TITLES[13],
                band=1,
                confidence=0.62,
                summary="Text deliverables look English. Narration language was not identified.",
                details={"language": language or "unknown", "language_confidence": language_confidence},
            ),
            ctx.rules,
        )

    return finish(
        CheckResult(
            item=13,
            key="english",
            title=TITLES[13],
            band=1,
            confidence=0.88,
            summary="Narration is English and the text deliverables that could be read are English.",
            details={"language": language or "en", "language_confidence": language_confidence},
        ),
        ctx.rules,
    )
