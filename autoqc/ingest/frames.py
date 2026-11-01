"""Frame sampling: 1 fps, scene changes, and the first/last seconds at 5 fps.

A submission may also ship pre-extracted frames via ``frames.csv``
(``filename,t`` relative to the submission root). When a video file is
present, ffprobe duration wins and frames are extracted from the video.
"""

from __future__ import annotations

import csv
import re
import statistics
import subprocess
from dataclasses import dataclass
from pathlib import Path

from autoqc.errors import AutoQCError
from autoqc.rules.loader import RuleSet

_PTS = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")


@dataclass
class FrameRef:
    t: float
    path: str
    source: str

    def to_dict(self) -> dict:
        return {"t": self.t, "path": self.path, "source": self.source}


def scene_change_times(video: Path, threshold: float = 0.4) -> list[float]:
    """Scene cuts from ffmpeg's scene filter. Times are seconds from the start."""
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-i",
        str(video),
        "-vf",
        f"select='gt(scene,{threshold})',showinfo",
        "-f",
        "null",
        "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AutoQCError(f"ffmpeg scene detection failed: {exc}") from exc
    times = [float(match.group(1)) for match in _PTS.finditer(proc.stderr)]
    # Drop a cut reported at t=0; that is the opening frame, not a change.
    return sorted({round(t, 3) for t in times if t > 0.05})


def scene_change_times_pyscenedetect(video: Path) -> list[float] | None:
    """Optional PySceneDetect backend. Returns None when the package is missing."""
    try:
        from scenedetect import ContentDetector, SceneManager, open_video
    except ImportError:
        return None
    try:
        stream = open_video(str(video))
        manager = SceneManager()
        manager.add_detector(ContentDetector())
        manager.detect_scenes(stream)
        scenes = manager.get_scene_list()
    except Exception:
        return None
    times: list[float] = []
    for index, (start, _end) in enumerate(scenes):
        if index == 0:
            continue
        times.append(float(start.get_seconds()))
    return times


def _ffmpeg(cmd: list[str]) -> None:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AutoQCError(f"ffmpeg failed: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "ffmpeg failed").strip()
        raise AutoQCError(detail.splitlines()[-1] if detail else "ffmpeg failed")


def _extract_rate(
    video: Path,
    dest: Path,
    fps: float,
    origin: float,
    start: float | None,
    end: float | None,
    max_width: int,
) -> list[tuple[float, Path]]:
    dest.mkdir(parents=True, exist_ok=True)
    for stale in dest.glob("*.png"):
        stale.unlink()
    scale = f"scale='min({int(max_width)},iw)':-2"
    vf = f"fps={fps},{scale}"
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(video)]
    if start is not None:
        cmd.extend(["-ss", f"{start:.3f}"])
    if end is not None:
        cmd.extend(["-to", f"{end:.3f}"])
    cmd.extend(["-vf", vf, str(dest / "%05d.png")])
    _ffmpeg(cmd)
    frames = []
    for index, path in enumerate(sorted(dest.glob("*.png"))):
        frames.append((origin + index / fps, path))
    return frames


def _extract_still(video: Path, dest: Path, t: float, max_width: int) -> Path | None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    scale = f"scale='min({int(max_width)},iw)':-2"
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video),
        "-ss",
        f"{t:.3f}",
        "-frames:v",
        "1",
        "-vf",
        scale,
        str(dest),
    ]
    try:
        _ffmpeg(cmd)
    except AutoQCError:
        return None
    return dest if dest.exists() else None


def _dedupe(frames: list[FrameRef], window: float = 0.05) -> list[FrameRef]:
    ordered = sorted(frames, key=lambda frame: (frame.t, frame.source))
    kept: list[FrameRef] = []
    for frame in ordered:
        if kept and abs(frame.t - kept[-1].t) < window:
            continue
        kept.append(frame)
    return kept


def extract_video_frames(video: Path, dest: Path, duration: float, rules: RuleSet) -> tuple[list[FrameRef], list[float]]:
    max_width = int(rules.get("ingest.analysis_max_width", 640))
    base_fps = float(rules.get("ingest.base_fps", 1))
    edge_fps = float(rules.get("ingest.edge_fps", 5))
    edge_s = float(rules.get("ingest.edge_seconds", 10))
    threshold = float(rules.get("ingest.scene_threshold", 0.4))
    backend = str(rules.get("ingest.scene_backend", "ffmpeg")).lower()

    dest.mkdir(parents=True, exist_ok=True)
    scene_dir = dest / "scene"
    if scene_dir.exists():
        for stale in scene_dir.glob("*.png"):
            stale.unlink()

    collected: list[FrameRef] = []
    for t, path in _extract_rate(video, dest / "1fps", base_fps, 0.0, None, None, max_width):
        collected.append(FrameRef(t=t, path=str(path), source="1fps"))

    edge_end = min(edge_s, duration)
    for t, path in _extract_rate(video, dest / "start", edge_fps, 0.0, 0.0, edge_end, max_width):
        collected.append(FrameRef(t=t, path=str(path), source="edge"))

    if duration > edge_s:
        start = max(0.0, duration - edge_s)
        for t, path in _extract_rate(video, dest / "end", edge_fps, start, start, duration, max_width):
            collected.append(FrameRef(t=t, path=str(path), source="edge"))

    scene_times: list[float] = []
    if backend in {"pyscenedetect", "auto"}:
        detected = scene_change_times_pyscenedetect(video)
        if detected is not None:
            scene_times = detected
    if backend in {"ffmpeg", "auto"} and not scene_times:
        scene_times = scene_change_times(video, threshold)

    for index, t in enumerate(scene_times):
        still = _extract_still(video, dest / "scene" / f"{index:04d}.png", t, max_width)
        if still is not None:
            collected.append(FrameRef(t=t, path=str(still), source="scene"))

    return _dedupe(collected), scene_times


def load_frames_csv(root: Path, csv_path: Path) -> list[FrameRef]:
    frames: list[FrameRef] = []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or "t" not in reader.fieldnames:
            raise AutoQCError(f"{csv_path.name} needs a header with filename and t")
        name_key = "filename" if "filename" in reader.fieldnames else "file"
        if name_key not in reader.fieldnames:
            raise AutoQCError(f"{csv_path.name} needs a filename column")
        for row in reader:
            raw_name = (row.get(name_key) or "").strip()
            if not raw_name:
                continue
            path = Path(raw_name)
            if not path.is_absolute():
                path = root / path
            try:
                t = float(row["t"])
            except (TypeError, ValueError) as exc:
                raise AutoQCError(f"bad timestamp in {csv_path.name}: {row.get('t')!r}") from exc
            if not path.exists():
                raise AutoQCError(f"frame listed in {csv_path.name} is missing: {raw_name}")
            frames.append(FrameRef(t=t, path=str(path), source="bundle"))
    if not frames:
        raise AutoQCError(f"{csv_path.name} has no frames")
    return sorted(frames, key=lambda frame: frame.t)


def infer_duration(frames: list[FrameRef], override: float | None) -> float:
    if not frames:
        if override is None:
            return 0.0
        return float(override)
    last = max(frame.t for frame in frames)
    if override is not None:
        if float(override) + 1e-6 < last:
            raise AutoQCError("duration_seconds is earlier than the last frame")
        return float(override)
    times = sorted(frame.t for frame in frames)
    if len(times) == 1:
        return max(last, 1.0)
    deltas = [b - a for a, b in zip(times, times[1:]) if b > a]
    step = statistics.median(deltas) if deltas else 1.0
    return last + step
