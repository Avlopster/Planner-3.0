# -*- coding: utf-8 -*-
"""Годовая ёмкость проектов. Зависит от repository и load_calculator."""
import math
import sqlite3
from datetime import date
from typing import Any, Dict, Optional

import pandas as pd

import config as app_config
import repository
from load_calculator import get_average_vacation_days_per_employee


def annual_project_capacity(conn: sqlite3.Connection, year: Optional[int] = None) -> Dict[str, Any]:
    """
    Годовая ёмкость по составу (младшие/старшие), отпускам и типовой длительности проекта.
    Возвращает N_capacity, N_active, projects_possible, missing_juniors, missing_seniors и др.
    """
    if year is None:
        year = date.today().year
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)

    cfg = repository.load_capacity_config(conn)
    D = cfg['annual_working_days']
    V = get_average_vacation_days_per_employee(conn, year)
    T = cfg['typical_project_days']
    x = cfg['typical_lead_share']
    max_concurrent = cfg['max_concurrent_projects']
    junior_ids = cfg['capacity_role_junior_ids']
    senior_ids = cfg['capacity_role_senior_ids']

    employees = repository.load_employees(conn)
    if employees.empty:
        return {
            'N_capacity': 0, 'N_active': 0, 'projects_possible': 0, 'missing_employees': 0,
            'capacity_reason': 'ok', 'effective_fund_F': 0, 'typical_days_T': T,
            'n_junior': 0, 'n_senior': 0, 'P': 0,
            'capacity_if_add_1_junior': 0, 'capacity_if_add_1_senior': 0,
            'capacity_limited_by': None, 'missing_juniors': 0, 'missing_seniors': 0,
        }

    role_id = employees.get('role_id') if 'role_id' in employees.columns else None
    role_name = employees.get('role_name') if 'role_name' in employees.columns else None
    if role_name is None or role_name.empty:
        role_name = role_id.apply(lambda _: 'Без роли') if role_id is not None and not role_id.empty else pd.Series(dtype=object)
    if junior_ids and role_id is not None and not role_id.empty:
        n_junior = int(role_id.isin(junior_ids).sum())
    elif role_name is not None and not role_name.empty:
        n_junior = int((role_name == app_config.ROLE_JUNIOR).sum())
    else:
        n_junior = 0
    if senior_ids and role_id is not None and not role_id.empty:
        n_senior = int(role_id.isin(senior_ids).sum())
    elif role_name is not None and not role_name.empty:
        n_senior = int((role_name == app_config.ROLE_SENIOR).sum())
    else:
        n_senior = 0

    F = max(0, D - V)
    if T <= 0:
        cycles = 0
    else:
        cycles = int(F // T)

    if n_senior <= 0 or x <= 0:
        P = 0
    else:
        P = min(max_concurrent, int(n_senior / x))

    if cycles == 0 and T > 0 and F > 0 and (n_junior > 0 and n_senior > 0):
        N_capacity = min(n_junior, P)
    else:
        N_junior = n_junior * cycles
        N_senior = P * cycles
        N_capacity = min(N_junior, N_senior) if (n_junior > 0 and n_senior > 0) else 0

    active_statuses = repository.get_capacity_statuses(conn)
    projects = repository.load_projects(conn)
    N_active = 0
    for _, proj in projects.iterrows():
        if proj.get('status_name', 'В работе') not in active_statuses:
            continue
        start_val = proj.get('project_start')
        end_val = proj.get('project_end')
        if pd.isna(start_val) or pd.isna(end_val):
            continue
        try:
            start_d = pd.to_datetime(start_val).date() if start_val else None
            end_d = pd.to_datetime(end_val).date() if end_val else None
        except (ValueError, TypeError):
            continue
        if start_d is None or end_d is None:
            continue
        if end_d < year_start or start_d > year_end:
            continue
        N_active += 1

    def _capacity_from_counts(n_j, n_s):
        if n_j <= 0 or n_s <= 0:
            return 0
        p_val = min(max_concurrent, int(n_s / x)) if x > 0 else 0
        if cycles == 0 and T > 0 and F > 0:
            return min(n_j, p_val)
        return min(n_j * cycles, p_val * cycles)

    capacity_if_add_1_junior = _capacity_from_counts(n_junior + 1, n_senior)
    capacity_if_add_1_senior = _capacity_from_counts(n_junior, n_senior + 1)

    if N_capacity == 0:
        capacity_limited_by = None
    elif cycles == 0 and T > 0 and F > 0:
        capacity_limited_by = 'juniors' if n_junior <= P else 'seniors'
    else:
        capacity_limited_by = 'juniors' if (n_junior * cycles) <= (P * cycles) else 'seniors'

    projects_possible = max(0, N_capacity - N_active)
    missing_employees = 0
    capacity_reason = 'ok'
    if N_capacity == 0:
        if n_junior == 0 and n_senior == 0:
            capacity_reason = 'no_junior'
            missing_employees = 1
        elif n_junior == 0:
            capacity_reason = 'no_junior'
            missing_employees = 1
        elif n_senior == 0:
            capacity_reason = 'no_senior'
            missing_employees = 1
        elif cycles == 0 and T > 0 and F > 0:
            capacity_reason = 'cycles_zero'
            missing_employees = 0

    missing_juniors = 0
    missing_seniors = 0
    if capacity_limited_by == 'juniors' and (n_junior > 0 or n_senior > 0):
        if cycles == 0 and T > 0 and F > 0:
            missing_juniors = max(0, N_active + 1 - n_junior)
        else:
            need_j = math.ceil((N_active + 1) / cycles) if cycles > 0 else 0
            missing_juniors = max(0, need_j - n_junior)
    if capacity_limited_by == 'seniors' and P < max_concurrent and (n_junior > 0 or n_senior > 0):
        target_p = min(max_concurrent, P + 1)
        need_s = math.ceil(target_p * x)
        missing_seniors = max(0, need_s - n_senior)

    return {
        'N_capacity': N_capacity,
        'N_active': N_active,
        'projects_possible': projects_possible,
        'missing_employees': missing_employees,
        'capacity_reason': capacity_reason,
        'effective_fund_F': F,
        'typical_days_T': T,
        'n_junior': n_junior,
        'n_senior': n_senior,
        'P': P,
        'capacity_if_add_1_junior': capacity_if_add_1_junior,
        'capacity_if_add_1_senior': capacity_if_add_1_senior,
        'capacity_limited_by': capacity_limited_by,
        'missing_juniors': missing_juniors,
        'missing_seniors': missing_seniors,
    }
