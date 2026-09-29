"""Plotly figures for the dashboard."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from config import PLOTLY_LAYOUT, THEME


def equity_curve_chart(equity: pd.Series, title: str = "Equity"):
    """Line chart of a backtest equity curve. Values are whatever the engine produced."""
    figure = go.Figure(
        go.Scatter(
            x=list(equity.index),
            y=[float(value) for value in equity.tolist()],
            mode="lines",
            line=dict(color=THEME["accent"], width=2),
            name="Equity",
        )
    )
    layout = dict(PLOTLY_LAYOUT)
    layout["title"] = title
    layout["yaxis"] = dict(gridcolor=THEME["border"], zeroline=False, showgrid=True, tickprefix="$")
    figure.update_layout(**layout)
    return figure
