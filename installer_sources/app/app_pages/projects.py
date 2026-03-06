# -*- coding: utf-8 -*-
"""Страница «Проекты и этапы»: проекты, этапы, назначения."""
from datetime import date, timedelta
import html
import logging
import os
import sqlite3

import pandas as pd
import streamlit as st

from components import ru_date_picker
import config as app_config
import database as db
import repository
from utils.app_logging import get_actions_logger, get_db_logger, log_user_facing_error, record_error
from utils.type_utils import safe_int

logger = get_db_logger()
actions_log = get_actions_logger()


def _render_projects_compact_css() -> None:
    """Локальные стили для страницы проектов: плотнее строки и формы этапов."""
    st.markdown(
        """
<style>
[data-testid="stExpanderDetails"] [data-testid="stExpander"] details summary {
    padding-top: 0.3rem;
    padding-bottom: 0.3rem;
}

[data-testid="stExpanderDetails"] [data-testid="stForm"] {
    border: 1px solid rgba(127, 127, 127, 0.22);
    border-radius: 0.5rem;
    padding: 0.55rem 0.7rem 0.7rem 0.7rem;
}

[data-testid="stExpanderDetails"] [data-testid="stForm"] [data-testid="stVerticalBlock"] > div {
    margin-bottom: 0.3rem;
}

[data-testid="stExpanderDetails"] [data-testid="stForm"] p {
    margin-bottom: 0.2rem;
}
</style>
""".strip(),
        unsafe_allow_html=True,
    )


def _get_lead_candidates_df(df_emp: pd.DataFrame, conn) -> pd.DataFrame:
    """Список сотрудников-кандидатов на ведущего: только роли из конфига «руководители» (capacity_role_senior_ids)."""
    cfg = repository.load_capacity_config(conn)
    senior_ids = cfg.get("capacity_role_senior_ids") or []
    if not senior_ids:
        return df_emp.sort_values("name") if not df_emp.empty else df_emp
    mask = df_emp["role_id"].isin(senior_ids)
    df_lead = df_emp.loc[mask]
    return df_lead.sort_values("name") if not df_lead.empty else df_emp.sort_values("name")


