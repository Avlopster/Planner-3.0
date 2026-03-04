# -*- coding: utf-8 -*-
"""Расчёт загрузки по дням, сводки по отделу, перегрузки. Зависит от repository."""
import sqlite3
from datetime import date, timedelta
from typing import List, Optional, Union

import pandas as pd

import config as app_config
import repository


def _annual_vacation_days_default(conn) -> int:
    """Значение по умолчанию для среднего отпуска (из config или config.py)."""
    v = repository.get_config(conn, 'annual_vacation_days', app_config.ANNUAL_VACATION_DAYS_DEFAULT)
    if v is None or (isinstance(v, str) and not v.strip()):
        return app_config.ANNUAL_VACATION_DAYS_DEFAULT
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return app_config.ANNUAL_VACATION_DAYS_DEFAULT
from utils.date_utils import date_range_list, normalize_date


def _working_days_in_range(
    d_start: Optional[Union[date, str]],
    d_end: Optional[Union[date, str]],
) -> int:
    """Число рабочих дней (пн–пт) в диапазоне [d_start, d_end] включительно."""
    if d_start is None or d_end is None or d_end < d_start:
        return 0
    if hasattr(d_start, 'date'):
        d_start = d_start.date() if callable(getattr(d_start, 'date')) else d_start
    if hasattr(d_end, 'date'):
        d_end = d_end.date() if callable(getattr(d_end, 'date')) else d_end
    n = 0
    delta = (d_end - d_start).days + 1
    for i in range(delta):
        d = d_start + timedelta(days=i)
        if d.weekday() < 5:
            n += 1
    return n


def get_average_vacation_days_per_employee(conn: sqlite3.Connection, year: Optional[int] = None) -> int:
    """Среднее число рабочих дней отпуска на одного сотрудника за год."""
    if year is None:
        year = date.today().year
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    employees = repository.load_employees(conn)
    if employees.empty:
        return _annual_vacation_days_default(conn)
    vacs = repository.load_vacations(conn)
    if vacs.empty:
        return _annual_vacation_days_default(conn)
    emp_days = {}
    for _, row in vacs.iterrows():
        eid = row.get('employee_id')
        if eid is None or pd.isna(eid):
            continue
        start_val = row.get('start_date')
        end_val = row.get('end_date')
        if pd.isna(start_val) or pd.isna(end_val):
            continue
        try:
            vs = pd.to_datetime(start_val).date()
            ve = pd.to_datetime(end_val).date()
        except (ValueError, TypeError):
            continue
        overlap_start = max(vs, year_start)
        overlap_end = min(ve, year_end)
        if overlap_end < overlap_start:
            continue
        days = _working_days_in_range(overlap_start, overlap_end)
        emp_days[eid] = emp_days.get(eid, 0) + days
    n_employees = len(employees)
    if n_employees == 0:
        return _annual_vacation_days_default(conn)
    total_days = sum(emp_days.values())
    if total_days == 0:
        return _annual_vacation_days_default(conn)
    return round(total_days / n_employees)


