# FinTools Pro

Streamlit app for screening a fixed list of stocks, backtesting a few technical rules, and reading insider filings. Prices and filings come from [yfinance](https://github.com/ranaroussi/yfinance). No API key.

## Live demo

https://YOUR-APP-NAME.streamlit.app

Replace `YOUR-APP-NAME` with the subdomain from Streamlit Community Cloud after the first deploy. The steps are under [Deploy](#deploy).

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

## Deploy

Community Cloud installs the root `requirements.txt` and runs `app.py`. `requirements-dev.txt` is for local tests only. `.streamlit/config.toml` sets the dark theme. Use Python 3.11 so the deploy matches CI. Community Cloud does not read a `runtime.txt`; the version is chosen in Advanced settings.

1. Open [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub. Deploying needs admin access to this repo.
2. Choose **Create app**, then **Yup, I have an app**.
3. Set the repository to `ParBproject/-Stock-Screener-Strategy-Backtester-Insider-Institutional-Signal-Tracker-`, the branch to `main`, and the main file path to `app.py`.
4. Optional: pick a custom subdomain. That name replaces `YOUR-APP-NAME` in the Live demo link.
5. Open **Advanced settings** and select Python **3.11**. Leave Secrets empty. This app does not need a key. Do not commit `.streamlit/secrets.toml`.
6. Deploy and wait for the first build. Installing the pinned packages can take a few minutes. Later pushes to `main` update the running app.

## Layout

```text
app.py                 home page
config.py              ticker list, presets, backtest defaults
.streamlit/config.toml theme for local runs and Community Cloud
modules/               screen, backtest, filings, performance stats
utils/                 yfinance access, indicators, charts, secrets
pages/                 screener, backtester, insider tracker
tests/
```

Indicators are rolling and EWM calculations in `utils/indicators.py`. `utils.secrets.get_secret` reads the environment, then a local `.env`, then Streamlit secrets. `.env` is gitignored. `.env.example` is the empty pattern.

Not investment advice. Historical fills and filing activity do not predict returns. Vendor data can be missing or revised.
