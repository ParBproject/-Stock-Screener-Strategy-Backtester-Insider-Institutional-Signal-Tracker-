"""Draw a small synthetic macOS-like frame for tests and local fixtures."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from autoqc.rules.loader import RuleSet, load_rules
from autoqc.vision.font import draw_text, text_width
from autoqc.vision.layout import menu_and_dock
from autoqc.vision.theme import (
    ARROW,
    BODY,
    BORDER,
    BORDER_PX,
    DOCK_COLOR,
    MENU_COLOR,
    TEXT_DARK,
    TEXT_LIGHT,
    TITLE_ACTIVE,
    TITLE_INACTIVE,
    TITLE_PX,
    WALLPAPER_DEFAULT,
)

DOCK_ICONS = (
    (220, 60, 50),
    (70, 130, 230),
    (80, 180, 90),
    (230, 180, 40),
    (170, 80, 190),
)


@dataclass
class ButtonSpec:
    x: int
    y: int
    w: int
    h: int
    label: str
    fill: tuple[int, int, int] = (214, 214, 218)


@dataclass
class WindowSpec:
    app: str
    title: str
    x: int
    y: int
    w: int
    h: int
    active: bool = False
    z: int = 0
    body_lines: tuple[str, ...] = ()
    buttons: tuple[ButtonSpec, ...] = ()
    body: tuple[int, int, int] = BODY


@dataclass
class FrameSpec:
    width: int = 320
    height: int = 180
    clock: str = "12:00:00"
    dock: str | None = "bottom"
    wallpaper: tuple[int, int, int] = WALLPAPER_DEFAULT
    cursor: tuple[int, int] | None = None
    cursor_kind: str = "default"
    windows: tuple[WindowSpec, ...] = ()
    rules: RuleSet | None = None
    extra_lines: tuple[tuple[int, int, str, tuple[int, int, int]], ...] = field(default_factory=tuple)


def render_frame(spec: FrameSpec) -> np.ndarray:
    rules = spec.rules or load_rules()
    image = np.zeros((spec.height, spec.width, 3), dtype=np.uint8)
    image[:, :] = spec.wallpaper
    menu_h, dock_h = menu_and_dock(spec.height, rules)
    image[:menu_h, :] = MENU_COLOR
    clock_x = max(0, spec.width - text_width(spec.clock) - 2)
    draw_text(image, clock_x, max(0, (menu_h - 7) // 2), spec.clock, TEXT_LIGHT)

    for window in sorted(spec.windows, key=lambda item: item.z):
        _draw_window(image, window)

    if spec.dock == "bottom":
        _draw_dock_bar(image, spec.height - dock_h, 0, spec.width, dock_h, horizontal=True)
    elif spec.dock == "left":
        _draw_dock_bar(image, 0, 0, dock_h, spec.height, horizontal=False)
    elif spec.dock == "right":
        _draw_dock_bar(image, 0, spec.width - dock_h, dock_h, spec.height, horizontal=False)

    for x, y, text, color in spec.extra_lines:
        draw_text(image, x, y, text, color)

    if spec.cursor is not None:
        if spec.cursor_kind == "default":
            _draw_arrow(image, spec.cursor[0], spec.cursor[1])
        else:
            x, y = spec.cursor
            image[y : y + 9, x : x + 9] = (0, 255, 0)
    return image


def _draw_window(image: np.ndarray, window: WindowSpec) -> None:
    x, y, w, h = window.x, window.y, window.w, window.h
    height, width = image.shape[:2]
    x1, y1 = min(width, x + w), min(height, y + h)
    if x1 <= x or y1 <= y:
        return
    image[y:y1, x:x1] = window.body
    thick = BORDER_PX
    image[y : min(y1, y + thick), x:x1] = BORDER
    image[max(y, y1 - thick) : y1, x:x1] = BORDER
    image[y:y1, x : min(x1, x + thick)] = BORDER
    image[y:y1, max(x, x1 - thick) : x1] = BORDER
    title_color = TITLE_ACTIVE if window.active else TITLE_INACTIVE
    text_color = TEXT_LIGHT if window.active else TEXT_DARK
    top = y + thick
    bottom = min(y1 - thick, top + TITLE_PX)
    left = x + thick
    right = x1 - thick
    if bottom > top and right > left:
        image[top:bottom, left:right] = title_color
        label = f"{window.app} - {window.title}" if window.title else window.app
        draw_text(image, left + 3, top + 3, label, text_color)
    body_top = top + TITLE_PX
    for index, line in enumerate(window.body_lines):
        draw_text(image, left + 4, body_top + 4 + index * 10, line, TEXT_DARK)
    for button in window.buttons:
        bx, by = left + button.x, body_top + button.y
        image[by : by + button.h, bx : bx + button.w] = button.fill
        draw_text(image, bx + 4, by + 4, button.label, TEXT_DARK)


def _draw_dock_bar(image, y, x, w, h, horizontal: bool) -> None:
    image[y : y + h, x : x + w] = DOCK_COLOR
    for index, color in enumerate(DOCK_ICONS):
        if horizontal:
            ix = x + 10 + index * 22
            iy = y + max(2, (h - 12) // 2)
            image[iy : iy + 12, ix : ix + 12] = color
        else:
            ix = x + max(2, (w - 12) // 2)
            iy = y + 28 + index * 22
            image[iy : iy + 12, ix : ix + 12] = color


def _draw_arrow(image: np.ndarray, x: int, y: int) -> None:
    height, width = image.shape[:2]
    for row, bits in enumerate(ARROW):
        for col, bit in enumerate(bits):
            if bit == "1":
                yy, xx = y + row, x + col
                if 0 <= yy < height and 0 <= xx < width:
                    image[yy, xx] = (0, 0, 0)
