"""ffprobe wrapper. Duration from a real recording is authoritative."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from autoqc.errors import AutoQCError


@dataclass
class MediaInfo:
    path: str | None
    duration: float
    width: int | None
    height: int | None
    fps: float | None
    video_codec: str | None
    audio_codec: str | None
    has_audio: bool
    sample_rate: int | None
    source: str

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "duration": self.duration,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
            "has_audio": self.has_audio,
            "sample_rate": self.sample_rate,
            "source": self.source,
        }


def _parse_fps(value: str | None) -> float | None:
    if not value or value == "0/0":
        return None
    if "/" in value:
        numer, denom = value.split("/", 1)
        if float(denom) == 0:
            return None
        return float(numer) / float(denom)
    return float(value)


def probe_video(path: Path) -> MediaInfo:
    if not path.exists():
        raise AutoQCError(f"recording not found: {path}")
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AutoQCError(f"ffprobe failed for {path.name}: {exc}") from exc
    if proc.returncode != 0:
        detail = proc.stderr.strip() or "ffprobe failed"
        raise AutoQCError(detail)
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise AutoQCError(f"ffprobe returned invalid JSON for {path.name}") from exc

    duration = float(payload.get("format", {}).get("duration") or 0.0)
    width = height = None
    fps = None
    video_codec = None
    audio_codec = None
    has_audio = False
    sample_rate = None
    for stream in payload.get("streams", []):
        kind = stream.get("codec_type")
        if kind == "video" and width is None:
            width = stream.get("width")
            height = stream.get("height")
            video_codec = stream.get("codec_name")
            fps = _parse_fps(stream.get("r_frame_rate"))
        elif kind == "audio" and not has_audio:
            has_audio = True
            audio_codec = stream.get("codec_name")
            if stream.get("sample_rate"):
                sample_rate = int(stream["sample_rate"])
    if width is None:
        raise AutoQCError(f"{path.name} has no video stream")
    return MediaInfo(
        path=str(path),
        duration=duration,
        width=int(width) if width else None,
        height=int(height) if height else None,
        fps=fps,
        video_codec=video_codec,
        audio_codec=audio_codec,
        has_audio=has_audio,
        sample_rate=sample_rate,
        source="ffprobe",
    )