def _render_new_project_form(conn, df_emp_sorted: pd.DataFrame, df_lead_candidates: pd.DataFrame) -> None:
    """Форма создания нового проекта: поля и кнопка «Создать проект». В поле «Ведущий специалист» — только сотрудники с ролью руководителя (из конфига)."""
    lead_options = df_lead_candidates["id"].tolist()
    if not lead_options:
        lead_options = df_emp_sorted["id"].tolist()
    lead_df = df_lead_candidates if not df_lead_candidates.empty else df_emp_sorted
    col1, col2, col3 = st.columns([1.8, 1.6, 1.4])
    with col1:
        if 'new_project_name' not in st.session_state:
            st.session_state.new_project_name = ""
        if 'new_project_client' not in st.session_state:
            st.session_state.new_project_client = ""
        if 'new_project_lead_id' not in st.session_state:
            st.session_state.new_project_lead_id = lead_options[0] if lead_options else None
        if 'new_project_lead_load' not in st.session_state:
            st.session_state.new_project_lead_load = 50
        if st.session_state.new_project_lead_id not in lead_options and lead_options:
            st.session_state.new_project_lead_id = lead_options[0]

        proj_name = st.text_input("Название проекта", value=st.session_state.new_project_name, key="new_proj_name")
        client_company = st.text_input("Компания клиента", value=st.session_state.new_project_client, key="new_proj_client")

    with col2:
        lead_id = st.selectbox(
            "Ведущий специалист", lead_options,
            format_func=lambda x: f"{lead_df[lead_df['id']==x]['name'].values[0]} ({lead_df[lead_df['id']==x]['role_name'].values[0]})",
            index=lead_options.index(st.session_state.new_project_lead_id) if st.session_state.new_project_lead_id in lead_options else 0,
            key="new_proj_lead"
        )
        if not (repository.load_capacity_config(conn).get("capacity_role_senior_ids")):
            st.caption("Для фильтра по роли ведущего настройте роли руководителей в разделе «Конфигурация».")
        lead_load = st.number_input("Загрузка ведущего (%)", min_value=1, max_value=100,
                                   value=st.session_state.new_project_lead_load, key="new_proj_lead_load")
        df_statuses = repository.load_project_statuses(conn)
        default_status_id = repository.get_status_id_by_code(conn, 'in_progress')
        status_options = df_statuses['id'].tolist() if not df_statuses.empty else []
        status_format = lambda x: df_statuses[df_statuses['id'] == x]['name'].values[0] if not df_statuses.empty and len(df_statuses[df_statuses['id'] == x]) else str(x)
        default_idx = status_options.index(default_status_id) if default_status_id in status_options else (1 if len(status_options) > 1 else 0)
        proj_status_id = st.selectbox(
            "Статус",
            status_options,
            format_func=status_format,
            index=min(default_idx, len(status_options) - 1) if status_options else 0,
            key="new_proj_status",
        )

    with col3:
        if 'new_project_auto_dates' not in st.session_state:
            st.session_state.new_project_auto_dates = True
        auto_dates = st.checkbox("Автоопределение дат по этапам",
                                 value=st.session_state.new_project_auto_dates, key="new_proj_auto_dates")
        if not auto_dates:
            st.caption("Дата начала проекта")
            if 'new_project_start' not in st.session_state:
                st.session_state.new_project_start = date.today()
            proj_start = ru_date_picker("", default=st.session_state.new_project_start, key_prefix="proj_start")
            proj_start_str = proj_start.isoformat()
            st.caption("Дата окончания проекта")
            if 'new_project_end' not in st.session_state:
                st.session_state.new_project_end = date.today() + timedelta(days=60)
            proj_end = ru_date_picker("", default=st.session_state.new_project_end, key_prefix="proj_end")
            proj_end_str = proj_end.isoformat()
        else:
            proj_start_str, proj_end_str = repository.get_date_placeholders(conn)
            st.caption("Даты проекта будут вычислены автоматически после добавления этапов.")

    juniors_list = []
    with st.expander("Рядовые сотрудники", expanded=False):
        if 'new_project_num_juniors' not in st.session_state:
            st.session_state.new_project_num_juniors = 1
        num_juniors = st.number_input(
            "Количество рядовых",
            min_value=0,
            max_value=10,
            value=st.session_state.new_project_num_juniors,
            step=1,
            key="new_proj_num_juniors",
        )
        for i in range(int(num_juniors)):
            cols = st.columns([1.6, 1.0])
            with cols[0]:
                junior_key = f"new_proj_junior_{i}"
                if junior_key not in st.session_state:
                    st.session_state[junior_key] = df_emp_sorted['id'].tolist()[0] if not df_emp_sorted.empty else None
                junior_id = st.selectbox(
                    f"Рядовой {i+1}",
                    df_emp_sorted['id'].tolist(),
                    format_func=lambda x, i=i: f"{df_emp_sorted[df_emp_sorted['id']==x]['name'].values[0]} ({df_emp_sorted[df_emp_sorted['id']==x]['role_name'].values[0]})",
                    index=df_emp_sorted['id'].tolist().index(st.session_state[junior_key]) if st.session_state[junior_key] in df_emp_sorted['id'].tolist() else 0,
                    key=f"junior_{i}",
                )
            with cols[1]:
                junior_load_key = f"new_proj_junior_load_{i}"
                if junior_load_key not in st.session_state:
                    st.session_state[junior_load_key] = 100
                junior_load = st.number_input(
                    f"Загрузка {i+1} (%)",
                    min_value=1,
                    max_value=100,
                    value=st.session_state[junior_load_key],
                    key=f"junior_load_{i}",
                )
            juniors_list.append((junior_id, junior_load))

    if st.button("Создать проект", use_container_width=True):
        if not proj_name:
            warn_msg = "Введите название проекта"
            log_user_facing_error(logging.WARNING, warn_msg)
            st.warning(warn_msg)
        else:
            proj_id = repository.insert_project(
                conn, proj_name, client_company or "", lead_id, float(lead_load),
                proj_start_str, proj_end_str, bool(auto_dates), int(proj_status_id),
            )
            if juniors_list:
                repository.add_project_juniors(conn, proj_id, [(int(jid), float(jload)) for (jid, jload) in juniors_list])
            actions_log.info("Создан проект '%s' (id=%s)", proj_name, proj_id)
            st.success(f"Проект '{proj_name}' создан!")
            st.session_state.new_project_name = ""
            st.session_state.new_project_client = ""
            if not df_emp_sorted.empty:
                st.session_state.new_project_lead_id = df_emp_sorted['id'].tolist()[0]
            st.session_state.new_project_lead_load = 50
            st.session_state.new_project_auto_dates = True
            st.session_state.new_project_num_juniors = 1
            st.session_state.new_project_start = date.today()
            st.session_state.new_project_end = date.today() + timedelta(days=60)
            for i in range(10):
                for key_suffix in [f"junior_{i}", f"junior_load_{i}"]:
                    if f"new_proj_{key_suffix}" in st.session_state:
                        del st.session_state[f"new_proj_{key_suffix}"]
            for key in ['proj_start_day', 'proj_start_month', 'proj_start_year',
                       'proj_end_day', 'proj_end_month', 'proj_end_year']:
                if key in st.session_state:
                    del st.session_state[key]
            st.cache_data.clear()
            st.rerun()


