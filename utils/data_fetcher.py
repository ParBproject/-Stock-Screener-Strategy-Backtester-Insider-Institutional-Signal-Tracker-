"""yfinance access with retries and a one-hour Streamlit cache.

Network calls live here so tests can replace ``yfinance`` without rendering
the app. Adjusted prices are requested on purpose: raw closes jump on splits
and omit dividends, which would distort return math. The ``end`` date passed
by callers is inclusive; Yahoo's ``end`` is exclusive, so one day is added
before download.
"""

from __future__ import annotations

import time

import pandas as pd
import yfinance as yf

_OHLCV = ["open", "high", "low", "close", "volume"]
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class DataFetchError(Exception):
    """A market-data request failed or returned nothing usable."""


def fetch_price_history(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Daily OHLCV from ``start`` through ``end``, inclusive.

    Prices are split- and dividend-adjusted (``auto_adjust=True``).
    """
    symbol = _clean_ticker(ticker)
    start_text = pd.Timestamp(start).strftime("%Y-%m-%d")
    end_exclusive = (pd.Timestamp(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    def _download():
        raw = yf.download(
            symbol,
            start=start_text,
            end=end_exclusive,
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        frame = normalize_ohlcv(raw)
        if frame.empty:
            raise DataFetchError(f"No price history for {symbol}.")
        return frame

    return call_with_retry(_download)


def fetch_realtime_price(ticker: str) -> dict:
    """Last close and the prior close from a short daily history."""
    end = pd.Timestamp.today().normalize()
    start = end - pd.Timedelta(days=14)
    history = fetch_price_history(ticker, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    price = float(history["close"].iloc[-1])
    previous = float(history["close"].iloc[-2]) if len(history) > 1 else None
    return {"price": price, "prev_close": previous, "market_cap": None}


def fetch_fundamentals(ticker: str) -> dict:
    """Latest Yahoo snapshot. This is not a historical filing."""
    symbol = _clean_ticker(ticker)

    def _load():
        info = yf.Ticker(symbol).info or {}
        if not info:
            raise DataFetchError(f"No fundamentals for {symbol}.")
        normalized = normalize_yahoo_info(info)
        if all(value is None for value in normalized.values()):
            raise DataFetchError(f"No fundamentals for {symbol}.")
        return normalized

    return call_with_retry(_load)


def fetch_insider_transactions(ticker: str) -> pd.DataFrame:
    """Vendor insider table. An empty table is a valid result."""
    from modules.insider import standardize_transactions

    symbol = _clean_ticker(ticker)

    def _load():
        raw = yf.Ticker(symbol).insider_transactions
        return standardize_transactions(raw)

    return call_with_retry(_load)


def fetch_institutional_holders(ticker: str) -> pd.DataFrame:
    """Latest institutional-holder snapshot. Not a point-in-time history."""
    symbol = _clean_ticker(ticker)

    def _load():
        raw = yf.Ticker(symbol).institutional_holders
        if raw is None:
            return pd.DataFrame()
        return raw

    return call_with_retry(_load)


def normalize_ohlcv(frame: pd.DataFrame | None) -> pd.DataFrame:
    """Lower-case a single-symbol Yahoo price frame and drop incomplete bars."""
    if frame is None or len(frame) == 0:
        return pd.DataFrame(columns=_OHLCV)
    out = frame.copy()
    if isinstance(out.columns, pd.MultiIndex):
        chosen = None
        for level in range(out.columns.nlevels):
            labels = {str(value).lower() for value in out.columns.get_level_values(level)}
            if "open" in labels and "close" in labels:
                chosen = out.columns.get_level_values(level)
                break
        out.columns = chosen if chosen is not None else [
            "_".join(str(part) for part in column if str(part)) for column in out.columns
        ]
    out.columns = [str(column).strip().lower().replace(" ", "_") for column in out.columns]
    for column in ("open", "high", "low", "close", "adj_close", "volume"):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    # A raw Yahoo frame has Close and Adj Close. Using the raw close across a
    # split books a crash that did not happen. auto_adjust already folds this
    # ratio in; if both columns are still here, do it before the backtest.
    if "adj_close" in out.columns and "close" in out.columns:
        raw_close = out["close"].mask(out["close"] == 0)
        factor = out["adj_close"] / raw_close
        for column in ("open", "high", "low"):
            if column in out.columns:
                out[column] = out[column] * factor
        out["close"] = out["adj_close"]
    elif "close" not in out.columns and "adj_close" in out.columns:
        out = out.rename(columns={"adj_close": "close"})
    keep = [column for column in _OHLCV if column in out.columns]
    out = out.loc[:, keep]
    if isinstance(out.index, pd.DatetimeIndex) and out.index.tz is not None:
        out.index = out.index.tz_localize(None)
    required = [column for column in ("open", "close") if column in out.columns]
    if required:
        out = out.dropna(subset=required)
    return out


def normalize_yahoo_info(info: dict) -> dict:
    """Map a Yahoo ``info`` dict into screen columns.

    Growth, margins, and payout ratio on Yahoo's quote summary are fractions
    (0.015 means 1.5%) and are stored as percents. ``dividendYield`` is
    already a percent (AAPL prints 0.32, meaning 0.32%). ``trailingAnnualDividendYield``
    is the fraction (about 0.003) and is not used. ``debtToEquity`` is a
    percent (150 means 1.50x) and is stored as a ratio. Screen presets use
    those units.
    """
    return {
        "name": _text(info.get("shortName") or info.get("longName")),
        "pe": _number(info.get("trailingPE")),
        "forward_pe": _number(info.get("forwardPE")),
        "peg": _number(info.get("pegRatio") if info.get("pegRatio") is not None else info.get("trailingPegRatio")),
        "pb": _number(info.get("priceToBook")),
        "ps": _number(info.get("priceToSalesTrailing12Months")),
        "roe": _percent_from_fraction(info.get("returnOnEquity")),
        "roa": _percent_from_fraction(info.get("returnOnAssets")),
        "profit_margin": _percent_from_fraction(info.get("profitMargins")),
        "operating_margin": _percent_from_fraction(info.get("operatingMargins")),
        "revenue_growth": _percent_from_fraction(info.get("revenueGrowth")),
        "earnings_growth": _percent_from_fraction(info.get("earningsGrowth")),
        "div_yield": _number(info.get("dividendYield")),
        "payout_ratio": _percent_from_fraction(info.get("payoutRatio")),
        "debt_equity": _debt_to_equity_ratio(info.get("debtToEquity")),
        "market_cap": _number(info.get("marketCap")),
        "beta": _number(info.get("beta")),
        "volume": _number(info.get("averageVolume")),
        "price_change_52w": _percent_from_fraction(info.get("52WeekChange")),
    }


def call_with_retry(fn, *, attempts: int = 3, sleep=None, base_delay: float = 0.5):
    """Retry rate limits and dropped connections. Other errors fail immediately."""
    if sleep is None:
        sleep = time.sleep
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    last_error = None
    for attempt in range(attempts):
        try:
            return fn()
        except DataFetchError:
            raise
        except Exception as exc:
            last_error = exc
            if not _retryable(exc) or attempt == attempts - 1:
                raise DataFetchError(_public_message(exc)) from exc
            sleep(base_delay * (2 ** attempt))
    raise DataFetchError("Market data request failed.") from last_error


def _retryable(exc: Exception) -> bool:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in _RETRYABLE_STATUS:
        return True
    text = f"{type(exc).__name__} {exc}".lower()
    markers = ("429", "rate limit", "too many requests", "timeout", "timed out", "temporarily", "connection")
    return any(marker in text for marker in markers)


def _public_message(exc: Exception) -> str:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    text = str(exc).lower()
    if status == 429 or "429" in text or "rate limit" in text or "too many requests" in text:
        return "Market data is rate-limiting requests. Wait a moment and try again."
    return "Market data request failed. Try again in a moment."


def _clean_ticker(ticker: str) -> str:
    symbol = str(ticker).strip().upper()
    if not symbol:
        raise DataFetchError("Ticker is empty.")
    return symbol


def _number(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _percent_from_fraction(value):
    number = _number(value)
    if number is None:
        return None
    return number * 100.0


def _debt_to_equity_ratio(value):
    number = _number(value)
    if number is None:
        return None
    return number / 100.0


def _cache(fn):
    try:
        import streamlit as st

        return st.cache_data(ttl=3600, show_spinner=False)(fn)
    except Exception:
        return fn


get_price_history = _cache(fetch_price_history)
get_realtime_price = _cache(fetch_realtime_price)
get_fundamentals = _cache(fetch_fundamentals)
get_insider_transactions = _cache(fetch_insider_transactions)
get_institutional_holders = _cache(fetch_institutional_holders)
