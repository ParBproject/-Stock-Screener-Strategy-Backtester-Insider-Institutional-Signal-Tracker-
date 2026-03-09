# 📈 FinTools Pro

> **Stock Screener · Strategy Backtester · Insider & Institutional Signal Tracker**  
> A professional-grade Streamlit trading intelligence platform powered by `yfinance`.

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
![Streamlit](https://img.shields.io/badge/Streamlit-1.32+-red?logo=streamlit)
![License](https://img.shields.io/badge/license-MIT-green)

---

## 🖥️ Screenshots

### 🏠 Home Dashboard
![Home](screenshots/home.png)

### 📊 Stock Screener
![Screener](screenshots/screener.png)

### 🔁 Strategy Backtester
![Backtester](screenshots/backtester.png)

### 🕵️ Insider Tracker
![Insider](screenshots/insider.png)

---

## 🚀 Quick Start

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/fintools-pro.git
cd fintools-pro

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run
streamlit run app.py
```

Open `http://localhost:8501` in your browser.

---

## 🛠️ Modules

### 📊 Stock Screener
Filter 60+ tickers across any combination of:

**Valuation:** Market Cap, P/E, Forward P/E, PEG, P/B, P/S, EV/EBITDA  
**Growth:** Revenue Growth %, EPS Growth %, Earnings estimates  
**Quality:** ROE, ROA, Profit Margin, Operating Margin, Debt/Equity  
**Income:** Dividend Yield, Payout Ratio  
**Technical:** RSI, 52-week change %, Average volume, Beta  

Pre-built presets: **Value**, **Growth**, **High Dividend**, **Momentum**, **Quality**  
Export results to CSV or Excel.

---

### 🔁 Strategy Backtester

Test strategies on any ticker from **2015 to present** using daily or weekly bars.

| Strategy | Description |
|---|---|
| **SMA Crossover** | Golden/Death cross — configurable fast/slow periods |
| **EMA Crossover** | Exponential MA crossover — faster signals |
| **RSI Mean-Reversion** | Buy oversold (RSI < 30), sell overbought (RSI > 70) |
| **MACD** | Signal-line crossover momentum system |
| **Bollinger Bands** | Mean-reversion on upper/lower band touches |

**Performance metrics included:**
Total Return · CAGR · Sharpe · Sortino · Calmar · Max Drawdown ·  
Alpha · Beta · Win Rate · Profit Factor · Equity Curve · Monthly Returns Heatmap · Trade Log

**Realistic simulation:** commission, slippage, and position sizing.

---

### 🕵️ Insider & Institutional Tracker

**Single Ticker Analysis:**
- All insider buy/sell transactions (Form 4 via yfinance)
- Institutional holder breakdown (13F filings)
- Insider roster with ownership details
- Composite signal score 0–100 with key reasons

**Market Scan:**
- Scan entire watchlist in one click
- Ranked results by signal strength
- Filter by minimum score

**Signal labels:** `STRONG BUY · BUY · NEUTRAL · SELL · STRONG SELL`

**Cluster Buy Detection:** Fires when ≥ 3 unique insiders buy the same stock.

---

## 📁 Project Structure

```
fintools_pro/
│
├── app.py                          # Main entry point + home dashboard
├── config.py                       # Global settings, theme, presets
├── requirements.txt
├── README.md
│
├── pages/
│   ├── 1_📊_Screener.py            # Stock screener page
│   ├── 2_🔁_Backtester.py          # Backtester page
│   └── 3_🕵️_Insider_Tracker.py    # Insider tracker page
│
├── modules/
│   ├── screener.py                 # Screening logic + filter engine
│   ├── backtester.py               # Vectorised backtest engine + strategies
│   └── insider.py                  # Insider signal scoring engine
│
├── utils/
│   ├── data_fetcher.py             # Cached yfinance data layer
│   ├── indicators.py               # pandas_ta + numpy TA indicators
│   └── charts.py                   # Plotly chart builders
│
└── assets/
    └── style.css                   # Dark terminal theme
```

---

## 📦 Dependencies

| Package | Purpose |
|---|---|
| `streamlit` | Web dashboard framework |
| `yfinance` | Stock data (prices, fundamentals, insider/institutional) |
| `pandas` / `numpy` | Data manipulation |
| `pandas-ta` | Technical indicators (RSI, MACD, Bollinger Bands, SMAs) |
| `plotly` | Interactive charts |
| `openpyxl` / `xlsxwriter` | Excel export |
| `joblib` | Additional caching |

---

## 🔌 Data Sources

All data is sourced from **yfinance** (free, no API key required):

| Data Type | yfinance method |
|---|---|
| OHLCV prices | `yf.download()` |
| Fundamentals | `Ticker.info` |
| Insider transactions | `Ticker.insider_transactions` |
| Institutional holders | `Ticker.institutional_holders` |
| Major holders | `Ticker.major_holders` |
| Insider roster | `Ticker.insider_roster_holders` |

### Optional: Finnhub / FMP (Enhanced insider data)
For more detailed insider data, create a `.env` file:
```
FINNHUB_API_KEY=your_key_here
FMP_API_KEY=your_key_here
```
The app works fully without these (yfinance fallback is automatic).

---

## ⚙️ Configuration

Edit `config.py` to:
- Change the ticker universe (`SP500_SAMPLE`)
- Add/modify screener presets (`PRESETS`)
- Adjust strategy parameter ranges (`STRATEGY_PARAMS`)
- Modify the visual theme (`THEME`)

---

## ⚠️ Disclaimer

This tool is for **educational and research purposes only**.  
Nothing here constitutes financial advice. Past strategy performance does not guarantee future results.  
Always consult a licensed financial advisor before making investment decisions.

---

## 📄 License

MIT
