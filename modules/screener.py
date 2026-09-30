"""Cross-sectional filters.

Criteria match ``config.PRESETS``. Compared values are already in display
units: ratios such as P/E stay as ratios, and ROE, yields, and growth are in
percent (10 means 10%). A missing value fails a constraint instead of passing
through it. This module does not fetch data and does not look backward.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

# (column, operator). "le" keeps rows at or below the cutoff.
FILTER_SPEC = {
    "max_pe": ("pe", "le"),
    "min_roe": ("roe", "ge"),
    "max_pb": ("pb", "le"),
    "min_div_yield": ("div_yield", "ge"),
    "max_debt_equity": ("debt_equity", "le"),
    "min_revenue_growth": ("revenue_growth", "ge"),
    "min_earnings_growth": ("earnings_growth", "ge"),
    "max_payout_ratio": ("payout_ratio", "le"),
    "min_market_cap": ("market_cap", "ge"),
    "min_price_change_52w": ("price_change_52w", "ge"),
    "min_rsi": ("rsi", "ge"),
    "max_rsi": ("rsi", "le"),
    "min_volume": ("volume", "ge"),
    "min_profit_margin": ("profit_margin", "ge"),
}


def apply_filters(frame: pd.DataFrame, criteria: Mapping) -> pd.DataFrame:
    """Return rows that satisfy every criterion. Unknown keys raise."""
    mask = pd.Series(True, index=frame.index)
    for key, cutoff in criteria.items():
        if key not in FILTER_SPEC:
            raise KeyError(f"Unknown screen criterion: {key}")
        column, operator = FILTER_SPEC[key]
        if column not in frame.columns:
            raise KeyError(f"Screen is missing column: {column}")
        values = pd.to_numeric(frame[column], errors="coerce")
        if operator == "le":
            passed = values <= cutoff
        else:
            passed = values >= cutoff
        mask &= passed.fillna(False)
    return frame.loc[mask].copy()