def _render_project_header(conn, proj, juniors_df: pd.DataFrame) -> None:
    """Шапка карточки проекта: ведущий, рядовые, даты, кнопки редактирования и удаления."""
    col1, col2 = st.columns([5, 1])
    with col1:
        st.write(f"**Ведущий:** {proj['lead_name']} ({proj['lead_load_percent']}%)")
        proj_jun = juniors_df[juniors_df['project_id'] == proj['id']]
        if not proj_jun.empty:
            st.write("**Рядовые:**")
            for _, j in proj_jun.iterrows():
                st.write(f"  - {repository.get_employee_name(conn, j['employee_id'])} ({j['load_percent']}%)")
        if proj['auto_dates']:
            st.write("**Даты проекта:** авто (на основе этапов)")
        else:
            start_fmt = proj['project_start'].strftime("%d.%m.%Y") if hasattr(proj.get('project_start'), 'strftime') and proj.get('project_start') else "—"
            end_fmt = proj['project_end'].strftime("%d.%m.%Y") if hasattr(proj.get('project_end'), 'strftime') and proj.get('project_end') else "—"
            st.write(f"**Период:** {start_fmt} — {end_fmt}")
    with col2:
        if st.button("✏️", key=f"edit_proj_{proj['id']}"):
            st.session_state[f'editing_proj_{proj["id"]}'] = True
        if st.button("🗑️", key=f"del_proj_{proj['id']}"):
            repository.delete_project(conn, proj['id'])
            st.cache_data.clear()
            st.rerun()


