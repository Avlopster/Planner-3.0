# -*- coding: utf-8 -*-
"""Тесты логики дашборда: статусы проектов, состав по проектам, ближайшие сроки, неполные проекты, этапы."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pandas as pd
from datetime import date, timedelta


# --- Логика дашборда (копия расчётов из Planner для тестов без Streamlit) ---

def dashboard_status_counts(df_projects):
    """KPI по статусам: считает количество по каждому статусу (колонка status_name или status)."""
    status_col = 'status_name' if 'status_name' in df_projects.columns else 'status'
    status = df_projects[status_col].fillna('В работе')
    return {
        'В работе': int(status.eq('В работе').sum()),
        'Планируется': int(status.eq('Планируется').sum()),
        'Завершён': int(status.eq('Завершён').sum()),
        'Отменён': int(status.eq('Отменён').sum()),
        'Всего': len(df_projects),
    }


def dashboard_project_team_rows(df_projects, df_employees, df_juniors):
    """Строит строки таблицы «Распределение сотрудников по проектам»."""
    emp_names = df_employees.set_index('id')['name'].to_dict()
    rows = []
    for _, proj in df_projects.iterrows():
        lead_id = proj.get('lead_id')
        lead_name = emp_names.get(lead_id, "—") if pd.notna(lead_id) and lead_id else "—"
        juniors_on_proj = df_juniors[df_juniors['project_id'] == proj['id']]
        junior_names = [emp_names.get(eid, "?") for eid in juniors_on_proj['employee_id'] if pd.notna(eid)]
        total_people = (1 if lead_id and pd.notna(lead_id) else 0) + len(junior_names)
        rows.append({
            'Проект': proj['name'],
            'Статус': proj.get('status_name', proj.get('status', 'В работе')) or 'В работе',
            'Ведущий': lead_name,
            'Рядовые': ", ".join(junior_names) if junior_names else "—",
            'Всего человек': total_people
        })
    return rows


def dashboard_upcoming(df_projects, today, horizon_days=30):
    """Проекты со статусом В работе/Планируется и датой окончания в ближайшие horizon_days дней."""
    end_limit = today + timedelta(days=horizon_days)
    status_col = 'status_name' if 'status_name' in df_projects.columns else 'status'
    status_fill = df_projects[status_col].fillna('В работе')
    active = status_fill.isin(['В работе', 'Планируется'])
    project_end = pd.to_datetime(df_projects['project_end']).dt.date
    mask = active & (project_end >= today) & (project_end <= end_limit)
    return df_projects[mask]


def dashboard_incomplete(df_projects, df_juniors, active_statuses=None):
    """Активные проекты без ведущего или без рядовых."""
    if active_statuses is None:
        active_statuses = ['В работе', 'Планируется']
    status_col = 'status_name' if 'status_name' in df_projects.columns else 'status'
    status_fill = df_projects[status_col].fillna('В работе') if status_col in df_projects.columns else pd.Series(['В работе'] * len(df_projects), index=df_projects.index)
    rows = []
    for _, proj in df_projects.iterrows():
        if status_fill.loc[proj.name] not in active_statuses:
            continue
        no_lead = not (proj.get('lead_id') and pd.notna(proj.get('lead_id')))
        no_juniors = df_juniors[df_juniors['project_id'] == proj['id']].empty
        if no_lead or no_juniors:
            rows.append({'Проект': proj['name'], 'Нет ведущего': no_lead, 'Нет рядовых': no_juniors})
    return rows


def dashboard_phase_counts(df_phases, df_projects):
    """Количество этапов по project_id с названием проекта."""
    if df_phases.empty:
        return pd.DataFrame(columns=['project_id', 'Этапов', 'Проект'])
    counts = df_phases.groupby('project_id').size().reset_index(name='Этапов')
    id_to_name = df_projects.set_index('id')['name'].to_dict()
    counts['Проект'] = counts['project_id'].map(lambda pid: id_to_name.get(pid, f"ID {pid}"))
    return counts


# --- Тесты ---

class TestDashboardStatusCounts:
    def test_empty_projects(self):
        df = pd.DataFrame(columns=['id', 'name', 'status_name'])
        r = dashboard_status_counts(df)
        assert r == {'В работе': 0, 'Планируется': 0, 'Завершён': 0, 'Отменён': 0, 'Всего': 0}

    def test_single_status(self):
        df = pd.DataFrame([
            {'id': 1, 'name': 'P1', 'status_name': 'В работе'},
            {'id': 2, 'name': 'P2', 'status_name': 'В работе'},
        ])
        r = dashboard_status_counts(df)
        assert r['В работе'] == 2
        assert r['Всего'] == 2
        assert r['Планируется'] == 0

    def test_all_statuses_and_nan(self):
        df = pd.DataFrame([
            {'id': 1, 'name': 'A', 'status_name': 'Планируется'},
            {'id': 2, 'name': 'B', 'status_name': 'В работе'},
            {'id': 3, 'name': 'C', 'status_name': 'Завершён'},
            {'id': 4, 'name': 'D', 'status_name': 'Отменён'},
            {'id': 5, 'name': 'E', 'status_name': pd.NA},
        ])
        r = dashboard_status_counts(df)
        assert r['Планируется'] == 1
        assert r['В работе'] == 2  # B + E (NA -> В работе)
        assert r['Завершён'] == 1
        assert r['Отменён'] == 1
        assert r['Всего'] == 5


class TestDashboardProjectTeamRows:
    def test_no_employees(self):
        df_proj = pd.DataFrame([{'id': 1, 'name': 'P1', 'lead_id': None, 'status_name': 'В работе'}])
        df_emp = pd.DataFrame(columns=['id', 'name'])
        df_jun = pd.DataFrame(columns=['project_id', 'employee_id'])
        rows = dashboard_project_team_rows(df_proj, df_emp, df_jun)
        assert len(rows) == 1
        assert rows[0]['Проект'] == 'P1'
        assert rows[0]['Ведущий'] == "—"
        assert rows[0]['Рядовые'] == "—"
        assert rows[0]['Всего человек'] == 0

    def test_lead_and_juniors(self):
        df_proj = pd.DataFrame([{'id': 1, 'name': 'P1', 'lead_id': 10, 'status_name': 'В работе'}])
        df_emp = pd.DataFrame([{'id': 10, 'name': 'Иванов'}, {'id': 20, 'name': 'Петров'}])
        df_jun = pd.DataFrame([{'project_id': 1, 'employee_id': 20}])
        rows = dashboard_project_team_rows(df_proj, df_emp, df_jun)
        assert len(rows) == 1
        assert rows[0]['Ведущий'] == 'Иванов'
        assert rows[0]['Рядовые'] == 'Петров'
        assert rows[0]['Всего человек'] == 2

    def test_two_projects(self):
        df_proj = pd.DataFrame([
            {'id': 1, 'name': 'A', 'lead_id': 1, 'status_name': 'В работе'},
            {'id': 2, 'name': 'B', 'lead_id': None, 'status_name': 'В работе'},
        ])
        df_emp = pd.DataFrame([{'id': 1, 'name': 'Lead'}])
        df_jun = pd.DataFrame([{'project_id': 1, 'employee_id': 1}])  # один рядовой на A
        rows = dashboard_project_team_rows(df_proj, df_emp, df_jun)
        assert len(rows) == 2
        by_name = {r['Проект']: r for r in rows}
        assert by_name['A']['Всего человек'] == 2  # lead + 1 junior
        assert by_name['B']['Всего человек'] == 0


class TestDashboardUpcoming:
    def test_empty(self):
        df = pd.DataFrame(columns=['id', 'name', 'status_name', 'project_end'])
        today = date(2025, 6, 1)
        u = dashboard_upcoming(df, today)
        assert u.empty

    def test_within_horizon(self):
        today = date(2025, 6, 1)
        df = pd.DataFrame([
            {'id': 1, 'name': 'P1', 'status_name': 'В работе', 'project_end': date(2025, 6, 15)},
            {'id': 2, 'name': 'P2', 'status_name': 'Завершён', 'project_end': date(2025, 6, 20)},
        ])
        u = dashboard_upcoming(df, today, horizon_days=30)
        assert len(u) == 1
        assert u.iloc[0]['name'] == 'P1'

    def test_past_end_excluded(self):
        today = date(2025, 6, 1)
        df = pd.DataFrame([
            {'id': 1, 'name': 'P1', 'status_name': 'В работе', 'project_end': date(2025, 5, 1)},
        ])
        u = dashboard_upcoming(df, today, horizon_days=30)
        assert len(u) == 0


class TestDashboardIncomplete:
    def test_all_complete(self):
        df_proj = pd.DataFrame([
            {'id': 1, 'name': 'P1', 'lead_id': 1, 'status_name': 'В работе'},
        ])
        df_jun = pd.DataFrame([{'project_id': 1, 'employee_id': 2}])
        inc = dashboard_incomplete(df_proj, df_jun)
        assert len(inc) == 0

    def test_no_lead(self):
        df_proj = pd.DataFrame([
            {'id': 1, 'name': 'P1', 'lead_id': None, 'status_name': 'В работе'},
        ])
        df_jun = pd.DataFrame([{'project_id': 1, 'employee_id': 1}])
        inc = dashboard_incomplete(df_proj, df_jun)
        assert len(inc) == 1
        assert inc[0]['Нет ведущего'] is True
        assert inc[0]['Нет рядовых'] is False

    def test_no_juniors(self):
        df_proj = pd.DataFrame([
            {'id': 1, 'name': 'P1', 'lead_id': 1, 'status_name': 'В работе'},
        ])
        df_jun = pd.DataFrame(columns=['project_id', 'employee_id'])
        inc = dashboard_incomplete(df_proj, df_jun)
        assert len(inc) == 1
        assert inc[0]['Нет ведущего'] is False
        assert inc[0]['Нет рядовых'] is True

    def test_completed_ignored(self):
        df_proj = pd.DataFrame([
            {'id': 1, 'name': 'P1', 'lead_id': None, 'status_name': 'Завершён'},
        ])
        df_jun = pd.DataFrame(columns=['project_id', 'employee_id'])
        inc = dashboard_incomplete(df_proj, df_jun)
        assert len(inc) == 0


class TestDashboardPhaseCounts:
    def test_empty_phases(self):
        df_ph = pd.DataFrame(columns=['project_id', 'name'])
        df_proj = pd.DataFrame([{'id': 1, 'name': 'P1'}])
        cnt = dashboard_phase_counts(df_ph, df_proj)
        assert cnt.shape[0] == 0

    def test_phases_per_project(self):
        df_ph = pd.DataFrame([
            {'project_id': 1, 'name': 'Э1'},
            {'project_id': 1, 'name': 'Э2'},
            {'project_id': 2, 'name': 'Э1'},
        ])
        df_proj = pd.DataFrame([{'id': 1, 'name': 'Proj1'}, {'id': 2, 'name': 'Proj2'}])
        cnt = dashboard_phase_counts(df_ph, df_proj)
        assert len(cnt) == 2
        p1 = cnt[cnt['project_id'] == 1].iloc[0]
        assert p1['Этапов'] == 2 and p1['Проект'] == 'Proj1'
        p2 = cnt[cnt['project_id'] == 2].iloc[0]
        assert p2['Этапов'] == 1 and p2['Проект'] == 'Proj2'
