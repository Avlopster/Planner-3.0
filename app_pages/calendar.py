# -*- coding: utf-8 -*-
"""Страница календаря: отпуска и проекты по сотрудникам, проекты vs отпуска, конфликты, экспорт Excel."""
import io
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

import components
import load_calculator
import repository
from utils.chart_theme import COLOR_PALETTE, apply_chart_theme


def render(conn):
    st.header("🗓️ Календарь отпусков и проектов")
    df_emp = repository.load_employees(conn)
    if df_emp.empty:
        st.warning("Нет сотрудников.")
    else:
        # Вкладки для разных режимов отображения
        tab1, tab2 = st.tabs(["Отпуска + проекты (по сотрудникам)", "Проекты vs отпуска (два окна)"])

        # Общие фильтры периода
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Начало периода**")
            start_cal = components.ru_date_picker("", default=date.today(), key_prefix="cal_start")
            start_str = start_cal.isoformat()
        with col2:
            st.markdown("**Конец периода**")
            end_cal = components.ru_date_picker("", default=date.today() + timedelta(days=90), key_prefix="cal_end")
            end_str = end_cal.isoformat()

        # Загрузка данных
        df_vac = repository.load_vacations(conn)
        projects = repository.load_projects(conn)
        juniors = repository.load_project_juniors(conn)
        phases_df = repository.load_phases(conn)

        # Фильтры по проектам и типам событий
        projects_sorted = projects.sort_values('name') if not projects.empty else projects
        project_names = projects_sorted['name'].tolist() if not projects_sorted.empty else []

        with tab1:
            st.subheader("Отпуска и проекты по сотрудникам")

            # Фильтры
            col_filter1, col_filter2 = st.columns(2)
            with col_filter1:
                selected_projects = st.multiselect("Фильтр по проектам", project_names, key="cal_filter_projects")
            with col_filter2:
                show_vacations = st.checkbox("Показывать отпуска", value=True, key="cal_show_vacations")
                show_projects = st.checkbox("Показывать проекты", value=True, key="cal_show_projects")

            events = []

            # Отпуска
            if show_vacations:
                for _, vac in df_vac.iterrows():
                    emp_name = repository.get_employee_name(conn, vac['employee_id'])
                    events.append(dict(
                        Сотрудник=emp_name,
                        Начало=pd.to_datetime(vac['start_date']),
                        Окончание=pd.to_datetime(vac['end_date']),
                        Тип='Отпуск',
                        Проект=''
                    ))

            # Проекты
            if show_projects:
                for _, proj in projects.iterrows():
                    # Фильтр по проектам
                    if selected_projects and proj['name'] not in selected_projects:
                        continue

                    if proj['auto_dates']:
                        proj_phases = phases_df[phases_df['project_id'] == proj['id']]
                        if proj_phases.empty:
                            continue
                        proj_start = proj_phases['start_date'].min()
                        proj_end = proj_phases['end_date'].max()
                    else:
                        proj_start = proj['project_start']
                        proj_end = proj['project_end']
                        if not proj_start or not proj_end:
                            continue

                    lead_name = repository.get_employee_name(conn, proj['lead_id'])
                    events.append(dict(
                        Сотрудник=lead_name,
                        Начало=pd.to_datetime(proj_start),
                        Окончание=pd.to_datetime(proj_end),
                        Тип='Проект (вед.)',
                        Проект=proj['name']
                    ))
                    proj_jun = juniors[juniors['project_id'] == proj['id']]
                    for _, j in proj_jun.iterrows():
                        jun_name = repository.get_employee_name(conn, j['employee_id'])
                        events.append(dict(
                            Сотрудник=jun_name,
                            Начало=pd.to_datetime(proj_start),
                            Окончание=pd.to_datetime(proj_end),
                            Тип='Проект',
                            Проект=proj['name']
                        ))

            df_events = pd.DataFrame(events)
            if not df_events.empty:
                # Показываем все события, которые пересекаются с выбранным периодом,
                # а не только полностью лежащие внутри него.
                period_start = pd.to_datetime(start_str)
                period_end = pd.to_datetime(end_str)
                df_events = df_events[
                    (df_events['Окончание'] >= period_start) &
                    (df_events['Начало'] <= period_end)
                ]
                if not df_events.empty:
                    n_emp_cal = df_events["Сотрудник"].nunique()
                    cal_height = max(300, min(600, 28 * n_emp_cal))
                    fig = px.timeline(df_events, x_start="Начало", x_end="Окончание", y="Сотрудник",
                                      color="Тип", title="Отпуска и проекты сотрудников",
                                      labels={"Сотрудник": "Сотрудник", "Тип": "Тип события",
                                              "Начало": "Дата начала", "Окончание": "Дата окончания"},
                                      color_discrete_sequence=COLOR_PALETTE)
                    apply_chart_theme(fig)
                    fig.update_yaxes(autorange="reversed")
                    fig.update_layout(height=cal_height, bargap=0.15, margin=dict(t=40, b=40, l=80, r=40))
                    fig.update_xaxes(tickformat="%d.%m.%Y", showgrid=True, gridwidth=0.5, linewidth=0.5, tickfont=dict(size=10))
                    fig.update_yaxes(tickfont=dict(size=10), linewidth=0.5)
                    st.plotly_chart(fig, width='stretch')
                else:
                    st.info("Нет событий в выбранном периоде.")
            else:
                st.info("Нет данных об отпусках или проектах.")

        with tab2:
            st.subheader("Проекты vs отпуска (два окна)")

            # Фильтры для двухоконного режима
            col_filter1, col_filter2 = st.columns(2)
            with col_filter1:
                selected_projects_dual = st.multiselect("Выберите проекты", project_names, key="dual_filter_projects")
                filter_employees_by_projects = st.checkbox("Показывать только сотрудников выбранных проектов",
                                                          value=False, key="dual_filter_emp")
            with col_filter2:
                st.write("")  # Пустое место для выравнивания

            # Определяем список сотрудников для отображения
            if filter_employees_by_projects and selected_projects_dual:
                project_ids = projects_sorted[projects_sorted['name'].isin(selected_projects_dual)]['id'].tolist()
                project_employees = set()
                for proj_id in project_ids:
                    proj = projects[projects['id'] == proj_id].iloc[0]
                    if proj['lead_id']:
                        project_employees.add(proj['lead_id'])
                    proj_jun = juniors[juniors['project_id'] == proj_id]
                    for _, j in proj_jun.iterrows():
                        project_employees.add(j['employee_id'])
                employees_to_show = df_emp[df_emp['id'].isin(project_employees)]
            else:
                employees_to_show = df_emp

            date_range = [pd.to_datetime(start_str), pd.to_datetime(end_str)]

            col_timeline_left, col_timeline_right = st.columns(2)
            with col_timeline_left:
                st.markdown("#### 📊 Проекты и этапы")
                tasks = []
                for _, proj in projects.iterrows():
                    if selected_projects_dual and proj['name'] not in selected_projects_dual:
                        continue

                    if proj['auto_dates']:
                        proj_phases = phases_df[phases_df['project_id'] == proj['id']]
                        if proj_phases.empty:
                            continue
                        proj_start = proj_phases['start_date'].min()
                        proj_end = proj_phases['end_date'].max()
                    else:
                        proj_start = proj['project_start']
                        proj_end = proj['project_end']
                        if not proj_start or not proj_end:
                            continue

                    tasks.append(dict(
                        Задача=f"📁 {proj['name']}",
                        Начало=pd.to_datetime(proj_start),
                        Окончание=pd.to_datetime(proj_end),
                        Тип='Проект',
                        Описание=f"Ведущий: {repository.get_employee_name(conn, proj['lead_id'])}"
                    ))

                    proj_phases = phases_df[phases_df['project_id'] == proj['id']]
                    for _, ph in proj_phases.iterrows():
                        tasks.append(dict(
                            Задача=f"  • {proj['name']} — {ph['name']}",
                            Начало=pd.to_datetime(ph['start_date']),
                            Окончание=pd.to_datetime(ph['end_date']),
                            Тип=ph['phase_type'],
                            Описание=''
                        ))

                df_tasks = pd.DataFrame(tasks)
                if not df_tasks.empty:
                    # Оставляем проекты и этапы, которые пересекаются с периодом.
                    period_start = pd.to_datetime(start_str)
                    period_end = pd.to_datetime(end_str)
                    df_tasks = df_tasks[
                        (df_tasks['Окончание'] >= period_start) &
                        (df_tasks['Начало'] <= period_end)
                    ]
                    if not df_tasks.empty:
                        task_order = list(dict.fromkeys(df_tasks["Задача"].tolist()))
                        n_rows_dual = len(task_order)
                        dual_height1 = max(300, min(600, 32 * n_rows_dual))
                        fig1 = px.timeline(
                            df_tasks,
                            x_start="Начало",
                            x_end="Окончание",
                            y="Задача",
                            color="Тип",
                            hover_data=["Описание"],
                            title="Проекты и этапы",
                            labels={"Задача": "Задача", "Тип": "Тип", "Начало": "Дата начала", "Окончание": "Дата окончания"},
                            category_orders={"Задача": task_order},
                            color_discrete_sequence=COLOR_PALETTE,
                        )
                        apply_chart_theme(fig1)
                        fig1.update_yaxes(autorange=True)
                        fig1.update_layout(height=dual_height1, bargap=0.15, margin=dict(t=40, b=40, l=80, r=40))
                        fig1.update_xaxes(tickformat="%d.%m.%Y", showgrid=True, gridwidth=0.5, linewidth=0.5, tickfont=dict(size=10))
                        fig1.update_yaxes(tickfont=dict(size=10), linewidth=0.5)
                        fig1.update_xaxes(range=date_range)
                        st.plotly_chart(fig1, width='stretch')
                    else:
                        st.info("Нет проектов/этапов в выбранном периоде.")
                else:
                    st.info("Нет проектов для отображения.")

            with col_timeline_right:
                st.markdown("#### 🏖️ Отпуска сотрудников")
                vac_events = []
                for _, vac in df_vac.iterrows():
                    emp_id = vac['employee_id']
                    if not employees_to_show.empty and emp_id not in employees_to_show['id'].values:
                        continue
                    emp_name = repository.get_employee_name(conn, emp_id)
                    vac_events.append(dict(
                        Сотрудник=emp_name,
                        Начало=pd.to_datetime(vac['start_date']),
                        Окончание=pd.to_datetime(vac['end_date']),
                        Тип='Отпуск'
                    ))

                df_vac_events = pd.DataFrame(vac_events)
                if not df_vac_events.empty:
                    # Оставляем отпуска, которые пересекаются с периодом.
                    period_start = pd.to_datetime(start_str)
                    period_end = pd.to_datetime(end_str)
                    df_vac_events = df_vac_events[
                        (df_vac_events['Окончание'] >= period_start) &
                        (df_vac_events['Начало'] <= period_end)
                    ]
                    if not df_vac_events.empty:
                        n_emp_vac = df_vac_events["Сотрудник"].nunique()
                        dual_height2 = max(300, min(600, 28 * n_emp_vac))
                        fig2 = px.timeline(df_vac_events, x_start="Начало", x_end="Окончание", y="Сотрудник",
                                          color="Тип", title="Отпуска сотрудников",
                                          labels={"Сотрудник": "Сотрудник", "Тип": "Тип события",
                                                  "Начало": "Дата начала", "Окончание": "Дата окончания"},
                                          color_discrete_sequence=COLOR_PALETTE)
                        apply_chart_theme(fig2)
                        fig2.update_yaxes(autorange="reversed")
                        fig2.update_layout(height=dual_height2, bargap=0.15, margin=dict(t=40, b=40, l=80, r=40))
                        fig2.update_xaxes(tickformat="%d.%m.%Y", showgrid=True, gridwidth=0.5, linewidth=0.5, tickfont=dict(size=10))
                        fig2.update_yaxes(tickfont=dict(size=10), linewidth=0.5)
                        fig2.update_xaxes(range=date_range)
                        st.plotly_chart(fig2, width='stretch')
                    else:
                        st.info("Нет отпусков в выбранном периоде.")
                else:
                    st.info("Нет данных об отпусках.")

            # Подсветка конфликтов отпуск/проект
            st.markdown("#### ⚠️ Конфликты отпуск/проект")
            conflicts = []
            employees_for_conflicts = employees_to_show if not employees_to_show.empty else df_emp
            for _, emp in employees_for_conflicts.iterrows():
                emp_id = emp['id']
                emp_name = emp['name']

                # Получаем отпуска сотрудника
                emp_vacations = df_vac[df_vac['employee_id'] == emp_id]

                # Получаем загрузку по дням без учёта отпусков (для выявления конфликтов)
                load_df = load_calculator.employee_load_by_day(conn, emp_id, start_str, end_str, ignore_vacations=True)

                # Проверяем каждый день на конфликт
                for _, day_row in load_df.iterrows():
                    day_date = day_row['date']
                    if isinstance(day_date, pd.Timestamp):
                        day_date = day_date.date()
                    elif isinstance(day_date, str):
                        day_date = pd.to_datetime(day_date).date()

                    # Проверяем, есть ли отпуск в этот день
                    in_vacation = False
                    for _, vac in emp_vacations.iterrows():
                        vac_start = vac['start_date']
                        vac_end = vac['end_date']
                        if isinstance(vac_start, str):
                            vac_start = pd.to_datetime(vac_start).date()
                        elif isinstance(vac_start, pd.Timestamp):
                            vac_start = vac_start.date()
                        if isinstance(vac_end, str):
                            vac_end = pd.to_datetime(vac_end).date()
                        elif isinstance(vac_end, pd.Timestamp):
                            vac_end = vac_end.date()

                        if vac_start <= day_date <= vac_end:
                            in_vacation = True
                            break

                    # Если есть отпуск И загрузка > 0, то конфликт
                    if in_vacation and day_row['load'] > 0:
                        phases_on_date = load_calculator.get_employee_phases_on_date(conn, emp_id, day_date)
                        proj_names = []
                        phase_names = []
                        first_project_id = None
                        first_phase_id = None
                        replacement_text = ""
                        if phases_on_date:
                            for s in phases_on_date:
                                proj_names.append(s['project_name'])
                                phase_names.append(s['phase_name'])
                            first_project_id = phases_on_date[0]['project_id']
                            first_phase_id = phases_on_date[0]['phase_id']
                            candidates = load_calculator.get_replacement_candidates_for_phase(conn, first_phase_id, emp_id, day_date)
                            replacement_text = ", ".join(c['employee_name'] for c in candidates) if candidates else "—"
                        conflicts.append({
                            'Сотрудник': emp_name,
                            'Дата': day_date.strftime("%d.%m.%Y"),
                            'Загрузка': f"{day_row['load']*100:.0f}%",
                            'Тип': 'Отпуск + проект',
                            'Проект': "; ".join(proj_names) if proj_names else "—",
                            'Этап': "; ".join(phase_names) if phase_names else "—",
                            'Рекомендуемая замена': replacement_text,
                            'project_id': first_project_id,
                            'phase_id': first_phase_id,
                        })

            if conflicts:
                conflicts_df = pd.DataFrame(conflicts)
                conflicts_df = conflicts_df.drop_duplicates(subset=['Сотрудник', 'Дата', 'Проект', 'Этап'], keep='first')
                display_cols = ['Сотрудник', 'Дата', 'Загрузка', 'Проект', 'Этап', 'Рекомендуемая замена']
                st.dataframe(conflicts_df[display_cols], width='stretch')
                seen_phase = set()
                st.markdown("**Перейти к редактированию этапа:**")
                for r in conflicts:
                    pid, phid = r.get('project_id'), r.get('phase_id')
                    if pid is not None and phid is not None and (pid, phid) not in seen_phase:
                        seen_phase.add((pid, phid))
                        proj_name = repository.get_project_name(conn, pid)
                        phase_row = phases_df[phases_df['id'] == phid]
                        ph_name = phase_row.iloc[0]['name'] if not phase_row.empty else "Этап"
                        if st.button(f"📌 {proj_name} — {ph_name}", key=f"goto_phase_conflict_{pid}_{phid}"):
                            st.session_state.menu = "Проекты и этапы"
                            st.session_state.open_project_id = pid
                            st.session_state.open_phase_id = phid
                            st.rerun()
                conflicts_excel = io.BytesIO()
                conflicts_df[display_cols].to_excel(conflicts_excel, index=False, engine='openpyxl')
                conflicts_excel.seek(0)
                st.download_button("📥 Скачать конфликты (Excel)", data=conflicts_excel,
                                   file_name=f"conflicts_{start_str}_{end_str}.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                   key="conflicts_export")
            else:
                st.success("Конфликтов отпуск/проект не обнаружено!")