def employee_load_by_day(
    conn: sqlite3.Connection,
    employee_id: int,
    start_date: Union[date, str],
    end_date: Union[date, str],
    ignore_vacations: bool = False,
) -> pd.DataFrame:
    """Загрузка сотрудника по дням."""
    start_date = pd.to_datetime(start_date)
    end_date = pd.to_datetime(end_date)
    dates = date_range_list(start_date.date() if hasattr(start_date, 'date') else start_date, end_date.date() if hasattr(end_date, 'date') else end_date)
    df = pd.DataFrame({'date': dates, 'load': 0.0})

    vacs = repository.get_employee_vacations(conn, employee_id)
    vacation_periods = [(pd.to_datetime(v['start_date']), pd.to_datetime(v['end_date'])) for _, v in vacs.iterrows()]

    projects = repository.load_projects(conn)
    juniors = repository.load_project_juniors(conn)
    phases = repository.load_phases(conn)
    phase_assignments = repository.load_phase_assignments(conn)

    for _, proj in projects.iterrows():
        if proj.get('auto_dates'):
            proj_phases = phases[phases['project_id'] == proj['id']]
            if proj_phases.empty:
                continue
            start_ser = pd.to_datetime(proj_phases['start_date'], errors='coerce').dropna()
            end_ser = pd.to_datetime(proj_phases['end_date'], errors='coerce').dropna()
            if start_ser.empty or end_ser.empty:
                continue
            proj_start = start_ser.min()
            proj_end = end_ser.max()
        else:
            proj_start = pd.to_datetime(proj['project_start'])
            proj_end = pd.to_datetime(proj['project_end'])

        project_workers = []
        if proj.get('lead_id') and proj['lead_id'] == employee_id:
            project_workers.append(('lead', proj['lead_load_percent'] / 100.0))
        proj_jun = juniors[juniors['project_id'] == proj['id']]
        for _, j in proj_jun.iterrows():
            if j['employee_id'] == employee_id:
                project_workers.append(('junior', j['load_percent'] / 100.0))

        if not project_workers:
            continue

        def _to_date(x):
            return x.date() if hasattr(x, 'date') and callable(getattr(x, 'date')) else x

        proj_start_d = _to_date(proj_start)
        proj_end_d = _to_date(proj_end)
        if pd.isna(proj_start_d) or pd.isna(proj_end_d):
            continue

        for i, row in df.iterrows():
            d = row['date']
            d_date = _to_date(d)
            if d_date < proj_start_d or d_date > proj_end_d:
                continue
            in_vacation = any(_to_date(vs) <= d_date <= _to_date(ve) for vs, ve in vacation_periods)
            if in_vacation and not ignore_vacations:
                continue
            day_phase = None
            for _, ph in phases[phases['project_id'] == proj['id']].iterrows():
                ph_start = pd.to_datetime(ph['start_date'])
                ph_end = pd.to_datetime(ph['end_date'])
                if pd.isna(ph_start) or pd.isna(ph_end):
                    continue
                if _to_date(ph_start) <= d_date <= _to_date(ph_end):
                    day_phase = ph
                    break
            if day_phase is not None:
                assigns = phase_assignments[phase_assignments['phase_id'] == day_phase['id']]
                if not assigns.empty:
                    assigned = assigns[assigns['employee_id'] == employee_id]
                    if not assigned.empty:
                        df.at[i, 'load'] += assigned.iloc[0]['load_percent'] / 100.0
                else:
                    if day_phase['phase_type'] == 'Командировка':
                        df.at[i, 'load'] += 1.0
                    else:
                        for _, load_val in project_workers:
                            df.at[i, 'load'] += load_val
            else:
                for _, load_val in project_workers:
                    df.at[i, 'load'] += load_val
    return df


