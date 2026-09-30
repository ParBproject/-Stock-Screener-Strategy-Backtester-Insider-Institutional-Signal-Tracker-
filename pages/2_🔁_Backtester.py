"""Strategy backtest. Fills are the next open. Metrics are computed for this run only."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from config import BACKTEST_DEFAULTS, STRATEGY_PARAMS
from modules.backtester import run_backtest
from utils.charts import equity_curve_chart
from utils.data_fetcher import DataFetchError, get_price_history


def _pct(value) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.2f}%"


def _num(value) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}"


st.markdown("### Strategy backtester")
st.caption(
    "A signal may use that bar's close. The fill is the next session's open. "
    "Commission and slippage are charged on turnover. Prices are adjusted for splits and dividends. "
    "The last open is not marked, because there is no following open, and that empty day is left out of Sharpe and CAGR. "
    "Buy and hold uses the same fills and the same costs, fully invested. "
    "Figures below are calculated from the series downloaded for this run. "
    "Parameters are chosen on this sample, not walk-forward. "
    "This page does not publish a track record."
)

ticker = st.text_input("Ticker", value="AAPL").strip().upper()
left, right = st.columns(2)
start = left.date_input("Start", value=date.fromisoformat(BACKTEST_DEFAULTS["start"]))
end = right.date_input("End", value=date.fromisoformat(BACKTEST_DEFAULTS["end"]))
strategy = st.selectbox("Strategy", list(STRATEGY_PARAMS))
params = {}
for name, spec in STRATEGY_PARAMS[strategy].items():
    step = spec["step"]
    if isinstance(spec["default"], float) or isinstance(step, float):
        params[name] = st.slider(
            name,
            min_value=float(spec["min"]),
            max_value=float(spec["max"]),
            value=float(spec["default"]),
            step=float(step),
        )
    else:
        params[name] = st.slider(
            name,
            min_value=int(spec["min"]),
            max_value=int(spec["max"]),
            value=int(spec["default"]),
            step=int(step),
        )

capital = st.number_input("Starting capital", min_value=1.0, value=float(BACKTEST_DEFAULTS["capital"]), step=1000.0)
commission = st.number_input(
    "Commission (fraction of notional per fill)",
    min_value=0.0,
    max_value=0.05,
    value=float(BACKTEST_DEFAULTS["commission"]),
    step=0.0005,
    format="%.4f",
)
slippage = st.number_input(
    "Slippage (fraction of notional per fill)",
    min_value=0.0,
    max_value=0.05,
    value=float(BACKTEST_DEFAULTS["slippage"]),
    step=0.0005,
    format="%.4f",
)
fraction = st.slider(
    "Position fraction when long",
    min_value=0.0,
    max_value=1.0,
    value=float(BACKTEST_DEFAULTS["position_fraction"]),
    step=0.05,
)

if st.button("Run backtest", type="primary"):
    if end < start:
        st.error("End date is before the start date.")
    elif not ticker:
        st.error("Enter a ticker.")
    else:
        try:
            prices = get_price_history(ticker, start.isoformat(), end.isoformat())
            result = run_backtest(
                prices,
                strategy,
                params,
                initial_capital=capital,
                commission=commission,
                slippage=slippage,
                position_fraction=fraction,
            )
        except DataFetchError as exc:
            st.error(str(exc))
        except ValueError as exc:
            st.error(str(exc))
        else:
            if float(result["signal"].sum()) == 0.0:
                st.info(
                    "The signal stayed flat, so the book stayed in cash. "
                    "That happens when the slow window is longer than the sample or the rule never fires."
                )
            metrics = result["metrics"]
            labels = [
                ("Total return", _pct(metrics["total_return"])),
                ("CAGR", _pct(metrics["cagr"])),
                ("Sharpe (rf = 0)", _num(metrics["sharpe"])),
                ("Sortino (rf = 0)", _num(metrics["sortino"])),
                ("Calmar", _num(metrics["calmar"])),
                ("Max drawdown", _pct(metrics["max_drawdown"])),
                ("Win rate", _pct(metrics["win_rate"])),
                ("Profit factor", _num(metrics["profit_factor"])),
                ("Closed trades", "0" if metrics["n_trades"] is None else str(metrics["n_trades"])),
                ("Time in market", _pct(metrics.get("time_in_market"))),
                ("Buy & hold return", _pct(metrics.get("benchmark_total_return"))),
                ("Buy & hold CAGR", _pct(metrics.get("benchmark_cagr"))),
                ("Excess total return", _pct(metrics.get("excess_total_return"))),
                ("Alpha (rf = 0)", _pct(metrics.get("alpha"))),
                ("Beta", _num(metrics.get("beta"))),
            ]
            columns = st.columns(3)
            for index, (label, text) in enumerate(labels):
                columns[index % 3].metric(label, text)
            st.caption(
                "Excess total return is the wealth ratio minus one, not the difference of the two total returns. "
                "Alpha is Jensen's alpha with a zero risk-free rate, annualized by multiplying the daily alpha by 252. "
                "Time in market is the share of completed open-to-open bars with a long position. "
                "An open trade is in the equity curve and is not in the win rate."
            )
            st.plotly_chart(
                equity_curve_chart(
                    result["equity"],
                    benchmark=result.get("benchmark_equity"),
                    title=f"{ticker} {strategy}",
                ),
            )
            if result["trades"].empty:
                st.info("No closed trade in this window. An open position is still in the equity curve.")
            else:
                trades = result["trades"].copy()
                trades["return"] = trades["return"].map(lambda value: f"{value * 100:.2f}%")
                st.dataframe(trades)
