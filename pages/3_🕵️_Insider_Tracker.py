"""Insider filings scored only after they are public. Institutions are display-only."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from modules.insider import score_filings
from utils.data_fetcher import DataFetchError, get_insider_transactions, get_institutional_holders

st.markdown("### Insider and institutional filings")
st.caption(
    "The transaction date is not the public date. When the feed has no filing stamp, "
    "a Form 4 is treated as public two business days later (weekends are skipped; "
    "exchange holidays are not). The score uses only filings already public on the "
    "as-of date. It describes filing activity and is not a return forecast. "
    "Institutional rows are the latest vendor snapshot and are not turned into a backtest. "
    "A 13F is not public on the quarter-end date; the deadline is 45 days later."
)

ticker = st.text_input("Ticker", value="AAPL").strip().upper()
asof = st.date_input("Score as of", value=date.today())
lookback = st.slider("Lookback (calendar days)", min_value=30, max_value=365, value=90, step=30)

if st.button("Load filings", type="primary") and ticker:
    try:
        filings = get_insider_transactions(ticker)
    except DataFetchError as exc:
        st.error(str(exc))
        filings = None
    if filings is not None:
        if filings.empty:
            st.info("The vendor returned no insider transactions.")
        else:
            scored = score_filings(filings, pd.Timestamp(asof), lookback_days=int(lookback))
            st.metric("Filing activity score", scored["score"], help="0–100 description of public insider prints. Not a forecast.")
            st.write(scored["label"])
            for reason in scored["reasons"]:
                st.write(f"- {reason}")
            show = filings.copy()
            show["counts_toward_score"] = (
                (show["available_date"] <= pd.Timestamp(asof))
                & (show["available_date"] > pd.Timestamp(asof) - pd.Timedelta(days=int(lookback)))
            )
            st.dataframe(show, use_container_width=True)
    try:
        holders = get_institutional_holders(ticker)
    except DataFetchError as exc:
        st.warning(f"Institutional snapshot: {exc}")
    else:
        st.markdown("#### Latest institutional snapshot")
        if holders is None or len(holders) == 0:
            st.info("No institutional rows returned.")
        else:
            st.dataframe(holders, use_container_width=True)
