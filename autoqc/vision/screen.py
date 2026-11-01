"""Deterministic screen parser: windows, Dock, cursor, clicks.

Bounding boxes come from dark window borders. Titles are read with glyph OCR
when that reader can decode them, otherwise with the configured OCR engine.
PySceneDetect and vision-LLM adapters are optional and are not required here.
"""

from __future__ import annotations

import statistics
from itertools import pairwise

import numpy as np

from autoqc.context import FrameImage
from autoqc.models import Action, FrameObservation, WindowBox
from autoqc.rules.loader import RuleSet
from autoqc.vision.layout import menu_and_dock
from autoqc.vision.font import GLYPH_H
from autoqc.vision.ocr import GlyphOcr, binarize, read_band
from autoqc.vision.theme import ARROW, TITLE_PX, WALLPAPER_DEFAULT

_ARROW = np.array([[bit == "1" for bit in row] for row in ARROW], dtype=bool)


def observe_frames(
    frames: list[FrameImage],
    rules: RuleSet,
    ocr,
    goal_text: str = "",
) -> list[FrameObservation]:
    observations: list[FrameObservation] = []
    previous = None
    previous_cursor = None
    for frame in frames:
        obs = _observe_one(frame, rules, ocr, goal_text)
        if previous is not None and obs.cursor is not None and previous_cursor is not None:
            dx = obs.cursor[0] - previous_cursor[0]
            dy = obs.cursor[1] - previous_cursor[1]
            obs.mouse_moving = (dx * dx + dy * dy) ** 0.5 > 4
            _mark_click(obs, previous.rgb if hasattr(previous, "rgb") else None, frame.rgb, ocr)
        previous = frame
        previous_cursor = obs.cursor
        observations.append(obs)
    return observations


def build_actions(observations: list[FrameObservation]) -> list[Action]:
    actions: list[Action] = []
    seen: set[tuple[str, str]] = set()
    for index, obs in enumerate(observations):
        if index == 0:
            for window in obs.windows:
                seen.add((window.app, window.title))
        else:
            for window in obs.windows:
                key = (window.app, window.title)
                if key not in seen:
                    seen.add(key)
                    actions.append(
                        Action(
                            t=obs.t,
                            kind="state_change",
                            app=window.app,
                            target=window.title or window.app,
                            window=window.label,
                            detail="window appeared",
                        )
                    )
        if obs.click:
            front = obs.frontmost_app or ""
            actions.append(
                Action(
                    t=obs.t,
                    kind="click",
                    app=front,
                    target=obs.click_target or "unknown",
                    window=obs.frontmost_title or front,
                    detail="click",
                )
            )
    return actions


def _observe_one(frame: FrameImage, rules: RuleSet, ocr, goal_text: str) -> FrameObservation:
    image = frame.rgb
    height, width = image.shape[:2]
    menu_h, dock_h = menu_and_dock(height, rules)
    windows = _find_windows(image, menu_h, dock_h, ocr)
    _label_roles(windows, goal_text)
    dock_position = _dock_position(image, dock_h)
    cursor, cursor_default = _find_cursor(image)
    front = next((window for window in windows if window.active), None)
    if front is None and windows:
        front = max(windows, key=lambda window: window.z)
    texts = [window.text for window in windows if window.text]
    return FrameObservation(
        t=frame.t,
        width=width,
        height=height,
        dock_visible=dock_position != "absent",
        dock_position=dock_position,
        frontmost_app=front.app if front else None,
        frontmost_title=front.title if front else None,
        windows=windows,
        cursor=cursor,
        cursor_default=cursor_default,
        mouse_moving=False,
        click=False,
        click_target=None,
        ocr_text=" ".join(texts),
        wallpaper_default=_wallpaper_default(image, windows, menu_h, dock_h),
        image_path=frame.path or None,
    )


def _read_text(image: np.ndarray, box: tuple[int, int, int, int], ocr) -> str:
    glyph = GlyphOcr().read(image, box, polarity="auto")
    if len(glyph) >= 2:
        return glyph
    if ocr is None or isinstance(ocr, GlyphOcr):
        return glyph
    return ocr.read(image, box, polarity="auto") or glyph


