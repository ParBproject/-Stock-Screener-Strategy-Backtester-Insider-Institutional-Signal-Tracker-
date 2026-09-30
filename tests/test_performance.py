"""Pins for compounded returns and 252-day annualization."""

import math

import numpy as np
import pandas as pd
import pytest

from config import TRADING_DAYS_PER_YEAR
from modules.performance import geometric_excess, performance_from_returns


def test_total_return_compounds_instead_of_summing():
    stats = performance_from_returns(pd.Series([0.10, -0.10]))
    assert stats["total_return"] == pytest.approx(1.10 * 0.90 - 1.0)
    assert stats["total_return"] != pytest.approx(0.0)


def test_cagr_uses_return_count_and_trading_days():
    daily = 2 ** (1 / TRADING_DAYS_PER_YEAR) - 1
    stats = performance_from_returns(pd.Series(np.full(TRADING_DAYS_PER_YEAR, daily)))
    assert stats["n_periods"] == TRADING_DAYS_PER_YEAR
    assert stats["total_return"] == pytest.approx(1.0, rel=1e-9)
    assert stats["cagr"] == pytest.approx(1.0, rel=1e-9)


def test_drawdown_is_peak_to_trough():
    stats = performance_from_returns(pd.Series([0.50, -0.40]))
    assert stats["max_drawdown"] == pytest.approx(-0.40)


def test_zero_volatility_sharpe_and_sortino_are_undefined():
    stats = performance_from_returns(pd.Series([0.01, 0.01, 0.01]))
    assert stats["sharpe"] is None
    assert stats["sortino"] is None
    assert stats["max_drawdown"] == pytest.approx(0.0)
    assert stats["calmar"] is None


def test_sortino_uses_root_mean_square_downside():
    returns = pd.Series([0.02, -0.01, 0.0])
    stats = performance_from_returns(returns)
    mean = (0.02 - 0.01 + 0.0) / 3
    downside = math.sqrt((0.01 ** 2) / 3)
    expected = mean / downside * math.sqrt(TRADING_DAYS_PER_YEAR)
    assert stats["sortino"] == pytest.approx(expected)


def test_geometric_excess_is_the_wealth_ratio():
    assert geometric_excess(0.21, 0.10) == pytest.approx(1.21 / 1.10 - 1.0)
    assert geometric_excess(0.21, 0.10) != pytest.approx(0.11)
    assert geometric_excess(0.10, 0.10) == pytest.approx(0.0)
    assert geometric_excess(None, 0.10) is None
    assert geometric_excess(-1.0, 0.10) is None


def test_alpha_beta_against_a_benchmark():
    benchmark = pd.Series([0.01, -0.02, 0.03, 0.00])
    doubled = benchmark * 2
    stats = performance_from_returns(doubled, benchmark=benchmark)
    assert stats["beta"] == pytest.approx(2.0)
    assert stats["alpha"] == pytest.approx(0.0, abs=1e-12)

    plus_one_bp = benchmark + 0.001
    tilted = performance_from_returns(plus_one_bp, benchmark=benchmark)
    assert tilted["beta"] == pytest.approx(1.0)
    assert tilted["alpha"] == pytest.approx(0.001 * TRADING_DAYS_PER_YEAR)
