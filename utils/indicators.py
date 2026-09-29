"""Causal technical indicators.

Every value at time t uses prices at t and earlier only. Rolling windows use
``center=False``. These series may be read at the close of bar t; the
backtester is responsible for trading them on a later bar.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(close: pd.Series, period: int) -> pd.Series:
    return close.astype(float).rolling(period, min_periods=period, center=False).mean()


def ema(close: pd.Series, span: int) -> pd.Series:
    return close.astype(float).ewm(span=span, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder-style RSI. Warmup values before ``period`` deltas are NaN."""
    delta = close.astype(float).diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    values = 100 - (100 / (1 + rs))
    values = values.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    values = values.mask((avg_gain == 0) & (avg_loss == 0), 50.0)
    return values


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series]:
    line = ema(close, fast) - ema(close, slow)
    signal_line = line.ewm(span=signal, adjust=False).mean()
    return line, signal_line


def bollinger(close: pd.Series, period: int = 20, std_dev: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    price = close.astype(float)
    mid = price.rolling(period, min_periods=period, center=False).mean()
    deviation = price.rolling(period, min_periods=period, center=False).std(ddof=0)
    return mid + std_dev * deviation, mid, mid - std_dev * deviation


def threshold_signal(
    indicator: pd.Series,
    *,
    enter_below: float | None = None,
    exit_above: float | None = None,
    enter_above: float | None = None,
    exit_below: float | None = None,
) -> pd.Series:
    """Stateful long/flat signal. Missing indicator values do not open a trade."""
    position = 0.0
    held: list[float] = []
    for value in indicator.to_numpy(dtype=float):
        if np.isnan(value):
            held.append(position)
            continue
        if enter_below is not None and value < enter_below:
            position = 1.0
        elif exit_above is not None and value > exit_above:
            position = 0.0
        if enter_above is not None and value > enter_above:
            position = 1.0
        elif exit_below is not None and value < exit_below:
            position = 0.0
        held.append(position)
    return pd.Series(held, index=indicator.index, dtype=float)