def _find_windows(image: np.ndarray, menu_h: int, dock_h: int, ocr) -> list[WindowBox]:
    height, width = image.shape[:2]
    dark = image.max(axis=2) < 28
    runs: list[tuple[int, int, int]] = []
    for y in range(menu_h, max(menu_h, height - dock_h)):
        row = dark[y]
        x = 0
        while x < width:
            if not row[x]:
                x += 1
                continue
            end = x + 1
            while end < width and row[end]:
                end += 1
            if end - x >= 36:
                runs.append((y, x, end))
            x = end

    candidates: list[tuple[int, int, int, int]] = []
    for index, (y0, x0, x1) in enumerate(runs):
        for y1, a0, a1 in runs[index + 1 :]:
            if y1 - y0 < 40:
                continue
            if abs(a0 - x0) > 3 or abs(a1 - x1) > 3:
                continue
            span = y1 - y0
            left = dark[y0:y1, x0]
            right = dark[y0:y1, min(width - 1, x1 - 1)]
            if left.size == 0 or float(left.mean()) < 0.35 or float(right.mean()) < 0.35:
                continue
            if span < 40:
                continue
            candidates.append((x0, y0, x1 - x0, y1 - y0))

    unique = _dedupe_rects(candidates)
    windows: list[WindowBox] = []
    for x, y, w, h in unique:
        title = _read_text(image, (x + 4, y + 4, x + w - 4, y + 2 + TITLE_PX), ocr)
        app, name = _split_title(title)
        body_text = _read_text(image, (x + 4, y + TITLE_PX + 4, x + w - 4, y + TITLE_PX + 28), ocr)
        active = _title_is_active(image, x, y, w)
        windows.append(
            WindowBox(
                app=app,
                title=name,
                window_id=f"{app.casefold()}:{x // 8}:{y // 8}",
                x=x,
                y=y,
                w=w,
                h=h,
                z=2 if active else 1,
                active=active,
                text=" ".join(part for part in (title, body_text) if part),
            )
        )
    return windows


