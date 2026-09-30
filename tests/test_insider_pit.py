"""Pins insider and fundamental release dates, including a backtest of the lag."""

import pandas as pd
import pytest

from modules.backtester import simulate_long_flat
from modules.fundamentals import latest_released
from modules.insider import (
    classify_side,
    filing_available_date,
    insider_long_signal,
    institutional_visible,
    score_filings,
    standardize_transactions,
    thirteen_f_public_date,
)


def test_blank_or_gift_rows_are_not_purchases():
    assert classify_side("", "", 100) == "other"
    assert classify_side("", "Stock Gift at price 0.00 per share.", 500) == "other"
    assert classify_side("", "Sale at price 10 per share.", 100) == "sell"
    assert classify_side("Purchase", "", 100) == "buy"
    assert classify_side("", "", -50) == "sell"


def test_missing_filing_date_waits_two_business_days():
    monday = pd.Timestamp("2024-01-08")
    friday = pd.Timestamp("2024-01-12")
    assert filing_available_date(monday) == pd.Timestamp("2024-01-10")
    assert filing_available_date(friday) == pd.Timestamp("2024-01-16")


def test_real_filing_date_is_used_and_a_stamp_before_the_trade_is_not():
    monday = pd.Timestamp("2024-01-08")
    assert filing_available_date(monday, "2024-01-09") == pd.Timestamp("2024-01-09")
    assert filing_available_date(monday, "2024-01-07") == pd.Timestamp("2024-01-10")


def test_cluster_is_invisible_until_the_filings_are_public():
    raw = pd.DataFrame(
        {
            "Start Date": ["2024-01-08", "2024-01-08", "2024-01-08"],
            "Insider": ["Ada", "Grace", "Lin"],
            "Transaction": ["Purchase", "Purchase", "Purchase"],
            "Shares": [10, 20, 30],
        }
    )
    standardized = standardize_transactions(raw)
    assert set(standardized["available_date"]) == {pd.Timestamp("2024-01-10")}

    before = score_filings(standardized, "2024-01-09")
    on_release = score_filings(standardized, "2024-01-10")
    assert before["cluster"] is False
    assert before["buyers"] == []
    assert before["label"] == "NEUTRAL"
    assert on_release["cluster"] is True
    assert on_release["label"] == "STRONG BUY"
    assert set(on_release["buyers"]) == {"ada", "grace", "lin"}


def test_repeat_purchases_by_one_insider_are_not_a_cluster():
    frame = pd.DataFrame(
        {
            "transaction_date": ["2024-01-08", "2024-01-08", "2024-01-08"],
            "filing_date": ["2024-01-10", "2024-01-10", "2024-01-10"],
            "insider": ["Ada", "Ada", "Ada"],
            "side": ["buy", "buy", "buy"],
            "shares": [1, 1, 1],
            "text": ["", "", ""],
            "available_date": ["2024-01-10", "2024-01-10", "2024-01-10"],
        }
    )
    scored = score_filings(frame, "2024-01-10")
    assert scored["cluster"] is False
    assert scored["buyers"] == ["ada"]


def test_prefiling_price_jump_is_not_in_the_backtest():
    index = pd.bdate_range("2024-01-08", periods=5)
    opens = pd.Series([10.0, 10.0, 10.0, 20.0, 20.0], index=index)
    raw = pd.DataFrame(
        {
            "Start Date": [index[0]],
            "Insider": ["Ada"],
            "Transaction": ["Purchase"],
            "Shares": [100],
        }
    )
    safe_signal = insider_long_signal(raw, index)
    assert safe_signal.tolist() == [0.0, 0.0, 1.0, 1.0, 1.0]

    cost = 0.002
    safe = simulate_long_flat(opens, safe_signal, commission=0.001, slippage=0.001)
    assert safe["metrics"]["total_return"] == pytest.approx(-cost)

    # Same simulator, but the signal pretends the Monday transaction was already public.
    biased_signal = pd.Series(1.0, index=index)
    biased = simulate_long_flat(opens, biased_signal, commission=0.001, slippage=0.001)
    assert biased["metrics"]["total_return"] == pytest.approx(1 - 2 * cost)
    assert safe["metrics"]["total_return"] < 0.05


