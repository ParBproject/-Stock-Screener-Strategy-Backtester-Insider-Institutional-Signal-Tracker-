"""Transcripts from a sidecar file or, optionally, faster-whisper.

The default backend never downloads weights. A missing model or package
becomes an empty transcript with low confidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from autoqc.audio.diarize import diarize_turns
from autoqc.ingest.submission import Submission
from autoqc.rules.loader import RuleSet


@dataclass
class Word:
    word: str
    start: float
    end: float
    confidence: float = 1.0


@dataclass
class Transcript:
    language: str
    language_confidence: float
    words: list[Word] = field(default_factory=list)
    source: str = "empty"
    notice: str = ""
    turns: list[dict] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(word.word for word in self.words).strip()


def empty_transcript(notice: str = "") -> Transcript:
    return Transcript(language="", language_confidence=0.0, words=[], source="empty", notice=notice)


def transcript_from_mapping(payload: dict, source: str) -> Transcript:
    words = []
    for item in payload.get("words") or []:
        words.append(
            Word(
                word=str(item.get("word") or item.get("text") or "").strip(),
                start=float(item.get("start", 0.0)),
                end=float(item.get("end", item.get("start", 0.0))),
                confidence=float(item.get("confidence", item.get("probability", 1.0))),
            )
        )
    words = [word for word in words if word.word]
    words.sort(key=lambda word: word.start)
    return Transcript(
        language=str(payload.get("language") or ""),
        language_confidence=float(payload.get("language_confidence", 0.0 if not payload.get("language") else 0.9)),
        words=words,
        source=source,
    )


def load_sidecar(path: Path) -> Transcript:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return transcript_from_mapping(payload, source=path.name)


def transcribe_with_whisper(media: Path, *, allow_download: bool) -> Transcript | None:
    """Optional faster-whisper path. Returns None when it cannot run."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    if not allow_download:
        return None
    try:
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segments, info = model.transcribe(str(media), word_timestamps=True, vad_filter=True)
    except Exception:
        return None
    words: list[Word] = []
    for segment in segments:
        for word in getattr(segment, "words", None) or []:
            words.append(
                Word(
                    word=str(word.word).strip(),
                    start=float(word.start),
                    end=float(word.end),
                    confidence=float(getattr(word, "probability", 0.0)),
                )
            )
    language = str(getattr(info, "language", "") or "")
    probability = float(getattr(info, "language_probability", 0.0) or 0.0)
    return Transcript(
        language=language,
        language_confidence=probability,
        words=[word for word in words if word.word],
        source="whisper",
    )


def load_transcript(submission: Submission, rules: RuleSet) -> Transcript:
    if submission.transcript_path and submission.transcript_path.exists():
        try:
            transcript = load_sidecar(submission.transcript_path)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return empty_transcript(f"unreadable transcript file: {submission.transcript_path.name}")
        turns = diarize_turns(submission.recording, rules)
        if turns:
            transcript.turns = turns
        return transcript

    backend = str(rules.get("audio.backend", "auto")).lower()
    allow = bool(rules.get("audio.allow_model_download", False))
    media = submission.recording
    if backend == "whisper" and media is not None:
        result = transcribe_with_whisper(media, allow_download=allow)
        if result is not None:
            return result
        if not allow:
            return empty_transcript("faster-whisper was not run because model download is disabled")
        return empty_transcript("faster-whisper is unavailable or failed")
    return empty_transcript("")