def _dedupe_rects(rects: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    ordered = sorted(rects, key=lambda rect: rect[2] * rect[3], reverse=True)
    kept: list[tuple[int, int, int, int]] = []
    for rect in ordered:
        if any(_iou(rect, other) > 0.6 for other in kept):
            continue
        kept.append(rect)
    return kept


def _iou(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x0, y0 = max(ax, bx), max(ay, by)
    x1, y1 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    union = aw * ah + bw * bh - inter
    return inter / union if union else 0.0


def _split_title(text: str) -> tuple[str, str]:
    cleaned = " ".join((text or "").split())
    if " - " in cleaned:
        app, _, title = cleaned.partition(" - ")
        return app.strip(), title.strip()
    return cleaned.strip(), ""


def _title_is_active(image: np.ndarray, x: int, y: int, w: int) -> bool:
    """True when the title bar itself is the focused blue, not a window behind it."""
    band = image[y + 4 : y + 14, x + 4 : max(x + 5, x + w - 4)]
    if band.size == 0:
        return False
    red = band[:, :, 0].astype(np.int16)
    blue = band[:, :, 2].astype(np.int16)
    focused = (blue > 150) & (blue > red + 30)
    return float(focused.mean()) > 0.45


def _label_roles(windows: list[WindowBox], goal_text: str) -> None:
    snippet = " ".join(goal_text.split())[:24].casefold()
    for window in windows:
        blob = f"{window.app} {window.title} {window.text}".casefold()
        window.is_goal = "goal" in blob or (len(snippet) >= 8 and snippet in blob)
    candidates = [window for window in windows if not window.is_goal and window.app.casefold() != "taskrecorder"]
    if not candidates:
        return
    content = max(candidates, key=lambda window: window.area)
    content.is_content = True


def _dock_position(image: np.ndarray, dock_h: int) -> str:
    height, width = image.shape[:2]
    if dock_h <= 0:
        return "absent"
    if _dock_like(image[height - dock_h : height, :]):
        return "bottom"
    if _dock_like(image[:, :dock_h]):
        return "left"
    if _dock_like(image[:, width - dock_h : width]):
        return "right"
    return "absent"


def _dock_like(band: np.ndarray) -> bool:
    if band.size == 0:
        return False
    median = np.median(band.reshape(-1, 3), axis=0)
    # The Dock is a dark bar. A light window or the wallpaper is not.
    if float(median.mean()) > 80:
        return False
    distance = np.abs(band.astype(np.int16) - median).sum(axis=2)
    bright = distance > 90
    fraction = float(bright.mean())
    return int(bright.sum()) > 24 and 0.01 < fraction < 0.5


def _find_cursor(image: np.ndarray) -> tuple[tuple[int, int] | None, bool | None]:
    green = (image[:, :, 1] > 200) & (image[:, :, 0] < 40) & (image[:, :, 2] < 40)
    if int(green.sum()) >= 20:
        ys, xs = np.nonzero(green)
        return (int(xs.mean()), int(ys.mean())), False
    black = image.max(axis=2) < 8
    found = _match_template(black, _ARROW)
    if found is None:
        return None, None
    return found, True


def _match_template(mask: np.ndarray, kernel: np.ndarray) -> tuple[int, int] | None:
    kh, kw = kernel.shape
    height, width = mask.shape
    if height < kh or width < kw:
        return None
    view = np.lib.stride_tricks.sliding_window_view(mask, (kh, kw))
    hits = np.argwhere(np.all(view == kernel, axis=(2, 3)))
    if len(hits) == 0:
        return None
    y, x = (int(hits[0][0]), int(hits[0][1]))
    return x, y


def _wallpaper_default(image, windows: list[WindowBox], menu_h: int, dock_h: int) -> bool:
    height, width = image.shape[:2]
    points = ((8, menu_h + 4), (width - 8, menu_h + 4), (8, height - dock_h - 6))
    for x, y in points:
        if not (0 <= x < width and 0 <= y < height):
            continue
        if any(window.x <= x < window.x + window.w and window.y <= y < window.y + window.h for window in windows):
            continue
        pixel = image[y, x].astype(int)
        return bool(np.max(np.abs(pixel - np.array(WALLPAPER_DEFAULT))) <= 18)
    return False


def _mark_click(obs: FrameObservation, previous: np.ndarray | None, current: np.ndarray, _ocr) -> None:
    if previous is None or obs.cursor is None or previous.shape != current.shape:
        return
    x, y = obs.cursor
    height, width = current.shape[:2]
    x0, y0 = max(0, x - 40), max(0, y - 28)
    x1, y1 = min(width, x + 80), min(height, y + 24)
    before = previous[y0:y1, x0:x1]
    after = current[y0:y1, x0:x1]
    if before.size == 0:
        return
    changed = np.abs(before.astype(np.int16) - after.astype(np.int16)).max(axis=2) > 18
    # Ignore the cursor glyph itself.
    changed[max(0, y - y0) : max(0, y - y0) + 7, max(0, x - x0) : max(0, x - x0) + 5] = False
    if int(changed.sum()) < 12:
        return
    obs.click = True
    obs.click_target = _read_nearest_line(current, x, y) or "unknown"


def _read_nearest_line(image: np.ndarray, x: int, y: int) -> str:
    """Prefer the glyph line closest to the cursor, not the longest line in the crop."""
    height, width = image.shape[:2]
    x0, x1 = max(0, x - 48), min(width, x + 72)
    y0, y1 = max(0, y - 32), min(height, y + 16)
    crop = image[y0:y1, x0:x1]
    binary = binarize(crop, "auto")
    if binary.shape[0] < GLYPH_H or binary.shape[1] < 5:
        return ""
    best = ""
    best_dist = 10**9
    for row in range(binary.shape[0] - GLYPH_H + 1):
        text, score = read_band(binary[row : row + GLYPH_H])
        if score < 2:
            continue
        center = y0 + row + GLYPH_H // 2
        dist = abs(center - y)
        if dist < best_dist:
            best = text
            best_dist = dist
    return best.strip()


def median_dt(times: list[float]) -> float:
    if len(times) < 2:
        return 1.0
    deltas = [b - a for a, b in pairwise(times) if b > a]
    if not deltas:
        return 1.0
    return float(statistics.median(deltas))
