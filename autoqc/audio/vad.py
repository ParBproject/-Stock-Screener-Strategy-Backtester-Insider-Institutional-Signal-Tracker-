"""Speech spans. Energy detection always works; webrtcvad is optional."""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path


def _rms16(raw: bytes) -> int:
    count = len(raw) // 2
    if count == 0:
        return 0
    samples = struct.unpack("<" + "h" * count, raw[: count * 2])
    square = sum(sample * sample for sample in samples) / count
    return int(math.sqrt(square))


def energy_speech_spans(
    path: Path,
    frame_ms: int = 30,
    threshold: int = 800,
) -> list[tuple[float, float]]:
    """Return ``[(start, end), ...]`` seconds of frames above ``threshold`` RMS."""
    try:
        handle = wave.open(str(path), "rb")
    except (OSError, wave.Error):
        return []
    with handle:
        rate = handle.getframerate() or 16000
        width = handle.getsampwidth() or 2
        channels = handle.getnchannels() or 1
        if width != 2 or channels != 1:
            return []
        frame_n = max(1, int(rate * frame_ms / 1000))
        spans: list[tuple[float, float]] = []
        index = 0
        open_at: float | None = None
        while True:
            raw = handle.readframes(frame_n)
            if not raw:
                break
            rms = _rms16(raw)
            t = index * frame_n / rate
            if rms >= threshold and open_at is None:
                open_at = t
            elif rms < threshold and open_at is not None:
                spans.append((open_at, t))
                open_at = None
            index += 1
        if open_at is not None:
            spans.append((open_at, index * frame_n / rate))
    return spans


def webrtc_speech_spans(path: Path) -> list[tuple[float, float]] | None:
    try:
        import webrtcvad
    except ImportError:
        return None
    try:
        handle = wave.open(str(path), "rb")
    except (OSError, wave.Error):
        return None
    with handle:
        if handle.getnchannels() != 1 or handle.getsampwidth() != 2:
            return None
        rate = handle.getframerate()
        if rate not in {8000, 16000, 32000, 48000}:
            return None
        vad = webrtcvad.Vad(2)
        frame_n = int(rate * 0.03)
        spans: list[tuple[float, float]] = []
        index = 0
        open_at: float | None = None
        while True:
            raw = handle.readframes(frame_n)
            if len(raw) < frame_n * 2:
                break
            t = index * 0.03
            voiced = vad.is_speech(raw, rate)
            if voiced and open_at is None:
                open_at = t
            elif not voiced and open_at is not None:
                spans.append((open_at, t))
                open_at = None
            index += 1
        if open_at is not None:
            spans.append((open_at, index * 0.03))
    return spans


def speech_spans(path: Path | None, backend: str = "auto") -> list[tuple[float, float]]:
    if path is None or not path.exists():
        return []
    mode = (backend or "auto").lower()
    if mode in {"auto", "webrtcvad"}:
        detected = webrtc_speech_spans(path)
        if detected is not None:
            return detected
    if mode == "off":
        return []
    return energy_speech_spans(path)
