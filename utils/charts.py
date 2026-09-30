"""Plotly figures for the dashboard."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from config import PLOTLY_LAYOUT, THEME


def equity_curve_chart(equity: pd.Series, title: str = "Equity", benchmark: pd.Series | None = None):
    """Line chart of a backtest equity curve, with buy-and-hold when supplied."""
    figure = go.Figure(
        go.Scatter(
            x=list(equity.index),
            y=[float(value) for value in equity.tolist()],
            mode="lines",
            line=dict(color=THEME["accent"], width=2),
            name="Strategy",
        )
    )
    if benchmark is not None:
        figure.add_trace(
            go.Scatter(
                x=list(benchmark.index),
                y=[float(value) for value in benchmark.tolist()],
                mode="lines",
                line=dict(color=THEME["text_muted"], width=2),
                name="Buy & hold",
            )
        )
    layout = dict(PLOTLY_LAYOUT)
    layout["title"] = title
    layout["yaxis"] = dict(gridcolor=THEME["border"], zeroline=False, showgrid=True, tickprefix="$")
    figure.update_layout(**layout)
    return figure
