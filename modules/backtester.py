"""Long/flat backtest with next-open fills.

A signal on bar t may use that bar's close. The order is filled at the open
of bar t+1. The position then earns the next open-to-open return. Filling at
the signal bar's close, or earning that bar's return, is look-ahead bias and
is not what this simulator does.

Commission and slippage are fractions of traded notional and are charged on
turnover. Returns are compounded. The final open has no following open, so a
signal on the last bar is not filled and the last open-to-close move is not
marked.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from modules.performance import performance_from_returns
from utils.indicators import bollinger, ema, macd, rsi, sma, threshold_signal


def build_signal(name: str, ohlcv: pd.DataFrame, params: dict) -> pd.Series:
    """Return a 0/1 signal aligned to ``ohlcv`` and known at that bar's close."""
    close = ohlcv["close"].astype(float)
    if name == "SMA Crossover":
        fast = int(params["fast_period"])
        slow = int(params["slow_period"])
        _require_fast_slow(fast, slow)
        return (sma(close, fast) > sma(close, slow)).astype(float).fillna(0.0)
    if name == "EMA Crossover":
        fast = int(params["fast_period"])
        slow = int(params["slow_period"])
        _require_fast_slow(fast, slow)
        signal = (ema(close, fast) > ema(close, slow)).astype(float)
        signal.iloc[: slow - 1] = 0.0
        return signal.fillna(0.0)
    if name == "RSI Mean-Reversion":
        values = rsi(close, int(params["rsi_period"]))
        return threshold_signal(
            values,
            enter_below=float(params["oversold"]),
            exit_above=float(params["overbought"]),
        )
    if name == "MACD":
        fast = int(params["fast"])
        slow = int(params["slow"])
        _require_fast_slow(fast, slow)
        line, signal_line = macd(close, fast, slow, int(params["signal"]))
        signal = (line > signal_line).astype(float)
        signal.iloc[: slow - 1] = 0.0
        return signal.fillna(0.0)
    if name == "Bollinger Bands":
        _upper, mid, lower = bollinger(close, int(params["period"]), float(params["std_dev"]))
        position = 0.0
        held: list[float] = []
        for price, lower_band, mid_band in zip(close.to_numpy(), lower.to_numpy(), mid.to_numpy()):
            if np.isnan(lower_band) or np.isnan(mid_band):
                position = 0.0
                held.append(0.0)
                continue
            if price < lower_band:
                position = 1.0
            elif price > mid_band:
                position = 0.0
            held.append(position)
        return pd.Series(held, index=close.index, dtype=float)
    raise KeyError(f"Unknown strategy: {name}")


def simulate_long_flat(
    open_prices: pd.Series,
    signal: pd.Series,
    *,
    initial_capital: float = 100_000.0,
    commission: float = 0.0,
    slippage: float = 0.0,
    position_fraction: float = 1.0,
) -> dict:
    """Simulate a long/flat book.

    ``signal`` is the desired exposure known at the close. Exposure held while
    earning the open-to-open return that starts at bar t is the prior close's
    signal, scaled by ``position_fraction``.
    """
    if initial_capital <= 0:
        raise ValueError("initial_capital must be positive")
    if commission < 0 or slippage < 0:
        raise ValueError("commission and slippage must be non-negative")
    if not 0.0 <= position_fraction <= 1.0:
        raise ValueError("position_fraction must be between 0 and 1")
    unit_cost = float(commission) + float(slippage)
    if unit_cost >= 1.0:
        raise ValueError("commission plus slippage must be below 100%")

    opens = pd.Series(open_prices, copy=True).astype(float).sort_index()
    opens = opens[opens > 0].dropna()
    if opens.empty:
        raise ValueError("open prices are empty")

    desired = pd.Series(signal, copy=True).reindex(opens.index).astype(float)
    desired = desired.clip(lower=0.0, upper=1.0).fillna(0.0)
    held = desired.shift(1).fillna(0.0) * float(position_fraction)

    forward = opens.shift(-1) / opens - 1.0
    gross = forward.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    turnover = held.diff().abs()
    turnover.iloc[0] = abs(float(held.iloc[0]))
    net = held * gross - turnover * unit_cost

    equity = float(initial_capital) * (1.0 + net).cumprod()
    trades, win_rate, profit_factor = _trades(held, net, opens, float(initial_capital))
    metrics = performance_from_returns(net, initial_capital=float(initial_capital))
    metrics["win_rate"] = win_rate
    metrics["profit_factor"] = profit_factor
    metrics["n_trades"] = int(len(trades))
    return {
        "equity": equity,
        "returns": net,
        "position": held,
        "signal": desired,
        "turnover": turnover,
        "trades": trades,
        "metrics": metrics,
    }


def run_backtest(
    ohlcv: pd.DataFrame,
    strategy: str,
    params: dict,
    *,
    initial_capital: float = 100_000.0,
    commission: float = 0.0,
    slippage: float = 0.0,
    position_fraction: float = 1.0,
) -> dict:
    """Build ``strategy`` on closes and fill it with ``simulate_long_flat``."""
    if "open" not in ohlcv.columns or "close" not in ohlcv.columns:
        raise ValueError("ohlcv must include open and close columns")
    signal = build_signal(strategy, ohlcv, params)
    return simulate_long_flat(
        ohlcv["open"],
        signal,
        initial_capital=initial_capital,
        commission=commission,
        slippage=slippage,
        position_fraction=position_fraction,
    )


def _require_fast_slow(fast: int, slow: int) -> None:
    if fast < 1 or slow < 2 or fast >= slow:
        raise ValueError("fast period must be at least 1 and shorter than the slow period")


def _trades(
    held: pd.Series,
    net: pd.Series,
    opens: pd.Series,
    initial_capital: float,
) -> tuple[pd.DataFrame, float | None, float | None]:
    """Closed round trips only. An open position stays in the equity curve."""
    rows: list[dict] = []
    pnls: list[float] = []
    in_trade = False
    entry_index = 0
    entry_equity = initial_capital
    equity = initial_capital
    for i, exposure in enumerate(held.to_numpy()):
        equity_before = equity
        equity *= 1.0 + float(net.iloc[i])
        if not in_trade and exposure > 0:
            in_trade = True
            entry_index = i
            entry_equity = equity_before
        elif in_trade and exposure == 0:
            pnl = equity - entry_equity
            pnls.append(pnl)
            segment = net.iloc[entry_index : i + 1]
            rows.append(
                {
                    "entry_date": held.index[entry_index],
                    "exit_date": held.index[i],
                    "entry_open": float(opens.iloc[entry_index]),
                    "exit_open": float(opens.iloc[i]),
                    "return": float(np.prod(1.0 + segment.to_numpy()) - 1.0),
                    "pnl": pnl,
                }
            )
            in_trade = False
    frame = pd.DataFrame(rows)
    if not pnls:
        return frame, None, None
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    win_rate = len(wins) / len(pnls)
    if not losses:
        profit_factor = None
    else:
        profit_factor = float(sum(wins) / abs(sum(losses)))
    return frame, win_rate, profit_factor
