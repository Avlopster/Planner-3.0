# -*- coding: utf-8 -*-
"""Юнит-тесты для Planner — проверка расчётов и бизнес-логики."""
import sys
import os
import sqlite3

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pandas as pd
from datetime import date, timedelta

import database as db
import repository
from utils.date_utils import date_range_list
from utils.type_utils import safe_int


def _vacation_conn(vacations_list):
    """Создаёт in-memory SQLite с таблицей vacations и вставленными записями. vacations_list: [(employee_id, start, end), ...]."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE vacations (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           employee_id INTEGER NOT NULL,
           start_date DATE NOT NULL,
           end_date DATE NOT NULL)"""
    )
    for (emp_id, start, end) in vacations_list:
        conn.execute(
            "INSERT INTO vacations (employee_id, start_date, end_date) VALUES (?, ?, ?)",
            (emp_id, start.isoformat() if hasattr(start, 'isoformat') else start, end.isoformat() if hasattr(end, 'isoformat') else end),
        )
    conn.commit()
    return conn


class TestDateRangeList:
    """Тесты для date_range_list."""

    def test_single_day(self):
        d = date(2025, 1, 15)
        result = date_range_list(d, d)
        assert result == [d]

    def test_two_days(self):
        start = date(2025, 1, 15)
        end = date(2025, 1, 16)
        result = date_range_list(start, end)
        assert result == [start, end]

    def test_week(self):
        start = date(2025, 1, 1)
        end = date(2025, 1, 7)
        result = date_range_list(start, end)
        assert len(result) == 7
        assert result[0] == start
        assert result[-1] == end


class TestCheckVacationOverlap:
    """Тесты проверки пересечения отпусков через repository.check_vacation_overlap (in-memory БД)."""

    def test_no_overlap(self):
        conn = _vacation_conn([(1, date(2025, 1, 1), date(2025, 1, 10))])
        try:
            overlap, _ = repository.check_vacation_overlap(
                conn, 1, date(2025, 1, 15), date(2025, 1, 20)
            )
            assert overlap is False
        finally:
            conn.close()

    def test_overlap_same_period(self):
        conn = _vacation_conn([(1, date(2025, 1, 5), date(2025, 1, 15))])
        try:
            overlap, _ = repository.check_vacation_overlap(
                conn, 1, date(2025, 1, 10), date(2025, 1, 20)
            )
            assert overlap is True
        finally:
            conn.close()

    def test_overlap_inside(self):
        conn = _vacation_conn([(1, date(2025, 1, 1), date(2025, 1, 31))])
        try:
            overlap, _ = repository.check_vacation_overlap(
                conn, 1, date(2025, 1, 10), date(2025, 1, 15)
            )
            assert overlap is True
        finally:
            conn.close()

    def test_exclude_self_on_edit(self):
        conn = _vacation_conn([(1, date(2025, 1, 5), date(2025, 1, 15))])
        try:
            overlap, _ = repository.check_vacation_overlap(
                conn, 1, date(2025, 1, 5), date(2025, 1, 15), exclude_vacation_id=1
            )
            assert overlap is False
        finally:
            conn.close()

    def test_overlap_with_another(self):
        conn = _vacation_conn([
            (1, date(2025, 1, 1), date(2025, 1, 10)),
            (1, date(2025, 1, 20), date(2025, 1, 25)),
        ])
        try:
            overlap, _ = repository.check_vacation_overlap(
                conn, 1, date(2025, 1, 8), date(2025, 1, 22)
            )
            assert overlap is True
        finally:
            conn.close()


