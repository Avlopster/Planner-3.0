# -*- coding: utf-8 -*-
"""Утилиты приведения типов из БД: safe_int, safe_date_series (в т.ч. для bytes)."""
from typing import Any, Optional

import pandas as pd


def safe_int(x: Any, default: Optional[int] = None) -> Optional[int]:
    """Приводит значение из БД к int (в т.ч. bytes, str, float). Для невалидных возвращает default."""
    if x is None or pd.isna(x):
        return default
    if isinstance(x, int) and not isinstance(x, bool):
        return x
    if isinstance(x, bytes):
        s = x.decode('utf-8', errors='replace').strip().strip('\x00').strip()
        if not s:
            return 0 if default is None else default
        try:
            return int(s)
        except ValueError:
            return 0 if default is None else default
    if isinstance(x, (float, str)):
        try:
            return int(float(x))
        except (ValueError, TypeError):
            return default
    try:
        return int(x)
    except (ValueError, TypeError):
        return 0 if default is None else default


def safe_date_series(ser: pd.Series) -> pd.Series:
    """Приводит серию дат из БД к date (в т.ч. если значения — bytes)."""
    if ser is None or ser.empty:
        return ser

    def to_date(v):
        if v is None or pd.isna(v):
            return pd.NaT
        if isinstance(v, bytes):
            v = v.decode('utf-8', errors='replace').strip()
        try:
            return pd.to_datetime(v, errors='coerce')
        except Exception:
            return pd.NaT

    if ser.dtype == object or ser.dtype.name == 'object' or (ser.size > 0 and isinstance(ser.iloc[0], bytes)):
        return ser.apply(to_date).dt.date
    return pd.to_datetime(ser, errors='coerce').dt.date
