"""Shared menu-bar and Dock band sizes.

The clock reader and the typing detector both use these heights so a
synthetic frame and the checker agree on which rows are chrome.
"""

from __future__ import annotations

from autoqc.rules.loader import RuleSet


def menu_and_dock(height: int, rules: RuleSet) -> tuple[int, int]:
    menu = max(
        int(rules.get("layout.menu_bar_min_px", 12)),
        int(round(height * float(rules.get("layout.menu_bar_height_fraction", 0.08)))),
    )
    dock = max(
        int(rules.get("layout.dock_min_px", 16)),
        int(round(height * float(rules.get("layout.dock_height_fraction", 0.10)))),
    )
    if height <= 0:
        return 0, 0
    if menu + dock >= height:
        menu = max(1, height // 10)
        dock = max(1, height // 12)
        if menu + dock >= height:
            return 0, 0
    return menu, dock
