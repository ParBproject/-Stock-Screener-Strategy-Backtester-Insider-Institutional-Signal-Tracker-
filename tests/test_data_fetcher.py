"""Data-access tests. yfinance is replaced; nothing here opens a socket."""

import pandas as pd
import pytest

from utils.data_fetcher import (
    DataFetchError,
    call_with_retry,
    fetch_fundamentals,
    fetch_insider_transactions,
    fetch_price_history,
    fetch_realtime_price,
    get_price_history,
    normalize_ohlcv,
    normalize_yahoo_info,
)


def test_price_request_uses_adjusted_bars_and_an_inclusive_end(monkeypatch):
    captured = {}

    def fake_download(ticker, start, end, **kwargs):
        captured["ticker"] = ticker
        captured["start"] = start
        captured["end"] = end
        captured.update(kwargs)
        index = pd.date_range("2024-01-02", periods=2, freq="B")
        return pd.DataFrame(
            {"Open": [10.0, 11.0], "High": [10.0, 11.0], "Low": [10.0, 11.0], "Close": [10.5, 11.5], "Volume": [100, 110]},
            index=index,
        )

    monkeypatch.setattr("utils.data_fetcher.yf.download", fake_download)
    frame = fetch_price_history("aapl", "2024-01-02", "2024-01-03")
    assert captured["ticker"] == "AAPL"
    assert captured["start"] == "2024-01-02"
    assert captured["end"] == "2024-01-04"
    assert captured["auto_adjust"] is True
    assert captured["threads"] is False
    assert list(frame["close"]) == [10.5, 11.5]


def test_raw_and_adjusted_close_are_not_mixed_across_a_split():
    """A 2-for-1 split must not look like a 40% crash when Adj Close is present."""
    raw = pd.DataFrame(
        {
            "Open": [10.0, 6.0],
            "High": [11.0, 7.0],
            "Low": [9.0, 5.0],
            "Close": [10.0, 6.0],
            "Adj Close": [10.0, 12.0],
            "Volume": [100, 200],
        },
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )
    normalized = normalize_ohlcv(raw)
    assert list(normalized["close"]) == [10.0, 12.0]
    assert list(normalized["open"]) == [10.0, 12.0]
    assert normalized["open"].iloc[1] / normalized["open"].iloc[0] - 1.0 == pytest.approx(0.20)
    assert "adj_close" not in normalized.columns
    assert list(normalized["volume"]) == [100, 200]


def test_multiindex_yahoo_frames_collapse_to_ohlcv():
    by_price = pd.MultiIndex.from_tuples([("Open", "AAPL"), ("Close", "AAPL"), ("High", "AAPL"), ("Low", "AAPL")])
    prices = pd.DataFrame([[1, 2, 1, 1]], columns=by_price)
    assert list(normalize_ohlcv(prices)["close"]) == [2]

    by_symbol = pd.MultiIndex.from_tuples([("AAPL", "Open"), ("AAPL", "Close")])
    other = pd.DataFrame([[3, 4]], columns=by_symbol)
    assert list(normalize_ohlcv(other)["open"]) == [3]


def test_empty_history_is_an_error_and_is_not_retried(monkeypatch):
    calls = {"n": 0}

    def fake_download(*_args, **_kwargs):
        calls["n"] += 1
        return pd.DataFrame()

    monkeypatch.setattr("utils.data_fetcher.yf.download", fake_download)
    with pytest.raises(DataFetchError, match="No price history"):
        fetch_price_history("ZZZZ", "2024-01-01", "2024-02-01")
    assert calls["n"] == 1


def test_rate_limit_retries_then_returns(monkeypatch):
    calls = {"n": 0}
    sleeps = []

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("429 too many requests")
        return "ok"

    monkeypatch.setattr("utils.data_fetcher.time.sleep", lambda seconds: sleeps.append(seconds))
    assert call_with_retry(flaky, base_delay=0.5) == "ok"
    assert calls["n"] == 3
    assert sleeps == [0.5, 1.0]


def test_unrelated_errors_are_not_retried_and_hide_the_raw_message():
    sleeps = []

    def bad():
        raise RuntimeError("https://example.test/secret-token-endpoint")

    with pytest.raises(DataFetchError, match="Try again") as caught:
        call_with_retry(bad, sleep=lambda _seconds: sleeps.append(1))
    assert sleeps == []
    assert "secret-token" not in str(caught.value)


def test_yahoo_info_units_match_the_screen_presets():
    normalized = normalize_yahoo_info(
        {
            "shortName": "Example",
            "trailingPE": 20,
            "returnOnEquity": 0.15,
            "dividendYield": 0.32,
            "debtToEquity": 150,
            "revenueGrowth": 0.10,
            "52WeekChange": 0.25,
        }
    )
    assert normalized["name"] == "Example"
    assert normalized["pe"] == 20
    assert normalized["roe"] == pytest.approx(15)
    assert normalized["div_yield"] == pytest.approx(0.32)
    assert normalized["debt_equity"] == pytest.approx(1.5)
    assert normalized["revenue_growth"] == pytest.approx(10)
    assert normalized["price_change_52w"] == pytest.approx(25)


def test_fundamentals_and_insiders_use_the_client_and_not_a_fixture(monkeypatch):
    class FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol
            self.info = {"shortName": "Example", "trailingPE": 12}
            self.insider_transactions = pd.DataFrame(
                {
                    "Start Date": [pd.Timestamp("2024-01-08")],
                    "Insider": ["Ada"],
                    "Transaction": ["Purchase"],
                    "Shares": [10],
                }
            )

    monkeypatch.setattr("utils.data_fetcher.yf.Ticker", FakeTicker)
    assert fetch_fundamentals("msft")["pe"] == 12
    filings = fetch_insider_transactions("msft")
    assert filings.loc[0, "available_date"] == pd.Timestamp("2024-01-10")
    assert filings.loc[0, "side"] == "buy"


def test_realtime_price_uses_the_last_two_closes(monkeypatch):
    def fake_download(*_args, **_kwargs):
        index = pd.date_range("2024-06-03", periods=2, freq="B")
        return pd.DataFrame(
            {"Open": [9.0, 10.0], "High": [9.0, 10.0], "Low": [9.0, 10.0], "Close": [9.5, 10.5], "Volume": [1, 1]},
            index=index,
        )

    monkeypatch.setattr("utils.data_fetcher.yf.download", fake_download)
    quote = fetch_realtime_price("AAPL")
    assert quote["price"] == pytest.approx(10.5)
    assert quote["prev_close"] == pytest.approx(9.5)


def test_public_price_getter_is_cached():
    assert hasattr(get_price_history, "clear")
