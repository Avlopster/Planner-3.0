# -*- coding: utf-8 -*-
"""Дымовые проверки логики новых хелперов (без импорта Planner)."""
import pandas as pd
from datetime import date


def _normalize_date(d):
    if d is None:
        return None
    if isinstance(d, str):
        return pd.to_datetime(d).date()
    if isinstance(d, pd.Timestamp):
        return d.date()
    return d


def test_normalize_date():
    assert _normalize_date(date(2025, 1, 1)) == date(2025, 1, 1)
    assert _normalize_date(None) is None
    assert _normalize_date("2025-06-15") == date(2025, 6, 15)
    assert _normalize_date(pd.Timestamp("2025-06-15")) == date(2025, 6, 15)


def test_sources_structure():
    """Структура элементов get_employee_load_sources_by_day."""
    sample = [
        {"project_id": 1, "project_name": "P", "phase_id": 1, "phase_name": "Ph"},
        {"project_id": 1, "project_name": "P", "phase_id": None, "phase_name": None},
    ]
    for r in sample:
        assert "project_id" in r and "project_name" in r
        assert "phase_id" in r and "phase_name" in r


def test_phases_structure():
    """Структура элементов get_employee_phases_on_date."""
    sample = [{"project_id": 1, "project_name": "P", "phase_id": 1, "phase_name": "Ph"}]
    for r in sample:
        assert "project_id" in r and "project_name" in r and "phase_id" in r and "phase_name" in r


def test_candidates_structure():
    """Структура элементов get_replacement_candidates_for_phase."""
    sample = [{"employee_id": 1, "employee_name": "X", "load_that_day": 0.5}]
    for r in sample:
        assert "employee_id" in r and "employee_name" in r and "load_that_day" in r
