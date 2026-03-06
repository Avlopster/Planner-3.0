# -*- coding: utf-8 -*-
"""Страница «Дашборд»: KPI по проектам, распределение сотрудников, загрузка, прогноз."""
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

import capacity as capacity_module
import capacity_ui
import load_calculator
import repository
from utils.type_utils import safe_int
from utils.chart_theme import COLOR_PALETTE, apply_chart_theme
from components import page_header


def render(conn, db_path=None):
    """Отрисовка страницы «Дашборд»: KPI по проектам, загрузка, прогноз. conn — подключение к БД."""
    page_header("🖥️", "Дашборд")
    df_projects = repository.load_projects(conn)
    df_employees = repository.load_employees(conn)
    df_juniors = repository.load_project_juniors(conn)
    df_phases = repository.load_phases(conn)
    if not df_projects.empty:
        df_projects = df_projects.copy()
        df_projects['status_fill'] = df_projects['status_name'].fillna('Не указан')

    if df_projects.empty:
        st.info("Нет проектов. Добавьте проекты в разделе «Проекты и этапы».")
        return

    status_counts = df_projects['status_fill'].value_counts()
    in_work = int(status_counts.get('В работе', 0)) if 'В работе' in status_counts.index else 0
    planned = int(status_counts.get('Планируется', 0)) if 'Планируется' in status_counts.index else 0
    completed = int(status_counts.get('Завершён', 0)) if 'Завершён' in status_counts.index else 0
    cancelled = int(status_counts.get('Отменён', 0)) if 'Отменён' in status_counts.index else 0
    not_set = int(status_counts.get('Не указан', 0)) if 'Не указан' in status_counts.index else 0
    total_projects = len(df_projects)

    with st.container():
        kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)
        kpi1.metric("В работе", in_work)
        kpi2.metric("Планируется", planned)
        kpi3.metric("Завершён", completed)
        kpi4.metric("Отменён", cancelled)
        kpi5.metric("Не указан", not_set)
        kpi6.metric("Всего проектов", total_projects)
    st.divider()

    emp_names = df_employees.set_index('id')['name'].to_dict()
    status_df = df_projects['status_fill'].value_counts().reset_index()
    status_df.columns = ['Статус', 'Количество']
    project_team_rows = []
    for _, proj in df_projects.iterrows():
        lead_id = proj.get('lead_id')
        lead_name = emp_names.get(lead_id, "—") if pd.notna(lead_id) and lead_id else "—"
        juniors_on_proj = df_juniors[df_juniors['project_id'] == proj['id']]
        junior_names = [emp_names.get(eid, "?") for eid in juniors_on_proj['employee_id'] if pd.notna(eid)]
        total_people = (1 if lead_id and pd.notna(lead_id) else 0) + len(junior_names)
        project_team_rows.append({
            'Проект': proj['name'],
            'Статус': proj.get('status_fill', proj.get('status_name', 'В работе')),
            'Ведущий': lead_name,
            'Рядовые': ", ".join(junior_names) if junior_names else "—",
            'Всего человек': total_people
        })
    df_team = pd.DataFrame(project_team_rows)
    fig_status = None
    if not status_df.empty:
        fig_status = px.pie(status_df, values='Количество', names='Статус', title='Распределение по статусам',
                            color_discrete_sequence=COLOR_PALETTE)
        apply_chart_theme(fig_status)
    fig_team = None
    if not df_team.empty:
        df_chart = df_team.sort_values('Всего человек', ascending=True)
        fig_team = px.bar(df_chart, x='Всего человек', y='Проект', orientation='h', title='Число сотрудников по проектам',
                          color_discrete_sequence=COLOR_PALETTE)
        apply_chart_theme(fig_team)

    col_status, col_team = st.columns(2)
    with col_status:
        st.subheader("📊 Проекты по статусам")
        if fig_status is not None:
            st.plotly_chart(fig_status, width='stretch')
        else:
            st.caption("Нет данных.")
    with col_team:
        st.subheader("👥 Распределение сотрудников по проектам")
        st.dataframe(df_team, width='stretch', hide_index=True)
        if fig_team is not None:
            st.plotly_chart(fig_team, width='stretch')
    st.divider()

    if 'department' in df_employees.columns and df_employees['department'].notna().any() and (df_employees['department'].astype(str).str.strip() != '').any():
        st.subheader("📁 Участие отделов в проектах")
        dept_proj = []
        for _, proj in df_projects.iterrows():
            pid = proj['id']
            lead_id = proj.get('lead_id')
            emp_ids = set()
            if pd.notna(lead_id) and lead_id:
                emp_ids.add(lead_id)
            for eid in df_juniors[df_juniors['project_id'] == pid]['employee_id']:
                if pd.notna(eid):
                    emp_ids.add(eid)
            for eid in emp_ids:
                emp_rows = df_employees[df_employees['id'] == eid]
                if not emp_rows.empty:
                    emp_row = emp_rows.iloc[0]
                    dept = emp_row.get('department') or ''
                    if pd.isna(dept):
                        dept = ''
                    dept = str(dept).strip()
                    if dept:
                        dept_proj.append({'Отдел': dept, 'Проект': proj['name'], 'Сотрудник': emp_names.get(eid, '?')})
        if dept_proj:
            df_dept = pd.DataFrame(dept_proj)
            dept_counts = df_dept.groupby(['Отдел', 'Проект']).size().reset_index(name='Человек')
            fig_dept = px.bar(dept_counts, x='Отдел', y='Человек', color='Проект', barmode='stack', title='Сотрудники отделов по проектам',
                              color_discrete_sequence=COLOR_PALETTE)
            apply_chart_theme(fig_dept)
            st.plotly_chart(fig_dept, width='stretch')
        else:
            st.caption("Нет данных по отделам для участников проектов.")
    else:
        st.caption("Для отображения по отделам заполните поле «Отдел» у сотрудников.")
    st.divider()

    today = date.today()
    horizon_days = 30
    end_limit = today + timedelta(days=horizon_days)
    active_statuses = list(repository.get_active_statuses(conn))
    proj_end = pd.to_datetime(df_projects['project_end'], errors='coerce').dt.date
    valid_end = proj_end.notna()
    upcoming = df_projects[(df_projects['status_fill'].isin(active_statuses)) & valid_end & (proj_end >= today) & (proj_end <= end_limit)]
    upcoming = upcoming.copy()
    upcoming['project_end'] = pd.to_datetime(upcoming['project_end'], errors='coerce').dt.date
    start_str = today.isoformat()
    end_str = (today + timedelta(days=30)).isoformat()

    col_deadlines, col_load = st.columns(2)
    with col_deadlines:
        st.subheader("📅 Ближайшие сроки окончания проектов")
        if not upcoming.empty:
            upcoming_display = []
            for _, r in upcoming.iterrows():
                lead_name = emp_names.get(r.get('lead_id'), "—") if pd.notna(r.get('lead_id')) else "—"
                upcoming_display.append({'Проект': r['name'], 'Дата окончания': r['project_end'], 'Ведущий': lead_name})
            st.dataframe(pd.DataFrame(upcoming_display), width='stretch', hide_index=True)
        else:
            st.info("Нет проектов со сроком окончания в ближайшие 30 дней.")
    with col_load:
        st.subheader("📈 Загрузка (сводка на 30 дней)")
        if not df_employees.empty:
            summary = load_calculator.department_load_summary(conn, start_str, end_str)
            capacity = capacity_module.annual_project_capacity(conn)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Всего человеко-дней", f"{summary['total_capacity_days']:.0f}")
            c2.metric("Использовано", f"{summary['used_days']:.0f}")
            c3.metric("Свободно", f"{summary['free_days']:.0f}")
            c4.metric("Проектов можно взять", capacity['projects_possible'])
            st.caption("Проектов можно взять — по годовой ёмкости отдела (состав технических специалистов и руководителей, отпуска, активные проекты в текущем году).")
            _reason = capacity.get('capacity_reason', 'ok')
            if _reason == 'no_junior':
                st.warning("Для расчёта ёмкости нужны сотрудники с ролями для **технических специалистов**. Назначьте роли в справочнике или настройте привязку ролей в разделе «Конфигурация».")
            elif _reason == 'no_senior':
                st.warning("Для расчёта ёмкости нужны сотрудники с ролями для **руководителей**. Назначьте роли в справочнике или настройте привязку ролей в разделе «Конфигурация».")
            elif _reason == 'cycles_zero':
                F_val = capacity.get('effective_fund_F', 0)
                T_val = capacity.get('typical_days_T', 0)
                st.warning(f"Годовая ёмкость нулевая: типовая длительность проекта (**{T_val}** дн.) не помещается в эффективный фонд (**{F_val}** дн.) в году. Уменьшите «Типовую длительность проекта» или увеличьте «Рабочих дней в году» в разделе «Конфигурация».")
            elif capacity.get('missing_employees', 0) > 0:
                st.warning(f"Для ещё одного типового проекта не хватает порядка {capacity['missing_employees']} сотрудников.")
            shortfall = load_calculator.overload_shortfall(conn, start_str, end_str)
            forecast_rows = capacity_ui.build_forecast_table_rows(
                capacity, shortfall, period_label="30 дней"
            )
            if forecast_rows:
                df_forecast = pd.DataFrame(forecast_rows)
                st.dataframe(df_forecast, column_config={"Блок": st.column_config.TextColumn("Блок", width="medium"), "Содержание": st.column_config.TextColumn("Содержание", width="large")}, hide_index=True)
            cap_j = capacity.get('capacity_if_add_1_junior', 0)
            cap_s = capacity.get('capacity_if_add_1_senior', 0)
            N_active = capacity.get('N_active', 0)
            poss = capacity.get('projects_possible', 0)
            extra_if_1_junior = max(0, cap_j - N_active) - poss
            extra_if_1_senior = max(0, cap_s - N_active) - poss
            with st.expander("📋 Прогноз: если добавить сотрудников"):
                st.caption("С учётом уже запланированных проектов в году.")
                if extra_if_1_junior > 0 or extra_if_1_senior > 0:
                    if extra_if_1_junior > 0:
                        st.markdown(f"- **+1 технический специалист:** ёмкость станет {cap_j}, можно взять ещё **{extra_if_1_junior}** проект(ов).")
                    if extra_if_1_senior > 0:
                        st.markdown(f"- **+1 руководитель:** ёмкость станет {cap_s}, можно взять ещё **{extra_if_1_senior}** проект(ов).")
                else:
                    limited = capacity.get('capacity_limited_by')
                    n_j = capacity.get('n_junior', 0)
                    n_s = capacity.get('n_senior', 0)
                    P_val = capacity.get('P', 0)
                    if limited == 'juniors':
                        st.markdown(f"При текущем составе дополнительный набор не увеличит число проектов: **ёмкость ограничена числом технических специалистов** ({n_j}). Добавление руководителя не даст новых проектов, пока не вырастет число технических специалистов.")
                    elif limited == 'seniors':
                        st.markdown(f"При текущем составе дополнительный набор не увеличит число проектов: **ёмкость ограничена числом руководителей или лимитом одновременных проектов** ({n_s} руководителей, P = {P_val}). По формуле каждый проект ведёт один ведущий (руководитель); максимум одновременных проектов P = min(лимит, руководители/x). Поэтому **найм технических специалистов не даст новых проектов** — нужны именно руководители.")
                    else:
                        st.markdown("При текущем составе дополнительный набор не увеличит число проектов (ёмкость ограничена составом или параметрами формулы).")
        else:
            st.warning("Нет сотрудников для расчёта загрузки.")
    st.divider()

    col_incomplete, col_phases = st.columns(2)
    with col_incomplete:
        st.subheader("⚠️ Проекты без полного состава")
        incomplete = []
        for _, proj in df_projects.iterrows():
            if proj.get('status_fill') in active_statuses:
                no_lead = not (proj.get('lead_id') and pd.notna(proj.get('lead_id')))
                no_juniors = df_juniors[df_juniors['project_id'] == proj['id']].empty
                if no_lead or no_juniors:
                    incomplete.append({'Проект': proj['name'], 'Нет ведущего': 'Да' if no_lead else '—', 'Нет рядовых': 'Да' if no_juniors else '—'})
        if incomplete:
            st.dataframe(pd.DataFrame(incomplete), width='stretch', hide_index=True)
        else:
            st.success("У всех активных проектов указаны ведущий и рядовые.")
    with col_phases:
        st.subheader("📌 Этапы по проектам")
        if not df_phases.empty:
            phase_counts = df_phases.groupby('project_id').size().reset_index(name='Этапов')
            phase_counts['Проект'] = phase_counts['project_id'].map(
                lambda pid: df_projects[df_projects['id'] == pid]['name'].values[0] if len(df_projects[df_projects['id'] == pid]) else f"ID {pid}"
            )
            fig_phases = px.bar(phase_counts, x='Проект', y='Этапов', title='Количество этапов по проектам',
                                color_discrete_sequence=COLOR_PALETTE)
            apply_chart_theme(fig_phases)
            fig_phases.update_xaxes(tickangle=-45)
            st.plotly_chart(fig_phases, width='stretch')
        else:
            st.info("Нет этапов проектов.")
