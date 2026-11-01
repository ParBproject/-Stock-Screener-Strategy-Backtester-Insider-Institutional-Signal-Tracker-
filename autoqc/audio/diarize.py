"""Optional pyannote diarization. Missing package or token is a no-op."""

from __future__ import annotations

import os
from pathlib import Path

from autoqc.rules.loader import RuleSet


def diarize_turns(media: Path | None, rules: RuleSet) -> list[dict] | None:
    """Return speaker turns, or None when diarization is off or unavailable."""
    if not bool(rules.get("audio.diarize", False)):
        return None
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if not token or media is None or not media.exists():
        return None
    try:
        from pyannote.audio import Pipeline
    except ImportError:
        return None
    try:
        pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", token=token)
        annotation = pipeline(str(media))
    except Exception:
        return None
    turns = []
    for segment, _, speaker in annotation.itertracks(yield_label=True):
        turns.append({"start": float(segment.start), "end": float(segment.end), "speaker": str(speaker)})
    return turns