def _render_phases_section(
    conn,
    proj,
    phases_df: pd.DataFrame,
    phase_assignments_df: pd.DataFrame,
    df_emp: pd.DataFrame,
    open_phase_id,
) -> None:
    """Блок «Этапы проекта»: список этапов с редактированием/удалением и форма добавления этапа (иерархия по parent_id, нумерация только верхнего уровня)."""
    st.markdown("#### 🗂️ Этапы проекта")
    proj_phases = phases_df[phases_df['project_id'] == proj['id']]
    if not proj_phases.empty:
        emp_id_to_name: dict[int, str] = {}
        try:
            if not df_emp.empty and "id" in df_emp.columns and "name" in df_emp.columns:
                emp_ids = df_emp["id"].astype(int).tolist()
                emp_names = df_emp["name"].fillna("").astype(str).tolist()
                emp_id_to_name = dict(zip(emp_ids, emp_names))
        except Exception:
            emp_id_to_name = {}

        proj_phase_ids: list[int] = []
        try:
            proj_phase_ids = [int(x) for x in proj_phases["id"].tolist() if pd.notna(x)]
        except Exception:
            proj_phase_ids = []

        assigns_by_phase: dict[int, pd.DataFrame] = {}
        if not phase_assignments_df.empty and proj_phase_ids:
            try:
                _proj_assigns = phase_assignments_df[phase_assignments_df["phase_id"].isin(proj_phase_ids)]
                if not _proj_assigns.empty:
                    assigns_by_phase = {int(pid): grp for pid, grp in _proj_assigns.groupby("phase_id")}
            except Exception:
                assigns_by_phase = {}

        phases_with_depth = repository.phases_tree_order(proj_phases)
        top_level_num = 0
        for ph, depth in phases_with_depth:
            with st.container():
                if open_phase_id is not None and ph['id'] == open_phase_id:
                    st.info("Вы здесь из-за перегрузки или конфликта отпуск/проект. Измените назначения на этап при необходимости.")
                col1, col2, col3, col4, col5, col_staff, col6, col7 = st.columns([3.4, 1.6, 1.4, 1.4, 1.0, 1.3, 0.7, 0.7])
                ph_start = ph['start_date']
                ph_end = ph['end_date']
                with col1:
                    indent_px = depth * 16
                    safe_name = html.escape(str(ph['name']), quote=True)
                    if depth == 0:
                        top_level_num += 1
                        display_label = f"<strong>{top_level_num}. {safe_name}</strong>"
                    else:
                        display_label = f"• {safe_name}"
                    st.markdown(
                        f'<p style="margin-left:{indent_px}px; margin-top:0; margin-bottom:0;">{display_label}</p>',
                        unsafe_allow_html=True,
                    )
                with col2:
                    st.caption(ph['phase_type'])
                with col3:
                    st.caption(ph_start.strftime("%d.%m.%Y") if hasattr(ph_start, 'strftime') else str(ph_start))
                with col4:
                    st.caption(ph_end.strftime("%d.%m.%Y") if hasattr(ph_end, 'strftime') else str(ph_end))
                with col5:
                    st.caption(f"{safe_int(ph.get('completion_percent'), 0) or 0}%")
                with col_staff:
                    assigns = assigns_by_phase.get(int(ph["id"]), pd.DataFrame()) if ph.get("id") is not None else pd.DataFrame()
                    if assigns.empty:
                        st.caption("Наслед.")
                    else:
                        n = int(len(assigns))
                        label = f"👥 {n}"
                        if hasattr(st, "popover"):
                            with st.popover(label):
                                for _, a in assigns.iterrows():
                                    emp_id = safe_int(a.get("employee_id"), None)
                                    emp_name = emp_id_to_name.get(int(emp_id)) if emp_id is not None else None
                                    if not emp_name and emp_id is not None:
                                        emp_name = repository.get_employee_name(conn, int(emp_id))
                                    load_pct = safe_int(a.get("load_percent"), 0) or 0
                                    st.write(f"{emp_name or '—'} ({load_pct}%)")
                        else:
                            with st.expander(label, expanded=False):
                                for _, a in assigns.iterrows():
                                    emp_id = safe_int(a.get("employee_id"), None)
                                    emp_name = emp_id_to_name.get(int(emp_id)) if emp_id is not None else None
                                    if not emp_name and emp_id is not None:
                                        emp_name = repository.get_employee_name(conn, int(emp_id))
                                    load_pct = safe_int(a.get("load_percent"), 0) or 0
                                    st.write(f"{emp_name or '—'} ({load_pct}%)")
                with col6:
                    if st.button("✏️", key=f"edit_phase_{ph['id']}"):
                        st.session_state[f"editing_phase_{ph['id']}"] = True
                with col7:
                    if st.button("❌", key=f"del_phase_{ph['id']}"):
                        repository.delete_phase(conn, ph['id'])
                        if proj['auto_dates']:
                            repository.update_project_dates_from_phases(conn, proj['id'])
                        st.cache_data.clear()
                        st.rerun()

                if st.session_state.get(f'editing_phase_{ph["id"]}', False):
                    completion_options = list(range(0, 101, 5))
                    current_completion = safe_int(ph.get('completion_percent'), 0) or 0
                    current_completion = min(100, max(0, current_completion))
                    if current_completion not in completion_options:
                        current_completion = (current_completion // 5) * 5
                    edit_col1, edit_col2, edit_col3 = st.columns([1.8, 1.8, 1.1])
                    with edit_col1:
                        new_ph_name = st.text_input("Название этапа", value=ph['name'], key=f"edit_ph_name_{ph['id']}")
                        new_ph_type = st.selectbox(
                            "Тип", ["Обычная работа", "Командировка"],
                            index=0 if ph['phase_type'] == 'Обычная работа' else 1,
                            key=f"edit_ph_type_{ph['id']}"
                        )
                    with edit_col2:
                        st.caption("Дата начала")
                        new_ph_start = ru_date_picker("", default=ph['start_date'], key_prefix=f"edit_ph_start_{ph['id']}")
                        new_ph_start_str = new_ph_start.isoformat()
                        st.caption("Дата окончания")
                        new_ph_end = ru_date_picker("", default=ph['end_date'], key_prefix=f"edit_ph_end_{ph['id']}")
                        new_ph_end_str = new_ph_end.isoformat()
                    with edit_col3:
                        new_ph_completion = st.selectbox(
                            "Готовность, %",
                            options=completion_options,
                            index=completion_options.index(current_completion),
                            key=f"edit_ph_completion_{ph['id']}"
                        )

                    st.caption("Назначения на этап. Оставьте пустым для наследования.")
                    has_existing_assigns = not assigns.empty
                    default_emp_ids = assigns['employee_id'].tolist() if has_existing_assigns else []
                    default_loads = dict(zip(assigns['employee_id'], assigns['load_percent'])) if has_existing_assigns else {}
                    use_custom_assign = st.checkbox(
                        "Использовать индивидуальные назначения", value=has_existing_assigns,
                        key=f"cust_assign_{ph['id']}"
                    )
                    assign_list = None
                    if use_custom_assign:
                        df_emp_sorted_phase = df_emp.sort_values('name')
                        selected_employees = st.multiselect(
                            "Выберите сотрудников для этапа",
                            options=df_emp_sorted_phase['id'].tolist(),
                            default=default_emp_ids,
                            format_func=lambda x: f"{df_emp_sorted_phase[df_emp_sorted_phase['id']==x]['name'].values[0]} ({df_emp_sorted_phase[df_emp_sorted_phase['id']==x]['role_name'].values[0]})",
                            key=f"multiselect_{ph['id']}"
                        )
                        assign_list = []
                        for emp_id in selected_employees:
                            emp_name = df_emp[df_emp['id'] == emp_id]['name'].values[0]
                            default_load = safe_int(default_loads.get(emp_id, 100), 100) or 100
                            load_pct = st.number_input(
                                f"Загрузка для {emp_name} (%)", min_value=1, max_value=100,
                                value=default_load, key=f"load_{ph['id']}_{emp_id}"
                            )
                            assign_list.append((emp_id, load_pct))
                    action_col1, action_col2, _ = st.columns([1, 1, 2])
                    with action_col1:
                        if st.button("💾 Сохранить", key=f"save_phase_{ph['id']}"):
                            try:
                                repository.update_phase(
                                    conn, ph['id'],
                                    new_ph_name, new_ph_type, new_ph_start_str, new_ph_end_str, new_ph_completion,
                                    assign_list if assign_list else None,
                                )
                                if proj['auto_dates']:
                                    repository.update_project_dates_from_phases(conn, proj['id'])
                                actions_log.info("Обновлён этап id=%s проекта id=%s", ph['id'], proj['id'])
                                st.success("Этап обновлён!")
                                st.session_state[f'editing_phase_{ph["id"]}'] = False
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as e:
                                msg_save = f"Ошибка при сохранении: {e}"
                                record_error(e, user_message=msg_save)
                                st.error(msg_save)
                    with action_col2:
                        if st.button("Отмена", key=f"cancel_phase_{ph['id']}"):
                            st.session_state[f'editing_phase_{ph["id"]}'] = False
                            st.rerun()
    else:
        st.info("Нет этапов")

    with st.form(key=f"add_phase_{proj['id']}"):
        st.markdown("**➕ Добавить этап**")
        col1, col2, col3 = st.columns([1.8, 1.8, 1.0])
        with col1:
            phase_name_key = f"new_phase_name_{proj['id']}"
            phase_type_key = f"new_phase_type_{proj['id']}"
            if phase_name_key not in st.session_state:
                st.session_state[phase_name_key] = ""
            if phase_type_key not in st.session_state:
                st.session_state[phase_type_key] = "Обычная работа"
            phase_name = st.text_input("Название этапа", value=st.session_state[phase_name_key], key=f"phase_name_{proj['id']}")
            phase_type = st.selectbox("Тип этапа", ["Обычная работа", "Командировка"],
                                     index=0 if st.session_state[phase_type_key] == "Обычная работа" else 1,
                                     key=f"phase_type_{proj['id']}")
        with col2:
            st.caption("Дата начала")
            phase_start_key = f"new_phase_start_{proj['id']}"
            if phase_start_key not in st.session_state:
                st.session_state[phase_start_key] = date.today()
            phase_start = ru_date_picker("", default=st.session_state[phase_start_key], key_prefix=f"phase_start_{proj['id']}")
            phase_start_str = phase_start.isoformat()
            st.caption("Дата окончания")
            phase_end_key = f"new_phase_end_{proj['id']}"
            if phase_end_key not in st.session_state:
                st.session_state[phase_end_key] = date.today() + timedelta(days=30)
            phase_end = ru_date_picker("", default=st.session_state[phase_end_key], key_prefix=f"phase_end_{proj['id']}")
            phase_end_str = phase_end.isoformat()
        with col3:
            phase_completion = st.selectbox(
                "Готовность, %", options=list(range(0, 101, 5)), index=0,
                key=f"new_phase_completion_{proj['id']}"
            )
            submitted = st.form_submit_button("Добавить этап", use_container_width=True)
        if submitted:
            if phase_name:
                repository.insert_phase(
                    conn, proj['id'], phase_name, phase_type,
                    phase_start_str, phase_end_str, phase_completion,
                )
                if proj['auto_dates']:
                    repository.update_project_dates_from_phases(conn, proj['id'])
                actions_log.info("Добавлен этап '%s' в проект id=%s", phase_name, proj['id'])
                st.success("Этап добавлен!")
                st.session_state[phase_name_key] = ""
                st.session_state[phase_type_key] = "Обычная работа"
                st.session_state[phase_start_key] = date.today()
                st.session_state[phase_end_key] = date.today() + timedelta(days=30)
                for key_suffix in ['day', 'month', 'year']:
                    for prefix in [f"phase_start_{proj['id']}", f"phase_end_{proj['id']}"]:
                        key = f"{prefix}_{key_suffix}"
                        if key in st.session_state:
                            del st.session_state[key]
                st.cache_data.clear()
                st.rerun()
            else:
                warn_phase = "Введите название этапа"
                log_user_facing_error(logging.WARNING, warn_phase)
                st.warning(warn_phase)


def render(conn, db_path=None):
    """Отрисовка страницы «Проекты и этапы». db_path — фактический путь к БД (для сохранения статуса на диск)."""
    effective_db_path = os.path.abspath(db_path) if db_path else os.path.abspath(app_config.DB_PATH)
    st.header("📌 Проекты и этапы")
    _render_projects_compact_css()
    df_emp = repository.load_employees(conn)
    if df_emp.empty:
        msg = "Сначала добавьте сотрудников."
        log_user_facing_error(logging.WARNING, msg)
        st.warning(msg)
        return
    df_emp_sorted = df_emp.sort_values('name')
    df_lead_candidates = _get_lead_candidates_df(df_emp, conn)

    with st.expander("➕ Новый проект", expanded=False):
        _render_new_project_form(conn, df_emp_sorted, df_lead_candidates)

    # Список проектов — всегда из БД, чтобы после обновления страницы или перезапуска приложения данные не сбрасывались
    st.subheader("Текущие проекты")
    if st.button("🔄 Обновить данные", key="proj_refresh"):
        st.cache_data.clear()
        st.rerun()
    if st.session_state.pop("_show_status_saved_message", False):
        st.success("Статус сохранён.")
    df_proj = repository.load_projects(conn)
    if not df_proj.empty:
        search_proj = st.text_input("🔍 Поиск по названию или компании", key="proj_search", placeholder="Введите текст...")
        if search_proj:
            mask = (df_proj['name'].str.contains(search_proj, case=False, na=False)) | \
                   (df_proj['client_company'].fillna('').str.contains(search_proj, case=False, na=False))
            if 'status_name' in df_proj.columns:
                mask = mask | (df_proj['status_name'].fillna('').astype(str).str.contains(search_proj, case=False, na=False))
            df_proj = df_proj[mask]
    if not df_proj.empty:
        df_proj = df_proj.copy()
        sort_by = st.selectbox(
            "Сортировка",
            ["По умолчанию", "По статусу (В работе → … → Отменён)"],
            key="proj_sort_by",
        )
        if sort_by == "По статусу (В работе → … → Отменён)":
            df_proj = repository.sort_projects_by_status(df_proj)
        df_proj['lead_name'] = df_proj['lead_id'].apply(lambda eid: repository.get_employee_name(conn, eid))
        juniors_df = repository.load_project_juniors(conn)
        phases_df = repository.load_phases(conn)
        phase_assignments_df = repository.load_phase_assignments(conn)
        open_project_id = st.session_state.get('open_project_id')
        open_phase_id = st.session_state.get('open_phase_id')

        for idx, proj in df_proj.iterrows():
            proj_status = proj.get('status_name', 'Не указан') or 'Не указан'
            expand_this = (open_project_id is not None and proj['id'] == open_project_id)
            with st.expander(f"📁 {proj['name']} — {proj['client_company'] if proj['client_company'] else 'Без компании'} [{proj_status}]", expanded=expand_this):
                safe_proj_name = html.escape(str(proj.get("name") or ""), quote=True)
                safe_client = html.escape(str(proj.get("client_company") or "Без компании"), quote=True)
                safe_status = html.escape(str(proj_status), quote=True)
                st.markdown(
                    f"""
<div style="margin: 0 0 0.35rem 0;">
  <div style="font-size: 1.6rem; font-weight: 700; line-height: 1.1;">{safe_proj_name}</div>
  <div style="font-size: 0.95rem; opacity: 0.85;">{safe_client} • {safe_status}</div>
</div>
""".strip(),
                    unsafe_allow_html=True,
                )
                _render_project_header(conn, proj, juniors_df)

                # Редактирование проекта: статус вынесен из формы (отдельный виджет), чтобы значение не терялось при отправке формы
                if st.session_state.get(f'editing_proj_{proj["id"]}', False):
                    pid = int(proj['id'])
                    init_key = f"_edit_proj_init_{pid}"
                    # Сохраняем выбранный статус сразу, до отрисовки виджетов — иначе в run с submitted виджеты могут перезаписать session_state
                    _captured_status_id = None
                    _raw_captured = st.session_state.get(f"_edit_status_save_{pid}")
                    if _raw_captured is not None:
                        try:
                            _captured_status_id = int(_raw_captured)
                        except (TypeError, ValueError):
                            pass
                    df_statuses_edit = repository.load_project_statuses(conn)
                    status_id_options = [int(safe_int(x, 0)) for x in df_statuses_edit['id'].tolist() if safe_int(x, None) is not None] if not df_statuses_edit.empty else []
                    proj_status_id = safe_int(proj.get('status_id'), None) or repository.get_status_id_by_code(conn, 'in_progress')
                    proj_status_id = int(proj_status_id) if proj_status_id is not None else (status_id_options[0] if status_id_options else None)
                    status_index = status_id_options.index(proj_status_id) if (status_id_options and proj_status_id in status_id_options) else 0
                    status_id_to_name = dict(zip(df_statuses_edit['id'].astype(int), df_statuses_edit['name'].astype(str))) if not df_statuses_edit.empty else {}
                    if not status_id_options:
                        selected_status_id = None
                        st.caption("Справочник статусов пуст. Добавьте статусы в Конфигурации.")
                    else:
                        # Статус: selectbox и кнопка вне формы. При нажатии кнопки используем _captured_status_id (захвачен в начале run до отрисовки виджетов)
                        selected_status_id = st.selectbox(
                            "Статус",
                            status_id_options,
                            index=status_index,
                            format_func=lambda x: status_id_to_name.get(int(x), str(x)),
                            key=f"edit_status_{pid}",
                        )
                        save_status_clicked = st.button("✓ Сохранить статус", key=f"save_status_btn_{pid}")
                        if save_status_clicked:
                            # При нажатии кнопки берём значение из текущего виджета (selected_status_id), иначе из session_state
                            sid = None
                            if selected_status_id is not None and selected_status_id in status_id_options:
                                sid = int(selected_status_id)
                            if sid is None and _captured_status_id is not None and (not status_id_options or _captured_status_id in status_id_options):
                                sid = int(_captured_status_id)
                            if sid is not None and sid != proj_status_id:
                                try:
                                    # Закрываем сессионное подключение, чтобы запись попала в тот же файл и не конфликтовала с открытым conn.
                                    # После st.rerun() в Planner.py создаётся новое подключение (_db_conn not in session_state).
                                    _session_conn = st.session_state.get("_db_conn")
                                    if _session_conn is not None:
                                        try:
                                            _session_conn.close()
                                        except sqlite3.OperationalError:
                                            pass
                                    st.session_state.pop("_db_conn", None)
                                    # Пишем в файл по пути из config и проверяем запись повторным открытием файла
                                    ok, _ = db.update_project_status_on_disk(effective_db_path, pid, sid)
                                    if not ok:
                                        msg = "Статус не сохранился в БД."
                                        log_user_facing_error(logging.ERROR, msg, context=f"project_id={pid} status_id={sid}")
                                        logger.warning("Проверка после записи статуса не прошла: project_id=%s status_id=%s", pid, sid)
                                        st.error(msg)
                                        st.cache_data.clear()
                                        st.rerun()
                                        return
                                    actions_log.info("Сохранён статус проекта id=%s -> status_id=%s", pid, sid)
                                    st.session_state["_show_status_saved_message"] = True
                                    st.session_state.pop(f"_edit_status_save_{pid}", None)
                                    if f"edit_status_{pid}" in st.session_state:
                                        del st.session_state[f"edit_status_{pid}"]
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    msg = f"Ошибка сохранения: {e}"
                                    record_error(e, user_message=msg)
                                    st.error(msg)
                            elif sid is not None and sid == proj_status_id:
                                st.info("Проект уже в выбранном статусе.")
                            else:
                                warn_msg = "Сначала выберите другой статус в списке и нажмите «Сохранить статус»."
                                log_user_facing_error(logging.WARNING, warn_msg)
                                st.warning(warn_msg)
                        else:
                            # Пока кнопка не нажата — запоминаем текущий выбор для следующего run
                            if selected_status_id is not None and selected_status_id in status_id_options:
                                st.session_state[f"_edit_status_save_{pid}"] = int(selected_status_id)
                        st.caption("Выберите статус, затем нажмите «Сохранить статус». После смены списка нажмите кнопку один раз.")
                    default_start = proj.get('project_start') or date.today()
                    if not hasattr(default_start, 'strftime'):
                        default_start = date.today()
                    default_end = proj.get('project_end') or (date.today() + timedelta(days=60))
                    if not hasattr(default_end, 'strftime'):
                        default_end = date.today() + timedelta(days=60)
                    df_emp_sorted_edit = df_emp.sort_values('name')
                    lead_options = df_lead_candidates['id'].tolist() if not df_lead_candidates.empty else df_emp_sorted_edit['id'].tolist()
                    proj_lead_id = safe_int(proj.get('lead_id'), None)
                    if proj_lead_id is not None and proj_lead_id not in lead_options:
                        lead_options = [proj_lead_id] + lead_options
                    if proj_lead_id is None and lead_options:
                        proj_lead_id = lead_options[0]
                    lead_index = lead_options.index(proj_lead_id) if (lead_options and proj_lead_id in lead_options) else 0
                    lead_format_df = df_emp_sorted_edit

                    with st.form(key=f"edit_form_{pid}"):
                        new_name = st.text_input("Название", value=proj['name'] or "", key=f"edit_name_{pid}")
                        new_client = st.text_input("Компания клиента", value=(proj['client_company'] or "") if proj.get('client_company') is not None else "", key=f"edit_client_{pid}")
                        new_lead = st.selectbox(
                            "Ведущий",
                            lead_options,
                            index=lead_index,
                            format_func=lambda x: lead_format_df[lead_format_df['id'] == x]['name'].values[0] if len(lead_format_df[lead_format_df['id'] == x]) else str(x),
                            key=f"edit_lead_{pid}",
                        )
                        new_lead_load = st.number_input("Загрузка ведущего %", min_value=1, max_value=100, value=safe_int(proj.get('lead_load_percent'), 100) or 100, key=f"edit_lead_load_{pid}")
                        new_auto = st.checkbox("Автоопределение дат", value=bool(proj.get('auto_dates')), key=f"edit_auto_{pid}")
                        if not new_auto:
                            st.markdown("**Дата начала**")
                            new_start = ru_date_picker("", default=default_start, key_prefix=f"edit_start_{pid}")
                            new_start_str = new_start.isoformat()
                            st.markdown("**Дата окончания**")
                            new_end = ru_date_picker("", default=default_end, key_prefix=f"edit_end_{pid}")
                            new_end_str = new_end.isoformat()
                        else:
                            new_start_str, new_end_str = repository.get_date_placeholders(conn)

                        col1, col2 = st.columns(2)
                        with col1:
                            submitted = st.form_submit_button("💾 Сохранить")
                        with col2:
                            cancel_clicked = st.form_submit_button("Отмена")

                    if cancel_clicked:
                        if init_key in st.session_state:
                            del st.session_state[init_key]
                        if f"edit_status_{pid}" in st.session_state:
                            del st.session_state[f"edit_status_{pid}"]
                        if f"_edit_status_save_{pid}" in st.session_state:
                            del st.session_state[f"_edit_status_save_{pid}"]
                        st.session_state[f'editing_proj_{pid}'] = False
                        st.rerun()
                    elif submitted:
                        # Статус: при отправке формы берём текущее значение виджета (selected_status_id), иначе из session_state
                        _status_id = None
                        if selected_status_id is not None and (not status_id_options or selected_status_id in status_id_options):
                            try:
                                _status_id = int(selected_status_id)
                            except (TypeError, ValueError):
                                pass
                        if _status_id is None and _captured_status_id is not None and (not status_id_options or _captured_status_id in status_id_options):
                            _status_id = int(_captured_status_id)
                        if _status_id is None or (status_id_options and _status_id not in status_id_options):
                            _status_id = repository.get_status_id_by_code(conn, 'in_progress')
                            _status_id = int(_status_id) if _status_id is not None else None
                        if _status_id is None:
                            msg = "Невозможно сохранить: в справочнике нет статусов. Добавьте статусы в Конфигурации."
                            log_user_facing_error(logging.ERROR, msg)
                            st.error(msg)
                        else:
                            _status_id = int(_status_id)
                            repository.update_project(
                                conn, pid, new_name, new_client or "", new_lead, float(new_lead_load),
                                new_start_str, new_end_str, bool(new_auto), _status_id,
                            )
                            current_status_id = repository.get_project_status_id(conn, pid)
                            if current_status_id is not None and current_status_id != _status_id:
                                msg2 = "Статус не сохранился в БД. Проверьте таблицу projects и колонку status_id."
                                log_user_facing_error(logging.ERROR, msg2)
                                st.error(msg2)
                            else:
                                if new_auto:
                                    repository.update_project_dates_from_phases(conn, pid)
                                if init_key in st.session_state:
                                    del st.session_state[init_key]
                                if f"edit_status_{pid}" in st.session_state:
                                    del st.session_state[f"edit_status_{pid}"]
                                if f"_edit_status_save_{pid}" in st.session_state:
                                    del st.session_state[f"_edit_status_save_{pid}"]
                                st.session_state[f'editing_proj_{pid}'] = False
                                st.cache_data.clear()
                                st.success("Проект обновлён!")
                                st.rerun()
                    else:
                        # Форма не отправлена — запоминаем текущий выбор (дополнение к on_change на случай первого отображения)
                        if status_id_options and selected_status_id is not None:
                            try:
                                _sid = int(selected_status_id)
                                if _sid in status_id_options:
                                    st.session_state[f"_edit_status_save_{pid}"] = _sid
                            except (TypeError, ValueError):
                                pass

                _render_phases_section(conn, proj, phases_df, phase_assignments_df, df_emp, open_phase_id)
    else:
        st.info("Нет проектов")
