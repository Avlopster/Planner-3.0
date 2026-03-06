# -*- coding: utf-8 -*-
"""Единая палитра и шаблон для графиков Plotly."""

import pandas as pd

CHART_TEMPLATE = "plotly_white"
COLOR_PALETTE = [
    "#2563eb", "#0ea5e9", "#06b6d4", "#8b5cf6", "#ec4899", "#f59e0b",
]


def apply_chart_theme(fig):
    """Применяет общий шаблон к фигуре Plotly."""
    fig.update_layout(template=CHART_TEMPLATE)


def apply_weekly_date_axis(fig, tickfont_size: int = 10, start_date=None, end_date=None):
    """Применяет недельную разбивку оси X и подписи вида: Неделя N (dd.mm-dd.mm)."""
    base_kwargs = dict(
        showgrid=True,
        gridwidth=0.5,
        linewidth=0.5,
        tickfont=dict(size=tickfont_size),
    )

    if start_date is None or end_date is None:
        fig.update_xaxes(
            tickformat="%d.%m.%Y",
            dtick=7 * 24 * 60 * 60 * 1000,
            tick0="2000-01-03",
            ticklabelmode="period",
            **base_kwargs,
        )
        return

    start_ts = pd.to_datetime(start_date, errors="coerce")
    end_ts = pd.to_datetime(end_date, errors="coerce")
    if pd.isna(start_ts) or pd.isna(end_ts):
        fig.update_xaxes(tickformat="%d.%m.%Y", **base_kwargs)
        return
    if end_ts < start_ts:
        start_ts, end_ts = end_ts, start_ts

    start_ts = start_ts.normalize()
    end_ts = end_ts.normalize()
    week_start = start_ts - pd.to_timedelta(start_ts.weekday(), unit="D")

    tickvals = []
    ticktext = []
    cur = week_start
    while cur <= end_ts:
        week_end = min(cur + pd.Timedelta(days=6), end_ts)
        week_no = int(cur.isocalendar().week)
        tickvals.append(cur)
        ticktext.append(f"Неделя {week_no} ({cur:%d.%m}-{week_end:%d.%m})")
        cur = cur + pd.Timedelta(days=7)

    fig.update_xaxes(
        tickmode="array",
        tickvals=tickvals,
        ticktext=ticktext,
        tickangle=-20,
        **base_kwargs,
    )
