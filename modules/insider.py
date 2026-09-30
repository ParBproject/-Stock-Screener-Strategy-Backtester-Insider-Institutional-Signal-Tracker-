"""Insider-filing signals that cannot see a trade before it is public.

Yahoo's insider feed reports the transaction date (``Start Date``) and does
not report the SEC filing date. Form 4 is due two business days later. Using
the transaction date as if the print were already public is look-ahead bias.
When a filing date is present it is used instead. A stamp earlier than the
transaction is ignored.
"""

from __future__ import annotations

import pandas as pd

from config import FORM4_BUSINESS_DAY_LAG, THIRTEEN_F_LAG_DAYS

_EMPTY_COLUMNS = [
    "transaction_date",
    "filing_date",
    "insider",
    "side",
    "shares",
    "text",
    "available_date",
]


def filing_available_date(transaction_date, filing_date=None) -> pd.Timestamp:
    """First date a filing may be used. Weekends are skipped; holidays are not."""
    transaction = _naive_day(transaction_date)
    if _is_missing(filing_date):
        return transaction + pd.offsets.BDay(FORM4_BUSINESS_DAY_LAG)
    filed = _naive_day(filing_date)
    if filed < transaction:
        return transaction + pd.offsets.BDay(FORM4_BUSINESS_DAY_LAG)
    return filed


def thirteen_f_public_date(period_end) -> pd.Timestamp:
    """Date a quarter-end 13F holding may be treated as public."""
    return _naive_day(period_end) + pd.Timedelta(days=THIRTEEN_F_LAG_DAYS)


def standardize_transactions(raw: pd.DataFrame | None) -> pd.DataFrame:
    """Map a vendor insider table onto transaction, filing, and public dates."""
    if raw is None or len(raw) == 0:
        return pd.DataFrame(columns=_EMPTY_COLUMNS)
    frame = raw.copy()
    frame.columns = [str(column) for column in frame.columns]
    transaction_col = _first_column(frame, ["transaction_date", "Start Date", "startDate", "Date"])
    filing_col = _first_column(frame, ["filing_date", "Filing Date", "filingDate"])
    insider_col = _first_column(frame, ["insider", "Insider", "filerName"])
    text_col = _first_column(frame, ["Text", "text", "transactionText"])
    action_col = _first_column(frame, ["Transaction", "transaction", "moneyText"])
    shares_col = _first_column(frame, ["Shares", "shares"])
    if transaction_col is None:
        raise ValueError("insider transactions have no transaction date column")

    rows: list[dict] = []
    for as_dict in frame.to_dict(orient="records"):
        transaction_date = as_dict[transaction_col]
        if _is_missing(transaction_date):
            continue
        filing_date = as_dict[filing_col] if filing_col else None
        text = "" if text_col is None else as_dict[text_col]
        action = "" if action_col is None else as_dict[action_col]
        shares = as_dict[shares_col] if shares_col else None
        rows.append(
            {
                "transaction_date": _naive_day(transaction_date),
                "filing_date": None if _is_missing(filing_date) else _naive_day(filing_date),
                "insider": "" if insider_col is None or _is_missing(as_dict[insider_col]) else str(as_dict[insider_col]).strip(),
                "side": classify_side(action, text, shares),
                "shares": shares,
                "text": "" if _is_missing(text) else str(text),
                "available_date": filing_available_date(transaction_date, filing_date),
            }
        )
    if not rows:
        return pd.DataFrame(columns=_EMPTY_COLUMNS)
    return pd.DataFrame(rows)


def classify_side(action, text, shares=None) -> str:
    """Map vendor text to buy, sell, or other.

    Sale words win over purchase words. A positive share count with no
    purchase language is ``other``: the Yahoo feed often leaves the text
    blank or says "Stock Gift", and treating that as a buy inflates the score.
    A negative share count with no text is a sale.
    """
    blob = f"{action or ''} {text or ''}".lower()
    if any(word in blob for word in ("sale", "sell", "sold")):
        return "sell"
    if any(word in blob for word in ("purchase", "buy", "bought")):
        return "buy"
    try:
        amount = float(shares)
    except (TypeError, ValueError):
        return "other"
    if amount < 0:
        return "sell"
    return "other"


