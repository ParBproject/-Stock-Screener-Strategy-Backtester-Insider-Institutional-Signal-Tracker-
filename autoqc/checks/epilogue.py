"""Checklist item 14: the closing epilogue.

Missing does not block approval. Ideas first approved before 6pm Pacific on
Oct 19, 2026 do not need one.
"""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from autoqc.audio.transcribe import Transcript
from autoqc.checks.common import TITLES, finish
from autoqc.context import ReviewContext
from autoqc.models import CheckResult, Evidence
from autoqc.timefmt import fmt_ts

_PACIFIC = ZoneInfo("America/Los_Angeles")
_TOPICS = {
    "verification": ("verify", "verified", "verification", "checked"),
    "approach": ("approach", "method"),
    "challenges": ("challenge", "challenges", "difficult", "stuck"),
    "quality": ("quality", "polish"),
    "reflections": ("reflect", "reflection", "learned", "hindsight"),
}
_MISSING = "Missing epilogue - does not block approval"


def _required(ctx: ReviewContext) -> bool:
    approved = ctx.submission.idea_first_approved_at
    raw = str(ctx.rules.get("epilogue.not_required_before", "2026-10-19T18:00:00-07:00"))
    cutoff = datetime.fromisoformat(raw)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=_PACIFIC)
    if approved is None:
        return True
    if approved.tzinfo is None:
        approved = approved.replace(tzinfo=_PACIFIC)
    return approved >= cutoff


def _token(text: str) -> str:
    return re.sub(r"[^a-z']", "", text.lower())


def _epilogue(words, duration: float):
    tokens = [(word.start, _token(word.word)) for word in words]
    hits: list[tuple[float, str]] = []
    for index, (start, token) in enumerate(tokens):
        if not token:
            continue
        for topic, cues in _TOPICS.items():
            if token in cues:
                hits.append((start, topic))
        if token == "next" and index + 1 < len(tokens) and tokens[index + 1][1] == "time":
            hits.append((start, "reflections"))
    late = [hit for hit in hits if hit[0] >= duration * 0.4]
    if not late:
        return None
    start = min(item[0] for item in late)
    topics = {topic for stamp, topic in late if stamp >= start}
    count = sum(1 for word in words if word.start >= start - 0.05)
    return start, topics, count


def score_epilogue(ctx: ReviewContext) -> CheckResult:
    if not _required(ctx):
        return finish(
            CheckResult(
                item=14,
                key="epilogue",
                title=TITLES[14],
                band=None,
                confidence=0.95,
                summary="Epilogue not required (idea first approved before Oct 19, 2026, 6pm PT).",
                unscored_reason="Epilogue not required (idea first approved before Oct 19, 2026, 6pm PT).",
            ),
            ctx.rules,
        )
    transcript = ctx.transcript if isinstance(ctx.transcript, Transcript) else None
    words = transcript.words if transcript else []
    duration = float(ctx.submission.media.duration or 0.0)
    if words:
        duration = max(duration, words[-1].end)
    found = _epilogue(words, duration) if words else None
    if found is None:
        return finish(
            CheckResult(
                item=14,
                key="epilogue",
                title=TITLES[14],
                band=None,
                confidence=0.8 if words else 0.4,
                summary=_MISSING,
                unscored_reason=_MISSING,
            ),
            ctx.rules,
        )
    start, topics, count = found
    length = max(0.0, duration - start)
    limit = float(ctx.rules.get("epilogue.max_seconds", 240))
    detail_words = int(ctx.rules.get("epilogue.min_words_detail", 40))
    detail_topics = int(ctx.rules.get("epilogue.min_topics_detail", 3))
    thin_words = int(ctx.rules.get("epilogue.thin_word_count", 25))
    detailed = count >= detail_words and len(topics) >= detail_topics
    thin = count < thin_words or len(topics) < 2
    evidence = [
        Evidence(
            text=f"Epilogue topics: {', '.join(sorted(topics)) or 'none'}. {count} words, {fmt_ts(length)} long.",
            start=start,
            end=duration,
        )
    ]
    if length <= limit and detailed:
        band = 1
        summary = f"Epilogue is {fmt_ts(length)} and covers the close in enough detail."
    else:
        band = 2
        if length > limit:
            summary = f"Epilogue runs {fmt_ts(length)}, over the 4:00 mark."
        else:
            summary = "Epilogue is thin: add more on verification, approach, challenges, quality, or reflection."
    return finish(
        CheckResult(
            item=14,
            key="epilogue",
            title=TITLES[14],
            band=band,
            confidence=0.82,
            summary=summary,
            evidence=evidence,
            details={
                "seconds": length,
                "words": count,
                "topics": sorted(topics),
                "thin": thin,
                "detailed": detailed,
                "blocks_approval": False,
            },
        ),
        ctx.rules,
    )
