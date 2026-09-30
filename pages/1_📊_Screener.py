"""Current fundamental and technical screen. Not a historical factor backtest."""

from __future__ import annotations

import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from config import PRESETS, SP500_SAMPLE
from modules.screener import apply_filters
from utils.data_fetcher import DataFetchError, get_fundamentals, get_price_history
from utils.indicators import rsi

st.markdown("### Stock screener")
st.caption(
    "This is a current snapshot. A missing field fails the filter. "
    "price_change_52w is the total change, dividends included, from the first to the last adjusted close in the fetched window (about a year). "
    "The ticker list is names that trade today, so it has survivorship bias "
    "and is not point-in-time S&P 500 membership. It is not a historical factor backtest."
)

preset_name = st.selectbox("Preset", ["Custom", *PRESETS.keys()])
criteria = dict(PRESETS.get(preset_name, {}))
if preset_name == "Custom":
    criteria = {}
    max_pe = st.number_input("Max P/E (blank skips)", min_value=0.0, value=0.0, step=1.0)
    min_roe = st.number_input("Min ROE % (blank skips)", min_value=0.0, value=0.0, step=1.0)
    if max_pe > 0:
        criteria["max_pe"] = max_pe
    if min_roe > 0:
        criteria["min_roe"] = min_roe

default_names = SP500_SAMPLE[:8]
tickers = st.multiselect("Tickers", SP500_SAMPLE, default=default_names)
st.caption("Each name is a separate vendor request. Results are cached for one hour. Scanning the full list can be rate-limited.")

if st.button("Run screen", type="primary", disabled=not tickers):
    rows = []
    errors = []
    progress = st.progress(0.0)
    end = date.today()
    start = end - timedelta(days=370)
    for i, ticker in enumerate(tickers):
        try:
            facts = get_fundamentals(ticker)
            row = {"ticker": ticker, **facts, "rsi": None}
            try:
                prices = get_price_history(ticker, start.isoformat(), end.isoformat())
            except DataFetchError as exc:
                errors.append(f"{ticker} prices: {exc}")
                prices = pd.DataFrame()
            if len(prices) >= 2 and "close" in prices.columns:
                row["price_change_52w"] = float(prices["close"].iloc[-1] / prices["close"].iloc[0] - 1.0) * 100.0
                indicator = rsi(prices["close"], 14)
                last_rsi = indicator.iloc[-1]
                row["rsi"] = None if pd.isna(last_rsi) else float(last_rsi)
            if "volume" in prices.columns and len(prices):
                row["volume"] = float(prices["volume"].tail(20).mean())
            rows.append(row)
        except DataFetchError as exc:
            errors.append(f"{ticker}: {exc}")
        progress.progress((i + 1) / len(tickers))
        if i + 1 < len(tickers):
            time.sleep(0.15)
    progress.empty()
    for message in errors:
        st.warning(message)
    if not rows:
        st.error("No snapshots came back. Nothing is filled in with sample data.")
    else:
        frame = pd.DataFrame(rows)
        kept = apply_filters(frame, criteria) if criteria else frame
        st.write(f"{len(kept)} of {len(frame)} snapshots passed.")
        st.dataframe(kept)
        st.download_button(
            "Download CSV",
            kept.to_csv(index=False).encode("utf-8"),
            file_name="screen.csv",
            mime="text/csv",
        )