def score_filings(transactions: pd.DataFrame, asof, lookback_days: int = 90) -> dict:
    """Score purchases and sales that were already public on ``asof``.

    The number describes filing activity. It is not a return forecast.
    Institutional holdings are not an input.
    """
    decision = _naive_day(asof)
    window_start = decision - pd.Timedelta(days=lookback_days)
    visible = _visible(_prepare(transactions), decision, window_start)
    buyers = _unique_people(visible, "buy")
    sellers = _unique_people(visible, "sell")
    cluster = len(buyers) >= 3
    raw = 50 + 15 * len(buyers) - 15 * len(sellers) + (20 if cluster else 0)
    score = int(max(0, min(100, raw)))
    reasons = []
    if buyers:
        reasons.append(f"{len(buyers)} insider purchase filing(s) public in the window")
    if sellers:
        reasons.append(f"{len(sellers)} insider sale filing(s) public in the window")
    if cluster:
        reasons.append("cluster: 3 or more distinct insiders with public purchase filings")
    if not reasons:
        reasons.append("no insider filings were public in the window")
    return {
        "score": score,
        "label": _label(score),
        "cluster": cluster,
        "buyers": sorted(buyers),
        "sellers": sorted(sellers),
        "reasons": reasons,
        "asof": decision,
    }


def insider_long_signal(
    transactions: pd.DataFrame,
    index: pd.DatetimeIndex,
    lookback_days: int = 90,
) -> pd.Series:
    """1 when a purchase filing is already public and still inside the lookback.

    The series is a close-of-day signal. Trade it with the backtester so the
    fill is the next open.
    """
    frame = _prepare(transactions)
    buys = frame[frame["side"] == "buy"] if len(frame) else frame
    values: list[float] = []
    for timestamp in index:
        decision = _naive_day(timestamp)
        window_start = decision - pd.Timedelta(days=lookback_days)
        if buys.empty:
            values.append(0.0)
            continue
        visible = buys[(buys["available_date"] <= decision) & (buys["available_date"] > window_start)]
        values.append(1.0 if len(visible) else 0.0)
    return pd.Series(values, index=index, dtype=float)


def institutional_visible(holders: pd.DataFrame, asof, period_column: str = "period_end") -> pd.DataFrame:
    """Keep 13F rows whose quarter-end plus 45 days is on or before ``asof``."""
    if holders is None or len(holders) == 0:
        return pd.DataFrame(columns=[] if holders is None else holders.columns)
    if period_column not in holders.columns:
        raise ValueError(f"holders must include {period_column}")
    decision = _naive_day(asof)
    frame = holders.copy()
    public = frame[period_column].map(thirteen_f_public_date)
    return frame.loc[public <= decision].drop(columns=[], errors="ignore")


def _prepare(transactions: pd.DataFrame | None) -> pd.DataFrame:
    if transactions is None or len(transactions) == 0:
        return standardize_transactions(transactions)
    frame = transactions
    if "available_date" not in frame.columns or "side" not in frame.columns:
        frame = standardize_transactions(frame)
    else:
        frame = frame.copy()
        frame["available_date"] = frame["available_date"].map(_naive_day)
    return frame


def _visible(frame: pd.DataFrame, decision: pd.Timestamp, window_start: pd.Timestamp) -> pd.DataFrame:
    if frame.empty:
        return frame
    return frame[(frame["available_date"] <= decision) & (frame["available_date"] > window_start)].copy()


def _unique_people(frame: pd.DataFrame, side: str) -> set[str]:
    if frame.empty or "side" not in frame.columns:
        return set()
    names = frame.loc[frame["side"] == side, "insider"]
    return {str(name).casefold() for name in names if str(name).strip()}


def _label(score: int) -> str:
    if score >= 80:
        return "STRONG BUY"
    if score >= 65:
        return "BUY"
    if score >= 40:
        return "NEUTRAL"
    if score >= 25:
        return "SELL"
    return "STRONG SELL"


def _first_column(frame: pd.DataFrame, names: list[str]) -> str | None:
    for name in names:
        if name in frame.columns:
            return name
    return None


def _is_missing(value) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _naive_day(value) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is not None:
        stamp = stamp.tz_localize(None)
    return stamp.normalize()
