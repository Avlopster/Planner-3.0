# -*- coding: utf-8 -*-
"""Страница «Проекты и этапы»: проекты, этапы, назначения."""
from datetime import date, timedelta
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


def _render_new_project_form(conn, df_emp_sorted: pd.DataFrame) -> None:
    """Форма создания нового проекта: поля и кнопка «Создать проект»."""
    col1, col2 = st.columns(2)
    with col1:
        if 'new_project_name' not in st.session_state:
            st.session_state.new_project_name = ""
        if 'new_project_client' not in st.session_state:
            st.session_state.new_project_client = ""
        if 'new_project_lead_id' not in st.session_state:
            st.session_state.new_project_lead_id = df_emp_sorted['id'].tolist()[0] if not df_emp_sorted.empty else None
        if 'new_project_lead_load' not in st.session_state:
            st.session_state.new_project_lead_load = 50

        proj_name = st.text_input("Название проекта", value=st.session_state.new_project_name, key="new_proj_name")
        client_company = st.text_input("Компания клиента", value=st.session_state.new_project_client, key="new_proj_client")
        lead_id = st.selectbox(
            "Ведущий специалист", df_emp_sorted['id'].tolist(),
            format_func=lambda x: f"{df_emp_sorted[df_emp_sorted['id']==x]['name'].values[0]} ({df_emp_sorted[df_emp_sorted['id']==x]['role_name'].values[0]})",
            index=df_emp_sorted['id'].tolist().index(st.session_state.new_project_lead_id) if st.session_state.new_project_lead_id in df_emp_sorted['id'].tolist() else 0,
            key="new_proj_lead"
        )
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
    with col2:
        if 'new_project_auto_dates' not in st.session_state:
            st.session_state.new_project_auto_dates = True
        auto_dates = st.checkbox("Автоопределение дат по этапам",
                                 value=st.session_state.new_project_auto_dates, key="new_proj_auto_dates")
        if not auto_dates:
            st.markdown("**Дата начала проекта**")
            if 'new_project_start' not in st.session_state:
                st.session_state.new_project_start = date.today()
            proj_start = ru_date_picker("", default=st.session_state.new_project_start, key_prefix="proj_start")
            proj_start_str = proj_start.isoformat()
            st.markdown("**Дата окончания проекта**")
            if 'new_project_end' not in st.session_state:
                st.session_state.new_project_end = date.today() + timedelta(days=60)
            proj_end = ru_date_picker("", default=st.session_state.new_project_end, key_prefix="proj_end")
            proj_end_str = proj_end.isoformat()
        else:
            proj_start_str, proj_end_str = repository.get_date_placeholders(conn)
            st.info("Даты проекта будут вычислены автоматически после добавления этапов.")
    st.markdown("**Рядовые сотрудники (можно добавить несколько)**")
    juniors_list = []
    if 'new_project_num_juniors' not in st.session_state:
        st.session_state.new_project_num_juniors = 1
    num_juniors = st.number_input("Количество рядовых", min_value=0, max_value=10,
                                 value=st.session_state.new_project_num_juniors, step=1, key="new_proj_num_juniors")
    for i in range(int(num_juniors)):
        cols = st.columns(2)
        with cols[0]:
            junior_key = f"new_proj_junior_{i}"
            if junior_key not in st.session_state:
                st.session_state[junior_key] = df_emp_sorted['id'].tolist()[0] if not df_emp_sorted.empty else None
            junior_id = st.selectbox(
                f"Рядовой {i+1}", df_emp_sorted['id'].tolist(),
                format_func=lambda x, i=i: f"{df_emp_sorted[df_emp_sorted['id']==x]['name'].values[0]} ({df_emp_sorted[df_emp_sorted['id']==x]['role_name'].values[0]})",
                index=df_emp_sorted['id'].tolist().index(st.session_state[junior_key]) if st.session_state[junior_key] in df_emp_sorted['id'].tolist() else 0,
                key=f"junior_{i}"
            )
        with cols[1]:
            junior_load_key = f"new_proj_junior_load_{i}"
            if junior_load_key not in st.session_state:
                st.session_state[junior_load_key] = 100
            junior_load = st.number_input(f"Загрузка {i+1} (%)", min_value=1, max_value=100,
                                         value=st.session_state[junior_load_key], key=f"junior_load_{i}")
        juniors_list.append((junior_id, junior_load))

    if st.button("Создать проект"):
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
    """Блок «Этапы проекта»: список этапов с редактированием/удалением и форма добавления этапа."""
    st.markdown("#### 🗂️ Этапы проекта")
    proj_phases = phases_df[phases_df['project_id'] == proj['id']]
    if not proj_phases.empty:
        for phase_num, (_, ph) in enumerate(proj_phases.iterrows(), start=1):
            with st.container():
                if open_phase_id is not None and ph['id'] == open_phase_id:
                    st.info("Вы здесь из-за перегрузки или конфликта отпуск/проект. Измените назначения на этап при необходимости.")
                col1, col2, col3, col4, col5, col6, col7 = st.columns([3, 2, 2, 2, 1.5, 1, 1])
                ph_start = ph['start_date']
                ph_end = ph['end_date']
                with col1:
                    st.write(f"{phase_num}. {ph['name']}")
                with col2:
                    st.write(ph['phase_type'])
                with col3:
                    st.write(ph_start.strftime("%d.%m.%Y") if hasattr(ph_start, 'strftime') else str(ph_start))
                with col4:
                    st.write(ph_end.strftime("%d.%m.%Y") if hasattr(ph_end, 'strftime') else str(ph_end))
                with col5:
                    st.write(f"{safe_int(ph.get('completion_percent'), 0) or 0}%")
                with col6:
                    if st.button("✏️", key=f"edit_phase_{ph['id']}"):
                        st.session_state[f'editing_phase_{ph['id']}'] = True
                with col7:
                    if st.button("❌", key=f"del_phase_{ph['id']}"):
                        repository.delete_phase(conn, ph['id'])
                        if proj['auto_dates']:
                            repository.update_project_dates_from_phases(conn, proj['id'])
                        st.cache_data.clear()
                        st.rerun()

                assigns = phase_assignments_df[phase_assignments_df['phase_id'] == ph['id']]
                if not assigns.empty:
                    st.markdown("   *Назначенные сотрудники:*")
                    for _, a in assigns.iterrows():
                        st.write(f"   - {repository.get_employee_name(conn, a['employee_id'])} ({a['load_percent']}%)")
                else:
                    st.markdown("   *Наследуется состав проекта*")

                if st.session_state.get(f'editing_phase_{ph["id"]}', False):
                    new_ph_name = st.text_input("Название этапа", value=ph['name'], key=f"edit_ph_name_{ph['id']}")
                    new_ph_type = st.selectbox(
                        "Тип", ["Обычная работа", "Командировка"],
                        index=0 if ph['phase_type'] == 'Обычная работа' else 1,
                        key=f"edit_ph_type_{ph['id']}"
                    )
                    st.markdown("**Новая дата начала**")
                    new_ph_start = ru_date_picker("", default=ph['start_date'], key_prefix=f"edit_ph_start_{ph['id']}")
                    new_ph_start_str = new_ph_start.isoformat()
                    st.markdown("**Новая дата окончания**")
                    new_ph_end = ru_date_picker("", default=ph['end_date'], key_prefix=f"edit_ph_end_{ph['id']}")
                    new_ph_end_str = new_ph_end.isoformat()
                    completion_options = list(range(0, 101, 5))
                    current_completion = safe_int(ph.get('completion_percent'), 0) or 0
                    current_completion = min(100, max(0, current_completion))
                    if current_completion not in completion_options:
                        current_completion = (current_completion // 5) * 5
                    new_ph_completion = st.selectbox(
                        "Готовность этапа, %", options=completion_options,
                        index=completion_options.index(current_completion),
                        key=f"edit_ph_completion_{ph['id']}"
                    )
                    st.markdown("**Назначения на этап (оставьте пустым для наследования)**")
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
                    col1, col2 = st.columns(2)
                    with col1:
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
                    with col2:
                        if st.button("Отмена", key=f"cancel_phase_{ph['id']}"):
                            st.session_state[f'editing_phase_{ph["id"]}'] = False
                            st.rerun()
    else:
        st.info("Нет этапов")

    with st.form(key=f"add_phase_{proj['id']}"):
        st.markdown("**➕ Добавить этап**")
        col1, col2 = st.columns(2)
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
            st.markdown("**Дата начала**")
            phase_start_key = f"new_phase_start_{proj['id']}"
            if phase_start_key not in st.session_state:
                st.session_state[phase_start_key] = date.today()
            phase_start = ru_date_picker("", default=st.session_state[phase_start_key], key_prefix=f"phase_start_{proj['id']}")
            phase_start_str = phase_start.isoformat()
            st.markdown("**Дата окончания**")
            phase_end_key = f"new_phase_end_{proj['id']}"
            if phase_end_key not in st.session_state:
                st.session_state[phase_end_key] = date.today() + timedelta(days=30)
            phase_end = ru_date_picker("", default=st.session_state[phase_end_key], key_prefix=f"phase_end_{proj['id']}")
            phase_end_str = phase_end.isoformat()
            st.markdown("**Готовность этапа, %**")
            phase_completion = st.selectbox(
                "Готовность, %", options=list(range(0, 101, 5)), index=0,
                key=f"new_phase_completion_{proj['id']}"
            )
        submitted = st.form_submit_button("Добавить этап")
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
    df_emp = repository.load_employees(conn)
    if df_emp.empty:
        msg = "Сначала добавьте сотрудников."
        log_user_facing_error(logging.WARNING, msg)
        st.warning(msg)
        return
    df_emp_sorted = df_emp.sort_values('name')

    with st.expander("➕ Новый проект", expanded=True):
        _render_new_project_form(conn, df_emp_sorted)

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
        df_proj['lead_name'] = df_proj['lead_id'].apply(lambda eid: repository.get_employee_name(conn, eid))
        juniors_df = repository.load_project_juniors(conn)
        phases_df = repository.load_phases(conn)
        phase_assignments_df = repository.load_phase_assignments(conn)
        open_project_id = st.session_state.get('open_project_id')
        open_phase_id = st.session_state.get('open_phase_id')

        for idx, proj in df_proj.iterrows():
            proj_status = proj.get('status_name', 'В работе') or 'В работе'
            expand_this = (open_project_id is not None and proj['id'] == open_project_id)
            with st.expander(f"📁 {proj['name']} — {proj['client_company'] if proj['client_company'] else 'Без компании'} [{proj_status}]", expanded=expand_this):
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
                    lead_options = df_emp_sorted_edit['id'].tolist()
                    proj_lead_id = safe_int(proj.get('lead_id'), None)
                    if proj_lead_id is None and lead_options:
                        proj_lead_id = lead_options[0]
                    lead_index = lead_options.index(proj_lead_id) if (lead_options and proj_lead_id in lead_options) else 0

                    with st.form(key=f"edit_form_{pid}"):
                        new_name = st.text_input("Название", value=proj['name'] or "", key=f"edit_name_{pid}")
                        new_client = st.text_input("Компания клиента", value=(proj['client_company'] or "") if proj.get('client_company') is not None else "", key=f"edit_client_{pid}")
                        new_lead = st.selectbox(
                            "Ведущий",
                            lead_options,
                            index=lead_index,
                            format_func=lambda x: df_emp_sorted_edit[df_emp_sorted_edit['id'] == x]['name'].values[0],
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
