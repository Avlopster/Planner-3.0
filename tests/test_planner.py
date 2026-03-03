# -*- coding: utf-8 -*-
"""Юнит-тесты для Planner — проверка расчётов и бизнес-логики."""
import sys
import os

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pandas as pd
from datetime import date, timedelta

from utils.date_utils import date_range_list
from utils.type_utils import safe_int


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


def check_vacation_overlap_logic(emp_vacations, new_start, new_end, exclude_vacation_id=None):
    """
    Логика проверки пересечения отпусков без БД.
    emp_vacations: list of dicts with keys id, start_date, end_date
    """
    for vac in emp_vacations:
        if exclude_vacation_id is not None and vac['id'] == exclude_vacation_id:
            continue
        vac_start = vac['start_date']
        vac_end = vac['end_date']
        if new_start <= vac_end and new_end >= vac_start:
            return True, vac
    return False, None


class TestCheckVacationOverlap:
    """Тесты для проверки пересечения отпусков."""

    def test_no_overlap(self):
        vacs = [
            {'id': 1, 'start_date': date(2025, 1, 1), 'end_date': date(2025, 1, 10)},
        ]
        overlap, _ = check_vacation_overlap_logic(
            vacs, date(2025, 1, 15), date(2025, 1, 20)
        )
        assert overlap is False

    def test_overlap_same_period(self):
        vacs = [
            {'id': 1, 'start_date': date(2025, 1, 5), 'end_date': date(2025, 1, 15)},
        ]
        overlap, _ = check_vacation_overlap_logic(
            vacs, date(2025, 1, 10), date(2025, 1, 20)
        )
        assert overlap is True

    def test_overlap_inside(self):
        vacs = [
            {'id': 1, 'start_date': date(2025, 1, 1), 'end_date': date(2025, 1, 31)},
        ]
        overlap, _ = check_vacation_overlap_logic(
            vacs, date(2025, 1, 10), date(2025, 1, 15)
        )
        assert overlap is True

    def test_exclude_self_on_edit(self):
        vacs = [
            {'id': 1, 'start_date': date(2025, 1, 5), 'end_date': date(2025, 1, 15)},
        ]
        overlap, _ = check_vacation_overlap_logic(
            vacs, date(2025, 1, 5), date(2025, 1, 15), exclude_vacation_id=1
        )
        assert overlap is False

    def test_overlap_with_another(self):
        vacs = [
            {'id': 1, 'start_date': date(2025, 1, 1), 'end_date': date(2025, 1, 10)},
            {'id': 2, 'start_date': date(2025, 1, 20), 'end_date': date(2025, 1, 25)},
        ]
        overlap, _ = check_vacation_overlap_logic(
            vacs, date(2025, 1, 8), date(2025, 1, 22)
        )
        assert overlap is True


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
