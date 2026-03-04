# -*- coding: utf-8 -*-
"""Страница «Диаграмма Ганта»: проекты и этапы на временной шкале."""
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

import config as app_config
import repository
from utils.chart_theme import apply_chart_theme
from utils.type_utils import safe_int


def render(conn):
    """Отрисовка страницы «Диаграмма Ганта»: проекты и этапы на временной шкале. conn — подключение к БД."""
    st.header("📊 Диаграмма Ганта проектов и этапов")
    df_proj = repository.load_projects(conn)
    if df_proj.empty:
        st.info("Нет проектов для отображения.")
    else:
        only_active = st.checkbox(
            "Только активные проекты (В работе)",
            value=False,
            key="gantt_only_active",
        )
        if only_active:
            gantt_statuses = repository.get_gantt_active_statuses(conn)
            df_proj = df_proj[df_proj['status_name'].fillna('Не указан').isin(gantt_statuses)].copy()
        if not df_proj.empty:
            df_proj = repository.sort_projects_by_status(df_proj)
            option_pairs = [
                (f"{row['name']} — {row.get('status_name', 'Не указан')}", row['id'])
                for _, row in df_proj.iterrows()
            ]
            gantt_options = [p[0] for p in option_pairs]
            # Ключ зависит от фильтра, чтобы при переключении чекбокса список выбора обновлялся
            selected_labels = st.multiselect(
                "Проекты на диаграмме (выделенные отображаются)",
                options=gantt_options,
                default=gantt_options,
                key=f"gantt_selected_projects_{only_active}",
            )
            selected_ids = [p[1] for p in option_pairs if p[0] in selected_labels]
            df_proj = df_proj[df_proj['id'].isin(selected_ids)].copy()
            df_proj = repository.sort_projects_by_status(df_proj)
        if df_proj.empty:
            st.info("Нет проектов для отображения.")
        else:
            # --- Управление сворачиванием этапов по проектам ---
            # Глобальный флаг по умолчанию для новых проектов
            default_show_phases = st.checkbox(
                "Показывать этапы проектов (по умолчанию)",
                value=st.session_state.get("gantt_default_show_phases", True),
                key="gantt_default_show_phases",
            )

            # Инициализация словаря состояний развёрнутости по проектам
            if "gantt_project_expand" not in st.session_state:
                st.session_state.gantt_project_expand = {}

            # Обновляем дефолт для ранее не встречавшихся проектов
            for proj_id in df_proj["id"]:
                pid = safe_int(proj_id, 0) or 0
                if pid not in st.session_state.gantt_project_expand:
                    st.session_state.gantt_project_expand[pid] = default_show_phases

            # Кнопки для массового разворачивания/сворачивания
            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("Развернуть этапы всех проектов"):
                    for proj_id in df_proj["id"]:
                        st.session_state.gantt_project_expand[safe_int(proj_id, 0) or 0] = True
                    st.rerun()
            with col2:
                if st.button("Свернуть этапы всех проектов"):
                    for proj_id in df_proj["id"]:
                        st.session_state.gantt_project_expand[safe_int(proj_id, 0) or 0] = False
                    st.rerun()

            st.markdown("**Отображение этапов по проектам:**")
            proj_list = list(df_proj.iterrows())
            n_cols = 4
            phase_cols = st.columns(n_cols)
            for i, (_, proj) in enumerate(proj_list):
                with phase_cols[i % n_cols]:
                    pid = safe_int(proj["id"], 0) or 0
                    key = f"gantt_show_phases_{pid}"
                    current_value = st.session_state.gantt_project_expand.get(pid, default_show_phases)
                    st.session_state.gantt_project_expand[pid] = st.checkbox(
                        f"{proj['name']}", value=current_value, key=key
                    )

            tasks = []
            phases_df = repository.load_phases(conn)
            for _, proj in df_proj.iterrows():
                pid = safe_int(proj["id"], 0) or 0
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
                proj_start_dt = pd.to_datetime(proj_start)
                proj_end_dt = pd.to_datetime(proj_end)
                proj_status = (proj.get('status_name') or 'Не указан').strip() or 'Не указан'
                tasks.append(dict(
                    Задача=f"📁 {proj['name']}",
                    Начало=proj_start_dt,
                    Окончание=proj_end_dt,
                    Тип=f"Проект ({proj_status})",
                    Описание=f"Ведущий: {repository.get_employee_name(conn, proj['lead_id'])}"
                ))
                display_date = date.today()
                percent = repository.gantt_project_completion_percent(proj['id'], display_date, phases_df)
                if percent > 0:
                    delta = (proj_end_dt - proj_start_dt) * percent
                    completed_end_dt = proj_start_dt + delta
                    pct_str = f"{round(percent * 100)}%"
                    tasks.append(dict(
                        Задача=f"📁 {proj['name']}",
                        Начало=proj_start_dt,
                        Окончание=completed_end_dt,
                        Тип='Выполнено',
                        Описание=f"Готовность на {display_date.isoformat()}: {pct_str}"
                    ))
                proj_phases = phases_df[phases_df['project_id'] == proj['id']]
                if st.session_state.gantt_project_expand.get(pid, default_show_phases):
                    for _, ph in proj_phases.iterrows():
                        ph_start_dt = pd.to_datetime(ph['start_date'])
                        ph_end_dt = pd.to_datetime(ph['end_date'])
                        phase_label = f"  • {proj['name']} — {ph['name']}"
                        tasks.append(dict(
                            Задача=phase_label,
                            Начало=ph_start_dt,
                            Окончание=ph_end_dt,
                            Тип=ph['phase_type'],
                            Описание=''
                        ))
                        ph_pct = safe_int(ph.get('completion_percent'), 0) or 0
                        if ph_pct > 0:
                            ph_pct_frac = min(1.0, max(0.0, ph_pct / 100.0))
                            ph_delta = (ph_end_dt - ph_start_dt) * ph_pct_frac
                            ph_completed_end = ph_start_dt + ph_delta
                            tasks.append(dict(
                                Задача=phase_label,
                                Начало=ph_start_dt,
                                Окончание=ph_completed_end,
                                Тип='Выполнено',
                                Описание=f"Готовность этапа: {ph_pct}%"
                            ))
            df_tasks = pd.DataFrame(tasks)
            if not df_tasks.empty:
                task_order = list(dict.fromkeys(df_tasks["Задача"].tolist()))
                n_rows = len(task_order)
                gantt_height_default = max(500, 32 * n_rows)
                gantt_height = st.slider(
                    "Высота диаграммы (px)",
                    min_value=400,
                    max_value=1200,
                    value=min(1200, gantt_height_default),
                    key="gantt_height_slider",
                )
                # Цвета по категории проекта (при отображении всех проектов)
                color_map = {
                    "Проект (В работе)": "#4caf50",
                    "Проект (Планируется)": "#ff9800",
                    "Проект (Завершён)": "#9e9e9e",
                    "Проект (Отменён)": "#bdbdbd",
                    "Проект": "lightgray",  # fallback при неизвестном статусе
                    "Выполнено": "#2e7d32",
                    "Обычная работа": px.colors.qualitative.Set2[0],
                    "Командировка": px.colors.qualitative.Set2[1],
                }
                fig = px.timeline(
                    df_tasks,
                    x_start="Начало",
                    x_end="Окончание",
                    y="Задача",
                    color="Тип",
                    color_discrete_map=color_map,
                    hover_data=["Описание"],
                    title="Диаграмма Ганта: проекты и этапы",
                    labels={"Задача": "Задача", "Тип": "Тип", "Начало": "Дата начала", "Окончание": "Дата окончания"},
                    category_orders={"Задача": task_order},
                )
                apply_chart_theme(fig)
                fig.update_yaxes(autorange=True)
                fig.update_layout(height=gantt_height, bargap=0.15, margin=dict(t=40, b=40, l=80, r=40))
                fig.update_xaxes(tickformat="%d.%m.%Y", showgrid=True, gridwidth=0.5, linewidth=0.5, tickfont=dict(size=10))
                fig.update_yaxes(tickfont=dict(size=10), linewidth=0.5)
                # Уникальный key при каждом рендере страницы, чтобы не оставалось ссылок на старый
                # медиафайл в Streamlit memory storage (избегаем MediaFileStorageError при переходе в Гант).
                if "gantt_plotly_key" not in st.session_state:
                    st.session_state.gantt_plotly_key = 0
                st.session_state.gantt_plotly_key += 1
                st.plotly_chart(fig, width='stretch', key=f"gantt_plotly_{st.session_state.gantt_plotly_key}")
            else:
                st.info("Нет данных для Ганта.")