def test_fundamentals_stay_hidden_until_available_date():
    filings = pd.DataFrame(
        {
            "period_end": ["2023-12-31", "2024-06-30"],
            "available_date": ["2024-03-01", "2024-08-01"],
            "pe": [10.0, 12.0],
        }
    )
    assert latest_released(filings, "2024-02-01") is None
    assert latest_released(filings, "2024-03-15")["pe"] == 10.0
    assert latest_released(filings, "2024-08-01")["pe"] == 12.0
    with pytest.raises(ValueError, match="period_end"):
        latest_released(filings.drop(columns=["available_date"]), "2024-08-01")


def test_thirteen_f_is_not_public_on_the_quarter_end():
    period_end = pd.Timestamp("2024-03-31")
    assert thirteen_f_public_date(period_end) == pd.Timestamp("2024-05-15")
    holders = pd.DataFrame({"holder": ["Fund"], "period_end": [period_end], "shares": [100]})
    assert institutional_visible(holders, "2024-05-14").empty
    visible = institutional_visible(holders, "2024-05-15")
    assert len(visible) == 1
    assert visible["public_date"].iloc[0] == pd.Timestamp("2024-05-15")


def test_thirteen_f_weekend_deadline_moves_to_monday():
    # 2015-12-31 plus 45 days is Sunday 2016-02-14. The due date is Monday.
    assert thirteen_f_public_date("2015-12-31") == pd.Timestamp("2016-02-15")
    assert institutional_visible(
        pd.DataFrame({"period_end": ["2015-12-31"], "shares": [1]}),
        "2016-02-14",
    ).empty


def test_yahoo_date_reported_is_treated_as_the_quarter_end():
    """Date Reported on the live institutional table lines up on quarter ends."""
    holders = pd.DataFrame(
        {
            "Date Reported": [pd.Timestamp("2026-06-30"), pd.Timestamp("2026-06-30")],
            "Holder": ["Blackrock Inc.", "Vanguard"],
            "Shares": [100, 80],
        }
    )
    assert institutional_visible(holders, "2026-07-01").empty
    visible = institutional_visible(holders, "2026-08-14")
    assert len(visible) == 2
    assert set(visible["public_date"]) == {pd.Timestamp("2026-08-14")}


def test_institutional_rows_without_a_period_end_are_withheld():
    dated = pd.DataFrame({"Date Reported": [pd.Timestamp("2024-03-31"), pd.NaT], "Shares": [1, 2]})
    visible = institutional_visible(dated, "2024-05-15")
    assert len(visible) == 1
    with pytest.raises(ValueError, match="quarter-end"):
        institutional_visible(pd.DataFrame({"Holder": ["Fund"], "Shares": [1]}), "2024-05-15")


def test_same_day_fundamentals_keep_the_later_fiscal_period():
    filings = pd.DataFrame(
        {
            "period_end": ["2024-03-31", "2024-06-30"],
            "available_date": ["2024-08-01", "2024-08-01"],
            "pe": [10.0, 12.0],
        }
    )
    reversed_rows = filings.iloc[::-1].reset_index(drop=True)
    assert latest_released(filings, "2024-08-01")["pe"] == 12.0
    assert latest_released(reversed_rows, "2024-08-01")["pe"] == 12.0


def test_vendor_sale_text_is_used_when_the_transaction_column_is_blank():
    raw = pd.DataFrame(
        {
            "Start Date": ["2024-01-08", "2024-01-08"],
            "Insider": ["Ada", "Ada"],
            "Position": ["Officer", "Officer"],
            "Transaction": ["", ""],
            "Text": ["Sale at price 10.00 per share.", ""],
            "Shares": [10, 50],
            "Ownership": ["D", "D"],
        }
    )
    out = standardize_transactions(raw)
    assert out["side"].tolist() == ["sell", "other"]
    assert list(out["available_date"]) == [pd.Timestamp("2024-01-10"), pd.Timestamp("2024-01-10")]
