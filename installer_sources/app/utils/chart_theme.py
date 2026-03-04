# -*- coding: utf-8 -*-
"""Единая палитра и шаблон для графиков Plotly."""

CHART_TEMPLATE = "plotly_white"
COLOR_PALETTE = [
    "#2563eb", "#0ea5e9", "#06b6d4", "#8b5cf6", "#ec4899", "#f59e0b",
]


def apply_chart_theme(fig):
    """Применяет общий шаблон к фигуре Plotly."""
    fig.update_layout(template=CHART_TEMPLATE)
