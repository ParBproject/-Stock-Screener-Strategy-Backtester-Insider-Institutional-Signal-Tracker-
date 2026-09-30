"""Screen filters fail closed when a value is missing."""

import pandas as pd
import pytest

from config import PRESETS
from modules.screener import FILTER_SPEC, apply_filters


def test_missing_pe_does_not_pass_a_max_pe_screen():
    frame = pd.DataFrame({"ticker": ["A", "B"], "pe": [10.0, None]})
    kept = apply_filters(frame, {"max_pe": 15})
    assert kept["ticker"].tolist() == ["A"]


def test_unknown_criterion_and_missing_column_raise():
    frame = pd.DataFrame({"pe": [10.0]})
    with pytest.raises(KeyError, match="Unknown"):
        apply_filters(frame, {"max_magic": 1})
    with pytest.raises(KeyError, match="roe"):
        apply_filters(frame, {"min_roe": 10})


def test_every_preset_uses_a_known_column():
    for criteria in PRESETS.values():
        for key in criteria:
            assert key in FILTER_SPEC


def test_value_preset_keeps_only_the_row_that_clears_every_hurdle():
    frame = pd.DataFrame(
        [
            {"ticker": "CHEAP", "pe": 12, "roe": 15, "pb": 1.5, "div_yield": 2.0, "debt_equity": 0.4},
            {"ticker": "RICH", "pe": 40, "roe": 15, "pb": 1.5, "div_yield": 2.0, "debt_equity": 0.4},
            {"ticker": "BLANK", "pe": 12, "roe": None, "pb": 1.5, "div_yield": 2.0, "debt_equity": 0.4},
        ]
    )
    kept = apply_filters(frame, PRESETS["Value Stocks"])
    assert kept["ticker"].tolist() == ["CHEAP"]
