"""Typing-share measurement from consecutive frames.

The share is time-weighted. For each pair of samples at t0 and t1, the
interval counts as typing when the number of changed pixels below the menu
bar and above the Dock is inside the configured band. Large jumps are
treated as navigation, not typing. The resulting ratio is the number the
checklist reports.
"""

from __future__ import annotations

import numpy as np

from autoqc.rules.loader import RuleSet
from autoqc.vision.layout import menu_and_dock


def changed_pixels(
    previous: np.ndarray,
    current: np.ndarray,
    menu_h: int,
    dock_h: int,
    tolerance: int,
) -> int:
    if previous.shape != current.shape:
        return 1_000_000_000
    delta = np.abs(previous.astype(np.int16) - current.astype(np.int16)).max(axis=2)
    mask = delta > tolerance
    height = mask.shape[0]
    if menu_h > 0:
        mask[: min(menu_h, height), :] = False
    if dock_h > 0:
        mask[max(0, height - dock_h) :, :] = False
    return int(mask.sum())


def frame_intervals(frames: list[tuple[float, np.ndarray]], rules: RuleSet) -> list[dict]:
    tolerance = int(rules.get("typing.pixel_tolerance", 18))
    low = int(rules.get("typing.min_changed_pixels", 8))
    high = int(rules.get("typing.max_changed_pixels", 800))
    ordered = sorted(frames, key=lambda item: item[0])
    rows: list[dict] = []
    for (t0, img0), (t1, img1) in zip(ordered, ordered[1:]):
        dt = float(t1) - float(t0)
        if dt <= 0:
            continue
        height = img1.shape[0]
        menu_h, dock_h = menu_and_dock(height, rules)
        changed = changed_pixels(img0, img1, menu_h, dock_h, tolerance)
        typing = low <= changed <= high
        rows.append(
            {
                "start": float(t0),
                "end": float(t1),
                "dt": dt,
                "changed_pixels": changed,
                "typing": typing,
            }
        )
    return rows


def typing_share(intervals: list[dict]) -> tuple[float, float, float]:
    """Return ``(share, typing_seconds, compared_seconds)``."""
    compared = sum(float(row["dt"]) for row in intervals)
    typing = sum(float(row["dt"]) for row in intervals if row["typing"])
    if compared <= 0:
        return 0.0, 0.0, 0.0
    return typing / compared, typing, compared