def employee_load_by_day_batch(
    conn: sqlite3.Connection,
    employee_ids: List[int],
    start_date: Union[date, str],
    end_date: Union[date, str],
    ignore_vacations: bool = False,
) -> pd.DataFrame:
    """Загрузка по дням для нескольких сотрудников за один проход (employee_id, date, load)."""
    if not employee_ids:
        return pd.DataFrame(columns=['employee_id', 'date', 'load'])
    start_d = normalize_date(start_date)
    end_d = normalize_date(end_date)
    if start_d is None:
        start_d = pd.to_datetime(start_date).date()
    if end_d is None:
        end_d = pd.to_datetime(end_date).date()
    dates = date_range_list(start_d, end_d)
    emp_set = set(employee_ids)
    # (employee_id, date) -> load
    load_map = {}
    for eid in emp_set:
        for d in dates:
            load_map[(eid, d)] = 0.0

    vacs = repository.load_vacations(conn)
    def _to_date(x):
        return x.date() if hasattr(x, 'date') and callable(getattr(x, 'date')) else x
    vacation_by_emp = {}
    for eid in emp_set:
        ev = vacs[vacs['employee_id'] == eid]
        vacation_by_emp[eid] = [(pd.to_datetime(r['start_date']), pd.to_datetime(r['end_date'])) for _, r in ev.iterrows()]

    projects = repository.load_projects(conn)
    juniors = repository.load_project_juniors(conn)
    phases = repository.load_phases(conn)
    phase_assignments = repository.load_phase_assignments(conn)

    for _, proj in projects.iterrows():
        if proj.get('auto_dates'):
            proj_phases = phases[phases['project_id'] == proj['id']]
            if proj_phases.empty:
                continue
            start_ser = pd.to_datetime(proj_phases['start_date'], errors='coerce').dropna()
            end_ser = pd.to_datetime(proj_phases['end_date'], errors='coerce').dropna()
            if start_ser.empty or end_ser.empty:
                continue
            proj_start = start_ser.min()
            proj_end = end_ser.max()
        else:
            proj_start = pd.to_datetime(proj['project_start'])
            proj_end = pd.to_datetime(proj['project_end'])
        proj_start_d = _to_date(proj_start)
        proj_end_d = _to_date(proj_end)
        if pd.isna(proj_start_d) or pd.isna(proj_end_d):
            continue
        project_workers = []
        if proj.get('lead_id') and proj['lead_id'] in emp_set:
            project_workers.append((proj['lead_id'], proj['lead_load_percent'] / 100.0))
        for _, j in juniors[juniors['project_id'] == proj['id']].iterrows():
            if j['employee_id'] in emp_set:
                project_workers.append((j['employee_id'], j['load_percent'] / 100.0))
        if not project_workers:
            continue
        proj_phases = phases[phases['project_id'] == proj['id']]
        for d in dates:
            if d < proj_start_d or d > proj_end_d:
                continue
            for emp_id, load_frac in project_workers:
                if not ignore_vacations and vacation_by_emp.get(emp_id):
                    if any(_to_date(vs) <= d <= _to_date(ve) for vs, ve in vacation_by_emp[emp_id]):
                        continue
                day_phase = None
                for _, ph in proj_phases.iterrows():
                    ph_start = pd.to_datetime(ph['start_date'])
                    ph_end = pd.to_datetime(ph['end_date'])
                    if pd.isna(ph_start) or pd.isna(ph_end):
                        continue
                    if _to_date(ph_start) <= d <= _to_date(ph_end):
                        day_phase = ph
                        break
                key = (emp_id, d)
                if key not in load_map:
                    load_map[key] = 0.0
                if day_phase is not None:
                    assigns = phase_assignments[phase_assignments['phase_id'] == day_phase['id']]
                    if not assigns.empty:
                        assigned = assigns[assigns['employee_id'] == emp_id]
                        if not assigned.empty:
                            load_map[key] += assigned.iloc[0]['load_percent'] / 100.0
                    else:
                        if day_phase['phase_type'] == 'Командировка':
                            load_map[key] += 1.0
                        else:
                            load_map[key] += load_frac
                else:
                    load_map[key] += load_frac

    rows = [{'employee_id': eid, 'date': d, 'load': load_map.get((eid, d), 0.0)} for eid in emp_set for d in dates]
    return pd.DataFrame(rows)


