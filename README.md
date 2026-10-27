# FinTools Pro

Streamlit app for screening a fixed list of stocks, backtesting a few technical rules, and reading insider filings. Prices and filings come from [yfinance](https://github.com/ranaroussi/yfinance). No API key.

## Pages

**Home.** Latest daily close for a few indices and a watchlist. This is the last close from the vendor, not a live tick.

**Screener.** Filters the names in `SP500_SAMPLE` (`config.py`) on the latest Yahoo snapshot. A missing value fails the filter. The list is companies that trade today, so a screen is conditioned on survival. It is not historical S&P 500 membership, and it is not a factor backtest.

**Backtester.** SMA crossover, EMA crossover, RSI, MACD, and Bollinger bands.

- A signal on day t may use that day's close. The order fills at the next session's open.
- Prices are split- and dividend-adjusted. Commission and slippage default to 0.1% of notional each and are charged when the position changes. A position fraction below 1 leaves the rest in cash.
- The comparison is buy-and-hold of the same ticker, filled the same way, fully invested, with the same costs on entry.
- Total return and CAGR are compounded. Sharpe and Sortino use 252 trading days and a risk-free rate of zero. They are left blank when volatility or downside deviation is zero.
- Excess return is ending strategy wealth divided by ending buy-and-hold wealth, minus one. Alpha is daily Jensen alpha with a zero risk-free rate, annualized by multiplying by 252.
- The last open is not marked, because there is no following open. A position still open at the end stays in the equity curve and is not counted as a win or a loss.
- Parameters are whatever you set on the page.

**Insider filings.** Buys and sells count only after a public date. If the feed has no filing date, the code waits two business days. That skip is weekends only, not exchange holidays. The score starts at 50, adds 15 per distinct buyer, subtracts 15 per distinct seller, and adds 20 when there are three or more buyers, then clamps to 0–100. Institutional rows are shown 45 days after quarter end, or the following Monday when that day is a weekend. They are not an input to the score.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501.

Tests mock the network:

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

## Layout

```text
app.py                 home page
config.py              ticker list, presets, backtest defaults
modules/               screen, backtest, filings, performance stats
utils/                 yfinance access, indicators, charts, secrets
pages/                 screener, backtester, insider tracker
tests/
```

Indicators are rolling and EWM calculations in `utils/indicators.py`. `utils.secrets.get_secret` reads the environment, then a local `.env`, then Streamlit secrets. `.env` is gitignored. `.env.example` is the empty pattern.

Not investment advice. Historical fills and filing activity do not predict returns. Vendor data can be missing or revised.
