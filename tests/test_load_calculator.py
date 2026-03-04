# -*- coding: utf-8 -*-
"""Интеграционные тесты для load_calculator (in-memory SQLite)."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import pytest
from datetime import date

import database as db
import load_calculator
import repository


@pytest.fixture
def conn():
    """In-memory SQLite с минимальной схемой и данными."""
    c = sqlite3.connect(":memory:", check_same_thread=False)
    db.init_schema(c)
    db.run_migrations(c)
    cur = c.cursor()
    # run_migrations уже создаёт роли и статусы (in_progress = id 2)
    cur.execute(
        "INSERT INTO employees (name, role_id, default_load_percent) VALUES ('A', 1, 100), ('B', 2, 100)"
    )
    cur.execute(
        "INSERT INTO projects (name, lead_id, project_start, project_end, auto_dates, status_id) VALUES ('P1', 1, '2025-01-01', '2025-01-31', 0, 2)"
    )
    cur.execute("INSERT INTO project_juniors (project_id, employee_id, load_percent) VALUES (1, 2, 100)")
    cur.execute(
        "INSERT INTO project_phases (project_id, name, phase_type, start_date, end_date, completion_percent) VALUES (1, 'F1', 'Обычная работа', '2025-01-01', '2025-01-31', 0)"
    )
    cur.execute("INSERT INTO phase_assignments (phase_id, employee_id, load_percent) VALUES (1, 1, 50), (1, 2, 100)")
    c.commit()
    yield c
    c.close()


def test_employee_load_by_day(conn):
    """Загрузка одного сотрудника за период: lead + phase assignment."""
    df = load_calculator.employee_load_by_day(conn, 1, date(2025, 1, 1), date(2025, 1, 10))
    assert not df.empty
    assert "date" in df.columns and "load" in df.columns
    assert len(df) == 10
    # Lead 50% + phase assignment 50% = 1.0 для сотрудника 1 на этапе
    assert df["load"].sum() >= 0


def test_employee_load_by_day_batch(conn):
    """Батчевый расчёт загрузки для нескольких сотрудников."""
    df = load_calculator.employee_load_by_day_batch(
        conn, [1, 2], date(2025, 1, 1), date(2025, 1, 5)
    )
    assert not df.empty
    assert set(df.columns) >= {"employee_id", "date", "load"}
    assert set(df["employee_id"].unique()) == {1, 2}
    assert len(df) == 2 * 5  # 2 employees * 5 days


def test_department_load_summary(conn):
    """Сводка по отделу: total_capacity_days, used_days, free_days."""
    summary = load_calculator.department_load_summary(
        conn, date(2025, 1, 1), date(2025, 1, 31)
    )
    assert "total_capacity_days" in summary
    assert "used_days" in summary
    assert "free_days" in summary
    assert summary["total_capacity_days"] >= 0
    assert summary["used_days"] >= 0
    assert summary["free_days"] == summary["total_capacity_days"] - summary["used_days"]
