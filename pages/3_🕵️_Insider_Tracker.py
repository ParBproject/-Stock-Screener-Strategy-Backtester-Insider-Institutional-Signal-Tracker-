"""Score insider filings after a public date. Institutional rows are display only."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from modules.insider import institutional_visible, score_filings
from utils.data_fetcher import DataFetchError, get_insider_transactions, get_institutional_holders

st.markdown("### Insider and institutional filings")
st.caption(
    "Buys and sells count only after a public date. A missing filing date waits two business days. "
    "The score is a count of those filings, not a forecast. "
    "A 13F row is shown 45 days after quarter end."
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
            st.metric("Filing activity score", scored["score"], help="Count of public insider buys and sells in the window. Not a forecast.")
            st.write(scored["label"])
            for reason in scored["reasons"]:
                st.write(f"- {reason}")
            show = filings.copy()
            show["counts_toward_score"] = (
                (show["available_date"] <= pd.Timestamp(asof))
                & (show["available_date"] > pd.Timestamp(asof) - pd.Timedelta(days=int(lookback)))
            )
            st.dataframe(show)
    try:
        holders = get_institutional_holders(ticker)
    except DataFetchError as exc:
        st.warning(f"Institutional snapshot: {exc}")
    else:
        st.markdown("#### Institutional holdings public on the as-of date")
        if holders is None or len(holders) == 0:
            st.info("No institutional rows returned.")
        else:
            try:
                visible = institutional_visible(holders, pd.Timestamp(asof))
            except ValueError as exc:
                st.warning(str(exc))
            else:
                withheld = len(holders) - len(visible)
                if withheld:
                    st.caption(
                        f"{withheld} holder row(s) withheld. Date Reported is the quarter end, "
                        "and the row is not treated as public until 45 days later."
                    )
                if visible.empty:
                    st.info("No institutional rows were public on this as-of date.")
                else:
                    st.dataframe(visible)
