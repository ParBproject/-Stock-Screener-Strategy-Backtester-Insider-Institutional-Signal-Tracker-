"""Point-in-time fundamental snapshots.

A row is visible only when ``available_date`` is on or before the decision
date. ``period_end`` is the fiscal period, not the public release, and is
rejected so a backtest cannot treat an unreported quarter as known.
"""

from __future__ import annotations

import pandas as pd


def latest_released(filings: pd.DataFrame, asof) -> pd.Series | None:
    """Return the latest filing whose public date is on or before ``asof``."""
    if "available_date" not in filings.columns:
        if "period_end" in filings.columns:
            raise ValueError(
                "period_end is not a public release date; pass available_date "
                "(the filing date, or the session after it)"
            )
        raise ValueError("filings must include available_date")

    decision = _naive_day(asof)
    frame = filings.copy()
    published = frame["available_date"].map(_naive_day)
    known = frame.loc[published <= decision].copy()
    if known.empty:
        return None
    known = known.assign(_published=published.loc[known.index])
    sort_by = ["_published"]
    if "period_end" in known.columns:
        # Same public date: the later fiscal period is the newer report.
        known["_period_end"] = known["period_end"].map(_naive_day)
        sort_by.append("_period_end")
    known["_order"] = range(len(known))
    sort_by.append("_order")
    known = known.sort_values(sort_by, kind="mergesort")
    drop = [column for column in ("_published", "_period_end", "_order") if column in known.columns]
    return known.drop(columns=drop).iloc[-1]


def _naive_day(value) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is not None:
        stamp = stamp.tz_localize(None)
    return stamp.normalize()
