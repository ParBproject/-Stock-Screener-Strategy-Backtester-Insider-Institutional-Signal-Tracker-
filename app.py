"""
app.py — FinTools Pro main entry point & home dashboard.
Run with:  streamlit run app.py
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="FinTools Pro",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Inject CSS ────────────────────────────────────────────────────────────────
css_path = Path(__file__).parent / "assets" / "style.css"
if css_path.exists():
    st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)

from utils.data_fetcher import get_price_history, get_realtime_price, get_fundamentals
from utils.charts import equity_curve_chart
from config import THEME

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style='text-align:center; padding: 1rem 0;'>
        <div style='font-family:"IBM Plex Mono",monospace; font-size:1.4rem;
                    color:#00d4ff; font-weight:600; letter-spacing:0.08em;'>
            📈 FINTOOLS PRO
        </div>
        <div style='color:#64748b; font-size:0.72rem; margin-top:4px;'>
            Trading Intelligence Platform
        </div>
    </div>
    <hr style='border-color:#1e2d45; margin: 0.5rem 0 1rem;'/>
    """, unsafe_allow_html=True)

    st.markdown("### Navigation")
    st.page_link("app.py",                          label="🏠 Home Dashboard",         )
    st.page_link("pages/1_📊_Screener.py",          label="📊 Stock Screener",          )
    st.page_link("pages/2_🔁_Backtester.py",        label="🔁 Strategy Backtester",     )
    st.page_link("pages/3_🕵️_Insider_Tracker.py",  label="🕵️ Insider Tracker",         )

    st.markdown("<hr style='border-color:#1e2d45;'/>", unsafe_allow_html=True)

    st.markdown("""
    <div style='color:#64748b; font-size:0.72rem; padding:0.5rem 0;'>
        Data: yfinance · pandas_ta · Plotly<br>
        For educational use only.
    </div>
    """, unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class='page-header'>
    <h1>🏠 Home Dashboard</h1>
    <p>Real-time market overview · Watchlist · Quick metrics</p>
</div>
""", unsafe_allow_html=True)

# ── Market Overview ───────────────────────────────────────────────────────────
INDICES = {
    "S&P 500":  "^GSPC",
    "NASDAQ":   "^IXIC",
    "Dow Jones":"^DJI",
    "VIX":      "^VIX",
    "Gold":     "GC=F",
    "BTC-USD":  "BTC-USD",
}

st.markdown("#### 📡 Market Snapshot")
cols = st.columns(len(INDICES))
for col, (name, sym) in zip(cols, INDICES.items()):
    with col:
        try:
            info = get_realtime_price(sym)
            price = info.get("price")
            prev  = info.get("prev_close")
            if price and prev:
                chg = (price - prev) / prev * 100
                delta_color = "normal"
                col.metric(
                    label=name,
                    value=f"{price:,.2f}" if price < 10_000 else f"{price:,.0f}",
                    delta=f"{chg:+.2f}%",
                    delta_color="normal",
                )
            else:
                col.metric(label=name, value="Loading…")
        except Exception:
            col.metric(label=name, value="—")

st.divider()

# ── Watchlist Sparklines ──────────────────────────────────────────────────────
st.markdown("#### 🔭 Watchlist")

DEFAULT_WATCH = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META"]
watchlist = st.multiselect(
    "Add tickers to watchlist:",
    options=["AAPL","MSFT","GOOGL","AMZN","META","NVDA","TSLA","JPM","V","NFLX",
             "AMD","INTC","PYPL","SQ","SHOP","UBER","LYFT","SNAP","TWTR","COIN"],
    default=DEFAULT_WATCH,
    label_visibility="collapsed",
)

if watchlist:
    watch_cols = st.columns(min(len(watchlist), 3))
    for i, ticker in enumerate(watchlist):
        col = watch_cols[i % 3]
        with col:
            try:
                info  = get_realtime_price(ticker)
                fund  = get_fundamentals(ticker)
                price = info.get("price", 0) or 0
                prev  = info.get("prev_close", price) or price
                chg   = ((price - prev) / prev * 100) if prev else 0
                color = THEME["green"] if chg >= 0 else THEME["red"]

                # Sparkline
                hist = get_price_history(ticker, "2024-07-01", "2025-01-01")
                spark = go.Figure(go.Scatter(
                    x=hist.index if not hist.empty else [],
                    y=hist["close"].tolist() if not hist.empty else [],
                    mode="lines",
                    line=dict(color=color, width=1.5),
                    fill="tozeroy",
                    fillcolor=f"rgba({','.join(str(int(c,16)) for c in [color[1:3],color[3:5],color[5:7]])},0.08)",
                ))
                spark.update_layout(
                    height=100, margin=dict(l=0,r=0,t=0,b=0),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    showlegend=False,
                    xaxis=dict(visible=False),
                    yaxis=dict(visible=False),
                )

                cap = info.get("market_cap", 0) or 0
                cap_str = f"${cap/1e12:.2f}T" if cap >= 1e12 else (f"${cap/1e9:.1f}B" if cap >= 1e9 else "—")

                st.markdown(f"""
                <div class='ticker-card'>
                    <div style='display:flex; justify-content:space-between; align-items:flex-start;'>
                        <div>
                            <span style='font-family:"IBM Plex Mono",monospace;
                                         font-size:1rem; font-weight:600;
                                         color:{THEME["accent"]};'>{ticker}</span>
                            <span style='color:{THEME["text_muted"]}; font-size:0.72rem;
                                         margin-left:6px;'>{fund.get('name','')[:20]}</span>
                        </div>
                        <span style='color:{color}; font-family:"IBM Plex Mono",monospace;
                                     font-size:0.82rem;'>{chg:+.2f}%</span>
                    </div>
                    <div style='font-family:"IBM Plex Mono",monospace; font-size:1.3rem;
                                color:{THEME["text"]}; margin:4px 0;'>
                        ${price:,.2f}
                    </div>
                    <div style='color:{THEME["text_muted"]}; font-size:0.7rem;'>
                        Cap: {cap_str} &nbsp;|&nbsp;
                        P/E: {fund.get('pe') or '—'} &nbsp;|&nbsp;
                        β: {fund.get('beta') or '—'}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                st.plotly_chart(spark, use_container_width=True, config={"displayModeBar": False})

            except Exception as e:
                col.warning(f"{ticker}: {e}")

st.divider()

# ── Quick Access ──────────────────────────────────────────────────────────────
st.markdown("#### ⚡ Quick Tools")
qa_cols = st.columns(3)
with qa_cols[0]:
    st.markdown("""
    <div class='ticker-card' style='text-align:center; cursor:pointer;'>
        <div style='font-size:2rem;'>📊</div>
        <div style='color:#00d4ff; font-weight:600; margin:6px 0;'>Stock Screener</div>
        <div style='color:#64748b; font-size:0.78rem;'>Filter 60+ tickers by fundamentals,
        technicals & custom criteria</div>
    </div>
    """, unsafe_allow_html=True)
with qa_cols[1]:
    st.markdown("""
    <div class='ticker-card' style='text-align:center; cursor:pointer;'>
        <div style='font-size:2rem;'>🔁</div>
        <div style='color:#7c3aed; font-weight:600; margin:6px 0;'>Strategy Backtester</div>
        <div style='color:#64748b; font-size:0.78rem;'>Test 5 built-in strategies
        on any ticker from 2015–present</div>
    </div>
    """, unsafe_allow_html=True)
with qa_cols[2]:
    st.markdown("""
    <div class='ticker-card' style='text-align:center; cursor:pointer;'>
        <div style='font-size:2rem;'>🕵️</div>
        <div style='color:#10b981; font-weight:600; margin:6px 0;'>Insider Tracker</div>
        <div style='color:#64748b; font-size:0.78rem;'>Score insider & institutional
        signals. Find cluster-buy opportunities.</div>
    </div>
    """, unsafe_allow_html=True)
