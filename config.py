"""
config.py — Global configuration, theme palette, and constants for FinTools Pro.
"""

# ── Colour Palette ────────────────────────────────────────────────────────────
THEME = {
    "bg":           "#0a0e1a",
    "surface":      "#111827",
    "surface2":     "#1a2235",
    "border":       "#1e2d45",
    "accent":       "#00d4ff",
    "accent2":      "#7c3aed",
    "green":        "#10b981",
    "red":          "#ef4444",
    "yellow":       "#f59e0b",
    "text":         "#e2e8f0",
    "text_muted":   "#64748b",
    "chart_bg":     "#0d1220",
}

# ── Plotly base layout ────────────────────────────────────────────────────────
PLOTLY_LAYOUT = dict(
    paper_bgcolor=THEME["chart_bg"],
    plot_bgcolor=THEME["chart_bg"],
    font=dict(color=THEME["text"], family="'IBM Plex Mono', monospace"),
    xaxis=dict(gridcolor=THEME["border"], zeroline=False, showgrid=True),
    yaxis=dict(gridcolor=THEME["border"], zeroline=False, showgrid=True),
    margin=dict(l=40, r=20, t=40, b=40),
    legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor=THEME["border"]),
    hoverlabel=dict(bgcolor=THEME["surface2"], font_color=THEME["text"]),
)

# ── Universe of tickers for screener ─────────────────────────────────────────
SP500_SAMPLE = [
    "AAPL","MSFT","GOOGL","AMZN","META","NVDA","TSLA","BRK-B","UNH","JPM",
    "V","XOM","JNJ","PG","MA","HD","CVX","MRK","ABBV","LLY",
    "AVGO","PEP","KO","COST","MCD","WMT","BAC","CSCO","ACN","PFE",
    "TMO","CRM","DHR","ABT","TXN","NEE","NKE","LIN","QCOM","MDT",
    "PM","AMGN","RTX","HON","UPS","BMY","SBUX","LOW","INTU","T",
    "GS","MS","BLK","SPGI","AXP","CAT","DE","GE","MMM","IBM",
    "ORCL","ADBE","AMD","INTC","NOW","UBER","LYFT","ABNB","SNOW","PLTR",
]

# ── Screener presets ──────────────────────────────────────────────────────────
PRESETS = {
    "Value Stocks": {
        "max_pe": 15, "min_roe": 10, "max_pb": 3,
        "min_div_yield": 1.0, "max_debt_equity": 1.5,
    },
    "Growth": {
        "min_revenue_growth": 15, "min_earnings_growth": 20,
        "max_pe": 50, "min_roe": 15,
    },
    "High Dividend": {
        "min_div_yield": 3.0, "max_payout_ratio": 80,
        "min_market_cap": 5e9,
    },
    "Momentum": {
        "min_price_change_52w": 20, "min_rsi": 50, "max_rsi": 75,
        "min_volume": 1_000_000,
    },
    "Quality": {
        "min_roe": 20, "min_profit_margin": 15,
        "max_debt_equity": 1.0, "min_market_cap": 10e9,
    },
}

# ── Backtester defaults ───────────────────────────────────────────────────────
BACKTEST_DEFAULTS = {
    "start":        "2020-01-01",
    "end":          "2024-12-31",
    "capital":      100_000,
    "commission":   0.001,   # 0.1% per trade
    "slippage":     0.001,   # 0.1% slippage
}

STRATEGY_PARAMS = {
    "SMA Crossover": {
        "fast_period": {"default": 50,  "min": 5,   "max": 200, "step": 5},
        "slow_period": {"default": 200, "min": 20,  "max": 500, "step": 10},
    },
    "EMA Crossover": {
        "fast_period": {"default": 12,  "min": 3,   "max": 50,  "step": 1},
        "slow_period": {"default": 26,  "min": 10,  "max": 200, "step": 5},
    },
    "RSI Mean-Reversion": {
        "rsi_period":  {"default": 14,  "min": 5,   "max": 30,  "step": 1},
        "oversold":    {"default": 30,  "min": 10,  "max": 45,  "step": 1},
        "overbought":  {"default": 70,  "min": 55,  "max": 90,  "step": 1},
    },
    "MACD": {
        "fast":        {"default": 12,  "min": 5,   "max": 30,  "step": 1},
        "slow":        {"default": 26,  "min": 10,  "max": 50,  "step": 1},
        "signal":      {"default": 9,   "min": 3,   "max": 20,  "step": 1},
    },
    "Bollinger Bands": {
        "period":      {"default": 20,  "min": 5,   "max": 50,  "step": 1},
        "std_dev":     {"default": 2,   "min": 1,   "max": 4,   "step": 0},
    },
}
