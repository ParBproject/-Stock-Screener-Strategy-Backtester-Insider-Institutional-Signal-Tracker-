# FinTools Pro

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](requirements.txt)
[![Streamlit](https://img.shields.io/badge/Streamlit-Trading_Intelligence-FF4B4B?logo=streamlit&logoColor=white)](app.py)
[![Data](https://img.shields.io/badge/Data-yfinance-2ea44f)](https://github.com/ranaroussi/yfinance)

A Streamlit-based equity research application that combines stock screening, strategy backtesting, and insider/institutional signal review in one interface.

## Modules

| Module | Purpose |
|---|---|
| Stock screener | Compare a curated ticker universe using valuation, growth, quality, income, and technical filters |
| Strategy backtester | Evaluate configurable technical strategies and review risk-adjusted performance |
| Ownership signals | Inspect insider transactions and institutional holdings |
| Reporting | Export filtered results and review interactive performance charts |

## Application Preview

### Home Dashboard

![FinTools Pro home dashboard](home.png)

### Stock Screener

![Stock screener](screener.png)

### Strategy Backtester

![Strategy backtester](backtester.png)

### Insider & Institutional Signals

![Insider signal tracker](insider.png)

## Screening Dimensions

- **Valuation:** P/E, forward P/E, PEG, price-to-book, price-to-sales
- **Growth:** revenue growth, EPS growth, and available estimates
- **Quality:** ROE, ROA, margins, and debt-to-equity
- **Income:** dividend yield and payout ratio
- **Technical:** RSI, price performance, volume, and beta

## Backtesting Features

The application supports SMA and EMA crossovers, RSI mean reversion, MACD, and Bollinger Band strategies. Performance views include return, CAGR, Sharpe ratio, Sortino ratio, maximum drawdown, win rate, equity curves, and trade-level output. Simulation inputs include commission, slippage, and position sizing.

## Run Locally

~~~bash
git clone https://github.com/ParBproject/-Stock-Screener-Strategy-Backtester-Insider-Institutional-Signal-Tracker-.git
cd ./-Stock-Screener-Strategy-Backtester-Insider-Institutional-Signal-Tracker-

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
~~~

Open http://localhost:8501.

## Repository Structure

~~~text
.
├── app.py
├── config.py
├── requirements.txt
├── home.png
├── screener.png
├── backtester.png
└── insider.png
~~~

## Skills Demonstrated

Python, financial-data integration, factor screening, technical indicators, historical backtesting, risk metrics, Streamlit, Plotly, data export, and decision-focused interface design.

## Responsible Use

This project is for educational and research purposes and does not provide financial advice. Historical performance and ownership activity do not predict future returns. External data can be delayed, incomplete, or revised.
