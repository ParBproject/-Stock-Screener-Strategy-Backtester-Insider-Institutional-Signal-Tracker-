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

from modules.insider import institutional_visible, score_filings
from utils.data_fetcher import DataFetchError, get_insider_transactions, get_institutional_holders

st.markdown("### Insider and institutional filings")
st.caption(
    "The transaction date is not the public date. When the feed has no filing stamp, "
    "a Form 4 is treated as public two business days later (weekends are skipped; "
    "exchange holidays are not). The score uses only filings already public on the "
    "as-of date. It describes filing activity and is not a return forecast. "
    "Institutional rows are not a backtest. Yahoo's Date Reported is the quarter end, "
    "not the filing day, so a row is shown only once that quarter end plus 45 days "
    "(rolled to Monday when the deadline is a weekend) is on or before the as-of date. "
    "Exchange holidays are not rolled."
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
