# -*- coding: utf-8 -*-
"""UI-компоненты: выбор даты (русские месяцы), кнопки меню."""
import calendar
import logging
from datetime import date, datetime
from typing import Optional, Union

import pandas as pd
import streamlit as st

import config as app_config
from utils.app_logging import log_user_facing_error


def ru_date_picker(
    label: str,
    default: Optional[Union[date, str, datetime, pd.Timestamp]] = None,
    key_prefix: Optional[str] = None,
) -> date:
    """Возвращает выбранную пользователем дату (русские месяцы в селектах)."""
    if default is None:
        default = date.today()
    elif isinstance(default, str):
        default = pd.to_datetime(default).date()
    elif isinstance(default, datetime):
        default = default.date()
    elif isinstance(default, pd.Timestamp):
        default = default.date()

    base_year = default.year
    years = list(range(base_year - 5, base_year + 6))

    day_key = f"{key_prefix}_day" if key_prefix else f"{label}_day"
    month_key = f"{key_prefix}_month" if key_prefix else f"{label}_month"
    year_key = f"{key_prefix}_year" if key_prefix else f"{label}_year"

    col1, col2, col3 = st.columns(3)
    with col1:
        day = st.selectbox(
            "День",
            options=list(range(1, 32)),
            index=default.day - 1,
            key=day_key
        )
    with col2:
        month_names = app_config.MONTHS_RU
        month_default_index = default.month - 1
        month_name = st.selectbox(
            "Месяц",
            options=month_names,
            index=month_default_index,
            key=month_key
        )
        month_num = app_config.MONTH_TO_NUM[month_name]
    with col3:
        year = st.selectbox(
            "Год",
            options=years,
            index=years.index(base_year) if base_year in years else 0,
            key=year_key
        )

    _, last_day = calendar.monthrange(year, month_num)
    if day > last_day:
        day = last_day

    try:
        selected_date = date(year, month_num, day)
        if day > last_day:
            warn = f"В {month_name} {year} только {last_day} дней. Выбран {last_day} число."
            log_user_facing_error(logging.WARNING, warn)
            st.warning(warn)
        return selected_date
    except ValueError:
        log_user_facing_error(logging.ERROR, "Некорректная дата")
        st.error("Некорректная дата")
        return default


def page_header(icon: str, title: str) -> None:
    """Единообразный заголовок страницы."""
    st.header(f"{icon} {title}")


def menu_button(label: str, icon: str) -> None:
    """Кнопка в сайдбаре для переключения раздела; при нажатии ставит menu и rerun."""
    if st.sidebar.button(f"{icon} {label}", key=f"menu_{label}"):
        st.session_state.menu = label
        st.rerun()
