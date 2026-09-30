"""Pins the execution rule: a close signal is filled at the next open."""

import numpy as np
import pandas as pd
import pytest

from modules.backtester import build_signal, run_backtest, simulate_long_flat


def test_same_bar_jump_is_not_earned():
    """Close doubles on the signal bar. The fill is the next open, which is already there."""
    index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])
    opens = pd.Series([10.0, 10.0, 20.0, 20.0], index=index)
    signal = pd.Series([0.0, 1.0, 1.0, 1.0], index=index)
    commission = 0.001
    slippage = 0.001
    result = simulate_long_flat(opens, signal, commission=commission, slippage=slippage)

    assert result["position"].tolist() == [0.0, 0.0, 1.0, 1.0]
    assert result["signal"].shift(1).fillna(0.0).tolist() == result["position"].tolist()
    assert result["metrics"]["total_return"] == pytest.approx(-(commission + slippage))
    assert result["metrics"]["n_trades"] == 0


def test_move_after_the_fill_is_earned():
    index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])
    opens = pd.Series([10.0, 10.0, 10.0, 15.0], index=index)
    signal = pd.Series([0.0, 1.0, 1.0, 1.0], index=index)
    cost = 0.002
    result = simulate_long_flat(opens, signal, commission=0.001, slippage=0.001)
    assert result["metrics"]["total_return"] == pytest.approx(0.50 - cost)


def test_round_trip_pays_entry_and_exit_costs():
    index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"])
    opens = pd.Series([10.0, 10.0, 10.0, 10.0, 10.0], index=index)
    signal = pd.Series([0.0, 1.0, 1.0, 0.0, 0.0], index=index)
    cost = 0.002
    result = simulate_long_flat(
        opens, signal, initial_capital=100_000, commission=0.001, slippage=0.001
    )
    expected = (1 - cost) * (1 - cost) - 1
    assert result["metrics"]["total_return"] == pytest.approx(expected)
    assert result["metrics"]["n_trades"] == 1
    assert result["metrics"]["win_rate"] == 0.0
    assert result["metrics"]["profit_factor"] == 0.0
    trade = result["trades"].iloc[0]
    assert trade["entry_open"] == 10.0
    assert trade["exit_open"] == 10.0
    assert result["equity"].iloc[-1] == pytest.approx(100_000 * (1 + expected))


def test_fill_price_is_the_next_open():
    index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"])
    opens = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0], index=index)
    signal = pd.Series([0.0, 1.0, 1.0, 0.0, 0.0], index=index)
    result = simulate_long_flat(opens, signal)
    trade = result["trades"].iloc[0]
    assert trade["entry_date"] == index[2]
    assert trade["entry_open"] == 12.0
    assert trade["exit_open"] == 14.0


def test_signal_on_the_final_bar_is_not_filled():
    index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    opens = pd.Series([10.0, 10.0, 10.0], index=index)
    signal = pd.Series([0.0, 0.0, 1.0], index=index)
    result = simulate_long_flat(opens, signal, commission=0.001, slippage=0.001)
    assert result["position"].tolist() == [0.0, 0.0, 0.0]
    assert result["metrics"]["total_return"] == pytest.approx(0.0)


def test_half_position_earns_half_the_open_to_open_move():
    index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])
    opens = pd.Series([10.0, 10.0, 10.0, 20.0], index=index)
    signal = pd.Series([0.0, 1.0, 1.0, 1.0], index=index)
    result = simulate_long_flat(opens, signal, position_fraction=0.5)
    assert result["metrics"]["total_return"] == pytest.approx(0.5)


def test_run_backtest_holds_the_lagged_signal_and_requires_open():
    frame = pd.DataFrame(
        {
            "open": [10.0, 10.0, 10.0, 11.0, 12.0, 14.0, 16.0, 18.0],
            "close": [10.0, 10.0, 11.0, 12.0, 13.0, 15.0, 17.0, 19.0],
        }
    )
    result = run_backtest(
        frame,
        "SMA Crossover",
        {"fast_period": 2, "slow_period": 3},
    )
    lagged = result["signal"].shift(1).fillna(0.0)
    assert result["position"].tolist() == lagged.tolist()
    with pytest.raises(ValueError, match="open"):
        run_backtest(frame.drop(columns=["open"]), "SMA Crossover", {"fast_period": 2, "slow_period": 3})


def test_strategy_values_do_not_change_when_a_future_price_is_appended():
    generator = np.random.default_rng(7)
    close = pd.Series(100 + generator.normal(0, 1, 90).cumsum())
    future = pd.concat([close, pd.Series([close.iloc[-1] + 80.0])], ignore_index=True)
    cases = {
        "SMA Crossover": {"fast_period": 5, "slow_period": 20},
        "EMA Crossover": {"fast_period": 12, "slow_period": 26},
        "RSI Mean-Reversion": {"rsi_period": 14, "oversold": 30, "overbought": 70},
        "MACD": {"fast": 12, "slow": 26, "signal": 9},
        "Bollinger Bands": {"period": 20, "std_dev": 2},
    }
    for name, params in cases.items():
        original = build_signal(name, _ohlc(close), params)
        extended = build_signal(name, _ohlc(future), params)
        pd.testing.assert_series_equal(
            original.reset_index(drop=True),
            extended.iloc[:-1].reset_index(drop=True),
            check_names=False,
        )