def department_load_summary_logic(employees, days_count, total_used, project_days=30, needed_multiplier=1.5):
    """Упрощённая логика сводки без БД."""
    total_capacity_days = 0.0
    for emp in employees:
        load_pct = emp.get('default_load_percent', 100)
        if pd.isna(load_pct):
            load_pct = 100
        total_capacity_days += (float(load_pct) / 100.0) * days_count

    free_capacity = total_capacity_days - total_used
    needed_for_one_project = needed_multiplier * project_days
    projects_possible = int(free_capacity // needed_for_one_project)
    missing_employees = 0
    if projects_possible < 1:
        missing_employees = int((needed_for_one_project - free_capacity) / needed_multiplier / project_days) + 1
    return {
        'total_capacity_days': total_capacity_days,
        'used_days': total_used,
        'free_days': free_capacity,
        'projects_possible': projects_possible,
        'missing_employees': missing_employees
    }


class TestDepartmentLoadSummary:
    """Тесты для department_load_summary."""

    def test_full_capacity(self):
        employees = [{'default_load_percent': 100}, {'default_load_percent': 100}]
        days = 30
        total_used = 0
        r = department_load_summary_logic(employees, days, total_used)
        assert r['total_capacity_days'] == 60
        assert r['free_days'] == 60
        assert r['projects_possible'] == 1  # 60 / 45

    def test_part_time_employee(self):
        employees = [{'default_load_percent': 50}, {'default_load_percent': 100}]
        days = 30
        total_used = 30
        r = department_load_summary_logic(employees, days, total_used)
        assert r['total_capacity_days'] == 45  # 15 + 30
        assert r['free_days'] == 15


def annual_capacity_formula(n_junior, n_senior, F, T, x, max_concurrent=4):
    """
    Чистая формула годовой ёмкости (без БД): N = min(N_junior, N_senior).
    F — эффективный фонд рабочих дней, T — длительность проекта, x — доля старшего на проект.
    """
    if T <= 0:
        return 0
    cycles = int(F // T)
    if n_senior <= 0 or x <= 0:
        P = 0
    else:
        P = min(max_concurrent, int(n_senior / x))
    N_junior = n_junior * cycles
    N_senior = P * cycles
    return min(N_junior, N_senior) if (n_junior > 0 and n_senior > 0) else 0


class TestAnnualCapacityFormula:
    """Тесты годовой формулы ёмкости проектов (по документу)."""

    def test_4_junior_3_senior_x025(self):
        # F=219, T=30 → cycles=7. x=0.25 → P=min(4,12)=4. N = min(28, 28)=28
        N = annual_capacity_formula(4, 3, F=219, T=30, x=0.25)
        assert N == 28

    def test_4_junior_3_senior_x08(self):
        # P=min(4, 3/0.8)=3. N_senior=21, N_junior=28 → N=21
        N = annual_capacity_formula(4, 3, F=219, T=30, x=0.8)
        assert N == 21

    def test_no_senior_zero_capacity(self):
        assert annual_capacity_formula(4, 0, F=219, T=30, x=0.25) == 0

    def test_no_junior_zero_capacity(self):
        assert annual_capacity_formula(0, 3, F=219, T=30, x=0.25) == 0


# ---------- Диаграмма Ганта: новая функциональность ----------
# Для фильтра «Только активные» на Ганте — только «В работе», планируемые исключаются
GANTT_ONLY_ACTIVE_STATUSES = ('В работе',)


def gantt_height_logic(n_rows):
    """Высота диаграммы Ганта: расширение вниз без потолка 800px."""
    return max(400, 32 * n_rows)


def gantt_filter_active_projects(df_proj):
    """Фильтр «Только активные проекты» по статусу (только «В работе», планируемые исключаются)."""
    status_col = 'status_name' if 'status_name' in df_proj.columns else 'status'
    return df_proj[df_proj[status_col].fillna('В работе').isin(GANTT_ONLY_ACTIVE_STATUSES)].copy()


def gantt_option_pairs_and_filter(df_proj, selected_labels):
    """Построение option_pairs и фильтрация по выбранным (мультиселект)."""
    status_col = 'status_name' if 'status_name' in df_proj.columns else 'status'
    option_pairs = [
        (f"{row['name']} — {row.get(status_col, 'В работе')}", row['id'])
        for _, row in df_proj.iterrows()
    ]
    selected_ids = [p[1] for p in option_pairs if p[0] in selected_labels]
    return df_proj[df_proj['id'].isin(selected_ids)].copy()


def gantt_project_completion_percent(project_id, display_date, phases_df):
    """
    Доля выполнения проекта (копия логики из Planner для тестов).
    Если есть колонка completion_percent — взвешенная по длительности этапов; иначе по дате.
    Возвращает 0.0–1.0; 0.0 если этапов нет.
    """
    if phases_df.empty:
        return 0.0
    proj_phases = phases_df[phases_df['project_id'] == project_id]
    if proj_phases.empty:
        return 0.0
    total_duration_days = 0
    completed_days = 0
    use_manual = 'completion_percent' in proj_phases.columns
    for _, ph in proj_phases.iterrows():
        start_d = pd.to_datetime(ph['start_date']).date() if ph['start_date'] else None
        end_d = pd.to_datetime(ph['end_date']).date() if ph['end_date'] else None
        if start_d is None or end_d is None:
            continue
        d_phase = max(0, (end_d - start_d).days)
        total_duration_days += d_phase
        if use_manual and ph.get('completion_percent') is not None:
            pct = safe_int(ph['completion_percent'], 0) or 0
            pct = min(100, max(0, pct))
            completed_days += d_phase * (pct / 100.0)
        else:
            if hasattr(display_date, 'date'):
                d = display_date.date()
            else:
                d = display_date
            if d >= end_d:
                completed_days += d_phase
            elif start_d <= d < end_d:
                completed_days += (d - start_d).days
    if total_duration_days <= 0:
        return 0.0
    return min(1.0, max(0.0, completed_days / total_duration_days))


class TestGanttHeight:
    """Тесты высоты диаграммы Ганта (расширение вниз)."""

    def test_min_height_400(self):
        assert gantt_height_logic(0) == 400
        assert gantt_height_logic(5) == 400  # 32*5=160 < 400

    def test_grows_with_rows(self):
        assert gantt_height_logic(20) == 640   # 32*20
        assert gantt_height_logic(25) == 800
        assert gantt_height_logic(50) == 1600
        assert gantt_height_logic(100) == 3200

    def test_no_cap_800(self):
        """Раньше было min(800, ...) — теперь высота не ограничена 800."""
        assert gantt_height_logic(30) == 960
        assert gantt_height_logic(100) == 3200


class TestGanttFilterActive:
    """Тесты фильтра «Только активные проекты»."""

    def test_keeps_only_in_work(self):
        """При фильтре «Только активные» остаются только проекты «В работе», планируемые исключаются."""
        df = pd.DataFrame([
            {'id': 1, 'name': 'A', 'status_name': 'В работе'},
            {'id': 2, 'name': 'B', 'status_name': 'Планируется'},
        ])
        out = gantt_filter_active_projects(df)
        assert len(out) == 1
        assert out.iloc[0]['id'] == 1
        assert out.iloc[0]['status_name'] == 'В работе'

    def test_filters_out_completed_cancelled(self):
        df = pd.DataFrame([
            {'id': 1, 'name': 'A', 'status_name': 'В работе'},
            {'id': 2, 'name': 'B', 'status_name': 'Завершён'},
            {'id': 3, 'name': 'C', 'status_name': 'Отменён'},
        ])
        out = gantt_filter_active_projects(df)
        assert len(out) == 1
        assert out.iloc[0]['id'] == 1

    def test_fillna_status(self):
        df = pd.DataFrame([
            {'id': 1, 'name': 'A', 'status_name': None},
        ])
        out = gantt_filter_active_projects(df)
        assert len(out) == 1  # fillna('В работе') → попадает в фильтр «только активные»


class TestGanttMultiselect:
    """Тесты мультиселекта «Проекты на диаграмме»."""

    def test_select_all(self):
        df = pd.DataFrame([
            {'id': 1, 'name': 'P1', 'status_name': 'В работе'},
            {'id': 2, 'name': 'P2', 'status_name': 'Планируется'},
        ])
        labels = [f"{r['name']} — {r['status_name']}" for _, r in df.iterrows()]
        out = gantt_option_pairs_and_filter(df, labels)
        assert len(out) == 2
        assert set(out['id']) == {1, 2}

    def test_select_one(self):
        df = pd.DataFrame([
            {'id': 1, 'name': 'P1', 'status_name': 'В работе'},
            {'id': 2, 'name': 'P2', 'status_name': 'Планируется'},
        ])
        labels = ['P2 — Планируется']
        out = gantt_option_pairs_and_filter(df, labels)
        assert len(out) == 1
        assert out.iloc[0]['id'] == 2

    def test_select_none_empty(self):
        df = pd.DataFrame([{'id': 1, 'name': 'P1', 'status_name': 'В работе'}])
        out = gantt_option_pairs_and_filter(df, [])
        assert len(out) == 0


class TestGanttProjectCompletionPercent:
    """Тесты расчёта процента выполнения проекта по этапам (заливка готовности на Ганте)."""

    def test_no_phases_returns_zero(self):
        phases = pd.DataFrame(columns=['project_id', 'start_date', 'end_date'])
        assert gantt_project_completion_percent(1, date(2025, 6, 15), phases) == 0.0
        phases = pd.DataFrame([{'project_id': 2, 'start_date': date(2025, 1, 1), 'end_date': date(2025, 1, 10)}])
        assert gantt_project_completion_percent(1, date(2025, 6, 15), phases) == 0.0

    def test_one_phase_fully_in_past_returns_one(self):
        phases = pd.DataFrame([
            {'project_id': 1, 'start_date': date(2025, 1, 1), 'end_date': date(2025, 1, 10)},
        ])
        assert gantt_project_completion_percent(1, date(2025, 1, 15), phases) == 1.0
        assert gantt_project_completion_percent(1, date(2025, 1, 10), phases) == 1.0

    def test_one_phase_display_date_inside_fractional(self):
        phases = pd.DataFrame([
            {'project_id': 1, 'start_date': date(2025, 1, 1), 'end_date': date(2025, 1, 11)},
        ])
        # 10 дней этап; на 2025-01-06 выполнено 5 дней (1..5 включительно = 5 дней)
        assert gantt_project_completion_percent(1, date(2025, 1, 6), phases) == pytest.approx(5 / 10)

    def test_one_phase_not_started_returns_zero(self):
        phases = pd.DataFrame([
            {'project_id': 1, 'start_date': date(2025, 6, 1), 'end_date': date(2025, 6, 10)},
        ])
        assert gantt_project_completion_percent(1, date(2025, 5, 15), phases) == 0.0

    def test_multiple_phases_mixed(self):
        phases = pd.DataFrame([
            {'project_id': 1, 'start_date': date(2025, 1, 1), 'end_date': date(2025, 1, 10)},   # 9 days, full
            {'project_id': 1, 'start_date': date(2025, 1, 11), 'end_date': date(2025, 1, 20)},  # 9 days, 0 (display before)
            {'project_id': 1, 'start_date': date(2025, 1, 21), 'end_date': date(2025, 1, 31)},  # 10 days, 5 done (21..25)
        ])
        # display_date = 2025-01-26: phase1 full 9, phase2 full 9, phase3: 5 days (21..25)
        # total 9+9+10=28, completed 9+9+5=23
        assert gantt_project_completion_percent(1, date(2025, 1, 26), phases) == pytest.approx(23 / 28)

    def test_result_clamped_to_one(self):
        phases = pd.DataFrame([
            {'project_id': 1, 'start_date': date(2025, 1, 1), 'end_date': date(2025, 1, 10)},
        ])
        assert gantt_project_completion_percent(1, date(2026, 1, 1), phases) == 1.0

    def test_completion_percent_weighted(self):
        """Готовность по полю completion_percent этапов (взвешенная по длительности)."""
        phases = pd.DataFrame([
            {'project_id': 1, 'start_date': date(2025, 1, 1), 'end_date': date(2025, 1, 11), 'completion_percent': 100},
            {'project_id': 1, 'start_date': date(2025, 1, 11), 'end_date': date(2025, 1, 21), 'completion_percent': 0},
        ])
        # 10 + 10 days; completed 10 + 0 = 10 -> 50%
        assert gantt_project_completion_percent(1, date(2025, 1, 1), phases) == pytest.approx(0.5)

    def test_completion_percent_all_hundred(self):
        phases = pd.DataFrame([
            {'project_id': 1, 'start_date': date(2025, 1, 1), 'end_date': date(2025, 1, 10), 'completion_percent': 100},
        ])
        assert gantt_project_completion_percent(1, date(2024, 1, 1), phases) == 1.0

    def test_completion_percent_mixed(self):
        phases = pd.DataFrame([
            {'project_id': 1, 'start_date': date(2025, 1, 1), 'end_date': date(2025, 1, 11), 'completion_percent': 50},
            {'project_id': 1, 'start_date': date(2025, 1, 11), 'end_date': date(2025, 1, 31), 'completion_percent': 100},
        ])
        # 10 + 20 days; completed 5 + 20 = 25 -> 25/30
        assert gantt_project_completion_percent(1, date(2025, 1, 1), phases) == pytest.approx(25 / 30)


def _minimal_app_conn():
    """In-memory БД с полной схемой и миграциями для тестов repository/load_calculator."""
    conn = sqlite3.connect(":memory:")
    db.init_schema(conn)
    db.run_migrations(conn)
    return conn


class TestPhaseCrud:
    """Тесты CRUD этапов через repository (insert_phase, load_phases, update_phase, delete_phase)."""

    def test_insert_and_load_phases(self):
        conn = _minimal_app_conn()
        try:
            status_id = repository.get_status_id_by_code(conn, "in_progress")
            assert status_id is not None
            proj_id = repository.insert_project(
                conn, "Тест", "", None, 50.0,
                "2025-01-01", "2025-12-31", False, status_id,
            )
            repository.insert_phase(
                conn, proj_id, "Этап 1", "Обычная работа",
                "2025-02-01", "2025-02-28", 0,
            )
            phases = repository.load_phases(conn)
            proj_phases = phases[phases["project_id"] == proj_id]
            assert len(proj_phases) == 1
            assert proj_phases.iloc[0]["name"] == "Этап 1"
        finally:
            conn.close()

    def test_update_phase(self):
        conn = _minimal_app_conn()
        try:
            status_id = repository.get_status_id_by_code(conn, "in_progress")
            proj_id = repository.insert_project(
                conn, "Проект", "", None, 50.0,
                "2025-01-01", "2025-12-31", False, status_id,
            )
            repository.insert_phase(
                conn, proj_id, "Старое", "Обычная работа",
                "2025-02-01", "2025-02-28", 0,
            )
            phases = repository.load_phases(conn)
            phase_id = int(phases[phases["project_id"] == proj_id].iloc[0]["id"])
            repository.update_phase(
                conn, phase_id, "Новое", "Командировка",
                "2025-02-05", "2025-02-20", 50, None,
            )
            phases = repository.load_phases(conn)
            row = phases[phases["id"] == phase_id].iloc[0]
            assert row["name"] == "Новое"
            assert row["phase_type"] == "Командировка"
        finally:
            conn.close()

    def test_delete_phase(self):
        conn = _minimal_app_conn()
        try:
            status_id = repository.get_status_id_by_code(conn, "in_progress")
            proj_id = repository.insert_project(
                conn, "Проект", "", None, 50.0,
                "2025-01-01", "2025-12-31", False, status_id,
            )
            repository.insert_phase(
                conn, proj_id, "Удаляемый", "Обычная работа",
                "2025-02-01", "2025-02-28", 0,
            )
            phases = repository.load_phases(conn)
            phase_id = int(phases[phases["project_id"] == proj_id].iloc[0]["id"])
            repository.delete_phase(conn, phase_id)
            phases = repository.load_phases(conn)
            assert phases[phases["project_id"] == proj_id].empty
        finally:
            conn.close()


class TestLoadCalculator:
    """Тесты load_calculator: employee_load_by_day, employee_load_by_day_batch (пустая/минимальная БД)."""

    def test_employee_load_by_day_empty_db(self):
        import load_calculator as lc
        conn = _minimal_app_conn()
        try:
            df = lc.employee_load_by_day(conn, 999, date(2025, 1, 1), date(2025, 1, 7))
            assert "date" in df.columns and "load" in df.columns
            assert len(df) == 7
            assert (df["load"] == 0.0).all()
        finally:
            conn.close()

    def test_employee_load_by_day_batch_empty_db(self):
        import load_calculator as lc
        conn = _minimal_app_conn()
        try:
            df = lc.employee_load_by_day_batch(
                conn, [1, 2], date(2025, 1, 1), date(2025, 1, 3)
            )
            assert list(df.columns) == ["employee_id", "date", "load"]
            assert len(df) == 2 * 3  # 2 employees, 3 days
            assert (df["load"] == 0.0).all()
        finally:
            conn.close()

    def test_employee_load_by_day_batch_empty_list(self):
        import load_calculator as lc
        conn = _minimal_app_conn()
        try:
            df = lc.employee_load_by_day_batch(conn, [], date(2025, 1, 1), date(2025, 1, 7))
            assert df.empty
            assert list(df.columns) == ["employee_id", "date", "load"]
        finally:
            conn.close()