def get_employee_load_sources_by_day(
    conn: sqlite3.Connection, employee_id: int, day_date: Union[date, str]
) -> List[dict]:
    """Список проектов/этапов, по которым сотруднику начисляется загрузка в день."""
    day_date = normalize_date(day_date)
    if not day_date:
        return []
    projects = repository.load_projects(conn)
    juniors = repository.load_project_juniors(conn)
    phases = repository.load_phases(conn)
    phase_assignments = repository.load_phase_assignments(conn)
    result = []
    for _, proj in projects.iterrows():
        if proj.get('auto_dates'):
            proj_phases = phases[phases['project_id'] == proj['id']]
            if proj_phases.empty:
                continue
            start_ser = pd.to_datetime(proj_phases['start_date'], errors='coerce').dropna()
            end_ser = pd.to_datetime(proj_phases['end_date'], errors='coerce').dropna()
            if start_ser.empty or end_ser.empty:
                continue
            proj_start = start_ser.min().date()
            proj_end = end_ser.max().date()
        else:
            if not proj.get('project_start') or not proj.get('project_end'):
                continue
            proj_start = normalize_date(proj['project_start'])
            proj_end = normalize_date(proj['project_end'])
        if day_date < proj_start or day_date > proj_end:
            continue
        project_workers = []
        if proj.get('lead_id') and proj['lead_id'] == employee_id:
            project_workers.append(('lead', proj['lead_load_percent'] / 100.0))
        proj_jun = juniors[juniors['project_id'] == proj['id']]
        for _, j in proj_jun.iterrows():
            if j['employee_id'] == employee_id:
                project_workers.append(('junior', j['load_percent'] / 100.0))
        if not project_workers:
            continue
        day_phase = None
        for _, ph in phases[phases['project_id'] == proj['id']].iterrows():
            ph_start = normalize_date(ph['start_date'])
            ph_end = normalize_date(ph['end_date'])
            if ph_start <= day_date <= ph_end:
                day_phase = ph
                break
        proj_name = proj['name']
        if day_phase is not None:
            assigns = phase_assignments[phase_assignments['phase_id'] == day_phase['id']]
            if not assigns.empty:
                assigned = assigns[assigns['employee_id'] == employee_id]
                if not assigned.empty:
                    result.append({'project_id': proj['id'], 'project_name': proj_name, 'phase_id': day_phase['id'], 'phase_name': day_phase['name']})
            else:
                result.append({'project_id': proj['id'], 'project_name': proj_name, 'phase_id': day_phase['id'], 'phase_name': day_phase['name']})
        else:
            result.append({'project_id': proj['id'], 'project_name': proj_name, 'phase_id': None, 'phase_name': None})
    return result


def get_employee_phases_on_date(conn, employee_id, day_date) -> List[dict]:
    """Этапы (и проекты), в которые входит day_date и в которых участвует сотрудник."""
    day_date = normalize_date(day_date)
    if not day_date:
        return []
    projects = repository.load_projects(conn)
    juniors = repository.load_project_juniors(conn)
    phases = repository.load_phases(conn)
    phase_assignments = repository.load_phase_assignments(conn)
    result = []
    for _, proj in projects.iterrows():
        project_workers = []
        if proj.get('lead_id') and proj['lead_id'] == employee_id:
            project_workers.append(True)
        proj_jun = juniors[juniors['project_id'] == proj['id']]
        for _, j in proj_jun.iterrows():
            if j['employee_id'] == employee_id:
                project_workers.append(True)
                break
        if not project_workers:
            continue
        proj_phases = phases[phases['project_id'] == proj['id']]
        for _, ph in proj_phases.iterrows():
            ph_start = normalize_date(ph['start_date'])
            ph_end = normalize_date(ph['end_date'])
            if ph_start <= day_date <= ph_end:
                assigns = phase_assignments[phase_assignments['phase_id'] == ph['id']]
                if not assigns.empty:
                    if assigns[assigns['employee_id'] == employee_id].empty:
                        continue
                result.append({'project_id': proj['id'], 'project_name': proj['name'], 'phase_id': ph['id'], 'phase_name': ph['name']})
    return result


