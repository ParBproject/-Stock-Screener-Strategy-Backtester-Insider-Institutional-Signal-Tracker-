"""The equity chart has to show the benchmark, not only the strategy."""

import pandas as pd

from utils.charts import equity_curve_chart


def test_benchmark_is_a_second_trace():
    index = pd.to_datetime(["2024-01-02", "2024-01-03"])
    equity = pd.Series([100.0, 110.0], index=index)
    benchmark = pd.Series([100.0, 105.0], index=index)
    alone = equity_curve_chart(equity)
    compared = equity_curve_chart(equity, benchmark=benchmark, title="AAPL")
    assert len(alone.data) == 1
    assert alone.data[0].name == "Strategy"
    assert len(compared.data) == 2
    assert compared.data[1].name == "Buy & hold"
    assert list(compared.data[1].y) == [100.0, 105.0]
    assert compared.layout.title.text == "AAPL"
