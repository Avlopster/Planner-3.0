# -*- coding: utf-8 -*-
"""Утилиты для парсинга дат и работы с диапазонами дат (импорт Excel, расчёты)."""
from datetime import date, timedelta
from typing import List, Optional, Union

import pandas as pd


def parse_date_from_excel(value: Union[str, date, pd.Timestamp, None]) -> date:
    """
    Приводит значение из Excel/DataFrame к date.
    Поддерживает: строки формата dd.mm.yyyy, pd.Timestamp, datetime, date.
    При None/pd.isna или невалидном формате возбуждает ValueError или TypeError.
    """
    if value is None or pd.isna(value):
        raise ValueError("Пустое или отсутствующее значение даты")
    if isinstance(value, date) and not isinstance(value, pd.Timestamp):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            raise ValueError("Пустая строка даты")
        try:
            from datetime import datetime
            return datetime.strptime(value, "%d.%m.%Y").date()
        except ValueError:
            try:
                return pd.to_datetime(value).date()
            except Exception as e:
                raise ValueError(f"Неверный формат даты: {e}") from e
    if isinstance(value, pd.Timestamp):
        return value.date()
    try:
        return pd.to_datetime(value).date()
    except Exception as e:
        raise TypeError(f"Неподдерживаемый тип даты: {type(value)}") from e


def date_range_list(start: date, end: date) -> List[date]:
    """Возвращает список дат от start до end включительно."""
    if start > end:
        return []
    delta = end - start
    return [start + timedelta(days=i) for i in range(delta.days + 1)]


def normalize_date(d: Optional[Union[str, date, pd.Timestamp]]) -> Optional[date]:
    """Приводит значение к date для сравнений. None, NaT и невалидные возвращают None."""
    if d is None or pd.isna(d):
        return None
    if isinstance(d, str):
        try:
            return pd.to_datetime(d).date()
        except (ValueError, TypeError):
            return None
    if isinstance(d, pd.Timestamp):
        return d.date()
    if isinstance(d, date):
        return d
    return None