def test_terminal_flat_bar_is_not_an_annualization_period():
    index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])
    opens = pd.Series([10.0, 10.0, 10.0, 20.0], index=index)
    signal = pd.Series([0.0, 1.0, 1.0, 1.0], index=index)
    result = simulate_long_flat(opens, signal, initial_capital=100_000)
    assert result["metrics"]["total_return"] == pytest.approx(1.0)
    assert result["metrics"]["n_periods"] == len(opens) - 1
    assert result["equity"].iloc[-1] == pytest.approx(200_000)
    assert result["metrics"]["total_return"] == pytest.approx(result["equity"].iloc[-1] / 100_000 - 1)
    wealth = 1.0 + result["metrics"]["total_return"]
    expected_cagr = wealth ** (252 / result["metrics"]["n_periods"]) - 1.0
    assert result["metrics"]["cagr"] == pytest.approx(expected_cagr)
    assert result["metrics"]["time_in_market"] == pytest.approx(1.0 / 3.0)


def test_exit_cost_on_the_final_open_stays_in_the_total_return():
    index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])
    opens = pd.Series([10.0, 10.0, 10.0, 10.0], index=index)
    signal = pd.Series([1.0, 1.0, 0.0, 0.0], index=index)
    cost = 0.002
    result = simulate_long_flat(opens, signal, commission=0.001, slippage=0.001)
    # Entry on the second open, exit on the last open. Both costs count.
    assert result["metrics"]["n_trades"] == 1
    assert result["metrics"]["total_return"] == pytest.approx((1 - cost) * (1 - cost) - 1)
    assert result["metrics"]["n_periods"] == len(opens)


def test_buy_and_hold_earns_the_move_the_lagged_signal_misses():
    index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])
    frame = pd.DataFrame(
        {"open": [10.0, 10.0, 20.0, 20.0], "close": [10.0, 10.0, 20.0, 20.0]},
        index=index,
    )
    cost = 0.002
    result = run_backtest(
        frame,
        "SMA Crossover",
        {"fast_period": 1, "slow_period": 2},
        initial_capital=50_000,
        commission=0.001,
        slippage=0.001,
        position_fraction=0.5,
    )
    assert result["metrics"]["benchmark_total_return"] == pytest.approx(1.0 - cost)
    assert result["benchmark_equity"].iloc[-1] == pytest.approx(50_000 * (2.0 - cost))
    strategy_wealth = 1.0 + result["metrics"]["total_return"]
    benchmark_wealth = 1.0 + result["metrics"]["benchmark_total_return"]
    assert result["metrics"]["excess_total_return"] == pytest.approx(strategy_wealth / benchmark_wealth - 1.0)
    assert result["metrics"]["benchmark_total_return"] > result["metrics"]["total_return"]
    assert result["metrics"]["alpha"] is not None
    assert result["metrics"]["beta"] is not None


def test_shuffled_rows_match_the_calendar_order():
    index = pd.bdate_range("2024-01-02", periods=40)
    generator = np.random.default_rng(11)
    close = pd.Series(50 + generator.normal(0, 1, len(index)).cumsum(), index=index)
    frame = pd.DataFrame({"open": close * 0.99, "close": close})
    shuffled = frame.sample(frac=1.0, random_state=3)
    ordered = run_backtest(frame, "EMA Crossover", {"fast_period": 4, "slow_period": 12})
    scrambled = run_backtest(shuffled, "EMA Crossover", {"fast_period": 4, "slow_period": 12})
    assert scrambled["metrics"]["total_return"] == pytest.approx(ordered["metrics"]["total_return"])
    assert scrambled["metrics"]["benchmark_total_return"] == pytest.approx(ordered["metrics"]["benchmark_total_return"])
    pd.testing.assert_series_equal(
        scrambled["signal"].sort_index(),
        ordered["signal"].sort_index(),
        check_names=False,
        check_freq=False,
    )


def test_duplicate_timestamps_are_rejected():
    frame = pd.DataFrame(
        {"open": [10.0, 11.0], "close": [10.0, 11.0]},
        index=pd.to_datetime(["2024-01-02", "2024-01-02"]),
    )
    with pytest.raises(ValueError, match="duplicate"):
        run_backtest(frame, "SMA Crossover", {"fast_period": 1, "slow_period": 2})


def test_completed_intervals_do_not_change_when_a_future_bar_is_appended():
    index = pd.bdate_range("2024-01-02", periods=30)
    generator = np.random.default_rng(7)
    close = pd.Series(100 + generator.normal(0, 1, len(index)).cumsum(), index=index)
    close.iloc[-1] = close.iloc[-2] + 25.0
    frame = pd.DataFrame({"open": close, "close": close})
    params = {"fast_period": 3, "slow_period": 8}
    short = run_backtest(frame.iloc[:-1], "SMA Crossover", params)
    long = run_backtest(frame, "SMA Crossover", params)
    # Bars that already had a next open keep their return. The old last bar did not.
    pd.testing.assert_series_equal(
        short["returns"].iloc[:-1],
        long["returns"].iloc[:-2],
        check_names=False,
    )
    held = simulate_long_flat(frame["open"], pd.Series(1.0, index=frame.index))
    unmarked = simulate_long_flat(frame["open"].iloc[:-1], pd.Series(1.0, index=frame.index[:-1]))
    assert unmarked["returns"].iloc[-1] == pytest.approx(0.0)
    jump = frame["open"].iloc[-1] / frame["open"].iloc[-2] - 1.0
    assert held["returns"].iloc[-2] == pytest.approx(jump)


def test_fast_period_must_be_shorter_than_slow():
    frame = _ohlc(pd.Series([1.0, 2.0, 3.0, 4.0]))
    with pytest.raises(ValueError):
        build_signal("SMA Crossover", frame, {"fast_period": 10, "slow_period": 10})


def _ohlc(close: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"open": close.astype(float), "close": close.astype(float)})
