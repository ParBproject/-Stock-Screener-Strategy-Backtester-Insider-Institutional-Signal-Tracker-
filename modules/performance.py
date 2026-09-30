"""Compounded returns and risk statistics.

Total return and CAGR are compounded. They are not a sum of simple returns.
CAGR and the Sharpe/Sortino ratios use 252 trading days. Sharpe and Sortino
are None when their denominator is zero, rather than infinity.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from config import TRADING_DAYS_PER_YEAR


def _finite_returns(returns: pd.Series) -> pd.Series:
    series = pd.Series(returns, copy=True).astype(float)
    return series.replace([np.inf, -np.inf], np.nan).dropna()


def performance_from_returns(
    returns: pd.Series,
    initial_capital: float = 1.0,
    benchmark: pd.Series | None = None,
) -> dict:
    """Summarize a series of simple net returns, one observation per bar."""
    cleaned = _finite_returns(returns)
    periods = int(len(cleaned))
    result = {
        "total_return": None,
        "cagr": None,
        "sharpe": None,
        "sortino": None,
        "calmar": None,
        "max_drawdown": None,
        "alpha": None,
        "beta": None,
        "n_periods": periods,
    }
    if periods == 0 or initial_capital <= 0:
        return result

    wealth_multiple = float(np.prod(1.0 + cleaned.to_numpy()))
    result["total_return"] = wealth_multiple - 1.0
    if wealth_multiple > 0:
        result["cagr"] = wealth_multiple ** (TRADING_DAYS_PER_YEAR / periods) - 1.0
    result["max_drawdown"] = _max_drawdown(cleaned.to_numpy())
    result["sharpe"] = _sharpe(cleaned.to_numpy())
    result["sortino"] = _sortino(cleaned.to_numpy())
    drawdown = result["max_drawdown"]
    if drawdown is not None and drawdown < 0 and result["cagr"] is not None:
        result["calmar"] = result["cagr"] / abs(drawdown)
    if benchmark is not None:
        alpha, beta = _alpha_beta(cleaned, benchmark)
        result["alpha"] = alpha
        result["beta"] = beta
    return result


def _max_drawdown(returns: np.ndarray) -> float:
    curve = np.concatenate([[1.0], np.cumprod(1.0 + returns)])
    peak = np.maximum.accumulate(curve)
    drawdown = curve / peak - 1.0
    return float(drawdown.min())


def _sharpe(returns: np.ndarray) -> float | None:
    if len(returns) < 2:
        return None
    deviation = float(pd.Series(returns).std(ddof=1))
    if not math.isfinite(deviation) or deviation == 0.0:
        return None
    return float(returns.mean() / deviation * math.sqrt(TRADING_DAYS_PER_YEAR))


def _sortino(returns: np.ndarray) -> float | None:
    """Sortino using the root-mean-square of non-positive returns (target 0)."""
    downside = np.minimum(returns, 0.0)
    downside_deviation = float(math.sqrt(np.mean(downside ** 2)))
    if downside_deviation == 0.0:
        return None
    return float(returns.mean() / downside_deviation * math.sqrt(TRADING_DAYS_PER_YEAR))


def _alpha_beta(returns: pd.Series, benchmark: pd.Series) -> tuple[float | None, float | None]:
    """Jensen alpha with rf = 0, annualized by multiplying the daily alpha by 252.

    Beta is the OLS slope of strategy returns on benchmark returns. Alpha is
    None when the benchmark does not vary.
    """
    paired = pd.concat(
        [returns.rename("strategy"), pd.Series(benchmark).astype(float).rename("benchmark")],
        axis=1,
    ).dropna()
    if len(paired) < 2:
        return None, None
    variance = float(paired["benchmark"].var(ddof=1))
    if not math.isfinite(variance) or variance == 0.0:
        return None, None
    covariance = float(paired["strategy"].cov(paired["benchmark"]))
    beta = covariance / variance
    daily_alpha = float(paired["strategy"].mean() - beta * paired["benchmark"].mean())
    return daily_alpha * TRADING_DAYS_PER_YEAR, float(beta)