def get_replacement_candidates_for_phase(conn, phase_id, exclude_employee_id, day_date, max_candidates=3, load_threshold=0.8) -> List[dict]:
    """Кандидаты для замены на этапе в указанный день."""
    day_date = normalize_date(day_date)
    if not day_date:
        return []
    phases = repository.load_phases(conn)
    phase_row = phases[phases['id'] == phase_id]
    if phase_row.empty:
        return []
    phase = phase_row.iloc[0]
    project_id = phase['project_id']
    projects = repository.load_projects(conn)
    proj_rows = projects[projects['id'] == project_id]
    if proj_rows.empty:
        return []
    proj = proj_rows.iloc[0]
    juniors = repository.load_project_juniors(conn)
    phase_assignments = repository.load_phase_assignments(conn)
    df_emp = repository.load_employees(conn)
    candidate_ids = set()
    if proj.get('lead_id') and proj['lead_id'] != exclude_employee_id:
        candidate_ids.add(proj['lead_id'])
    for _, j in juniors[juniors['project_id'] == project_id].iterrows():
        if j['employee_id'] != exclude_employee_id:
            candidate_ids.add(j['employee_id'])
    for _, a in phase_assignments[phase_assignments['phase_id'] == phase_id].iterrows():
        if a['employee_id'] != exclude_employee_id:
            candidate_ids.add(a['employee_id'])
    if len(candidate_ids) < max_candidates:
        for _, emp in df_emp.iterrows():
            if emp['id'] != exclude_employee_id and emp['id'] not in candidate_ids:
                candidate_ids.add(emp['id'])
            if len(candidate_ids) >= max_candidates * 2:
                break
    df_vac = repository.load_vacations(conn)
    candidates = []
    for emp_id in candidate_ids:
        vacs = df_vac[df_vac['employee_id'] == emp_id]
        in_vacation = False
        for _, vac in vacs.iterrows():
            vs = normalize_date(vac['start_date'])
            ve = normalize_date(vac['end_date'])
            if vs is None or ve is None or pd.isna(vs) or pd.isna(ve):
                continue
            if vs <= day_date <= ve:
                in_vacation = True
                break
        if in_vacation:
            continue
        ld = employee_load_by_day(conn, emp_id, day_date, day_date)
        load_val = ld['load'].iloc[0] if not ld.empty else 0.0
        if load_val < load_threshold:
            candidates.append({
                'employee_id': emp_id,
                'employee_name': repository.get_employee_name(conn, emp_id),
                'load_that_day': load_val
            })
    candidates.sort(key=lambda x: x['load_that_day'])
    return candidates[:max_candidates]


def department_load_summary(
    conn: sqlite3.Connection,
    start_date: Union[date, str],
    end_date: Union[date, str],
) -> dict:
    """Сводка загрузки по отделу за период (всего/использовано/свободно человеко-дней)."""
    employees = repository.load_employees(conn)
    if employees.empty:
        days_count = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days + 1
        return {
            'total_capacity_days': 0.0, 'used_days': 0.0, 'free_days': 0.0,
            'projects_possible': 0, 'missing_employees': 0,
        }
    employee_ids = employees['id'].dropna().astype(int).tolist()
    batch_df = employee_load_by_day_batch(conn, employee_ids, start_date, end_date)
    days_count = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days + 1
    total_capacity_days = 0.0
    for _, emp in employees.iterrows():
        load_pct = emp.get('default_load_percent', 100)
        if pd.isna(load_pct):
            load_pct = 100
        total_capacity_days += (float(load_pct) / 100.0) * days_count
    total_used = 0.0
    if not batch_df.empty:
        total_used = batch_df['load'].clip(upper=1.0).sum()
    free_capacity = total_capacity_days - total_used
    project_days = 30
    needed_for_one_project = 1.5 * project_days
    projects_possible_legacy = int(free_capacity // needed_for_one_project)
    missing_employees = 0
    if projects_possible_legacy < 1:
        missing_employees = int((needed_for_one_project - free_capacity) / 1.5 / 30) + 1
    return {
        'total_capacity_days': total_capacity_days,
        'used_days': total_used,
        'free_days': free_capacity,
        'projects_possible': projects_possible_legacy,
        'missing_employees': missing_employees
    }


def overload_shortfall(
    conn: sqlite3.Connection,
    start_date: Union[date, str],
    end_date: Union[date, str],
) -> dict:
    """По перегрузкам за период возвращает эквивалент недостающих FTE (equivalent_missing_fte и др.)."""
    employees = repository.load_employees(conn)
    if employees.empty:
        days_count = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days + 1
        return {'total_overload_ftedays': 0.0, 'days_in_period': max(1, days_count), 'equivalent_missing_fte': 0.0}
    employee_ids = employees['id'].dropna().astype(int).tolist()
    batch_df = employee_load_by_day_batch(conn, employee_ids, start_date, end_date)
    days_count = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days + 1
    days_in_period = max(1, days_count)
    total_overload_ftedays = 0.0
    if not batch_df.empty:
        over = batch_df[batch_df['load'] > 1.0]
        total_overload_ftedays = (over['load'] - 1.0).sum()
    equivalent_missing_fte = round(total_overload_ftedays / days_in_period, 2)
    return {
        'total_overload_ftedays': total_overload_ftedays,
        'days_in_period': days_in_period,
        'equivalent_missing_fte': equivalent_missing_fte,
    }
