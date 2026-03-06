# -*- coding: utf-8 -*-
"""Страница «Сотрудники»: список, добавление, редактирование, удаление."""
import logging
from datetime import date, timedelta

import pandas as pd
import streamlit as st

import repository
from utils.app_logging import get_actions_logger, log_user_facing_error
from utils.type_utils import safe_int

actions_log = get_actions_logger()


def render(conn):
    """Отрисовка страницы «Сотрудники»: список, добавление и редактирование. conn — подключение к БД."""
    st.header("👥 Сотрудники")
    df_roles = repository.load_roles(conn)
    cur = conn.cursor()
    with st.expander("➕ Добавить нового сотрудника", expanded=True):
        col1, col2, col3, col4, col5, col6 = st.columns([2, 1, 2, 1, 2, 1])
        with col1:
            if 'new_employee_name' not in st.session_state:
                st.session_state.new_employee_name = ""
            name = st.text_input("ФИО", value=st.session_state.new_employee_name, key="new_emp_name_input")
        with col2:
            initials = st.text_input("Инициалы", value="", key="new_emp_initials", placeholder="Не указаны")
        with col3:
            if not df_roles.empty:
                df_roles_sorted = df_roles.sort_values('name')
                if 'new_employee_role_id' not in st.session_state:
                    st.session_state.new_employee_role_id = df_roles_sorted['id'].tolist()[0] if not df_roles_sorted.empty else None
                role_id = st.selectbox(
                    "Роль", df_roles_sorted['id'].tolist(),
                    format_func=lambda x: df_roles_sorted[df_roles_sorted['id'] == x]['name'].values[0],
                    index=df_roles_sorted['id'].tolist().index(st.session_state.new_employee_role_id) if st.session_state.new_employee_role_id in df_roles_sorted['id'].tolist() else 0,
                    key="new_emp_role_select"
                )
            else:
                msg = "Сначала добавьте роли в разделе 'Роли'."
                log_user_facing_error(logging.WARNING, msg)
                st.error(msg)
                role_id = None
        with col4:
            department = st.text_input("Отдел", value="", key="new_emp_dept", placeholder="Не указан")
        with col5:
            default_load = st.number_input("Ставка, %", min_value=10, max_value=100, value=100, step=5, key="new_emp_load")
        with col6:
            if st.button("Добавить"):
                if name and role_id is not None:
                    cur.execute(
                        "INSERT INTO employees (name, role_id, department, default_load_percent, initials) VALUES (?,?,?,?,?)",
                        (name, role_id, department.strip() or None, default_load, initials.strip() or None)
                    )
                    conn.commit()
                    actions_log.info("Добавлен сотрудник '%s' (role_id=%s)", name, role_id)
                    st.success(f"Сотрудник {name} добавлен!")
                    st.session_state.new_employee_name = ""
                    if not df_roles.empty:
                        df_roles_sorted = df_roles.sort_values('name')
                        st.session_state.new_employee_role_id = df_roles_sorted['id'].tolist()[0]
                    st.cache_data.clear()
                    st.rerun()
                else:
                    warn_msg = "Введите имя и выберите роль"
                    log_user_facing_error(logging.WARNING, warn_msg)
                    st.warning(warn_msg)
    st.subheader("Список сотрудников")
    df_emp = repository.load_employees(conn)
    if not df_emp.empty:
        search_emp = st.text_input("🔍 Поиск по ФИО, инициалам, роли или отделу", key="emp_search", placeholder="Введите текст...")
        if search_emp:
            mask = (df_emp['name'].str.contains(search_emp, case=False, na=False)) | (df_emp['role_name'].str.contains(search_emp, case=False, na=False))
            if 'department' in df_emp.columns:
                mask = mask | (df_emp['department'].fillna('').str.contains(search_emp, case=False, na=False))
            if 'initials' in df_emp.columns:
                mask = mask | (df_emp['initials'].fillna('').str.contains(search_emp, case=False, na=False))
            df_emp = df_emp[mask]
    if not df_emp.empty:
        for num, (idx, row) in enumerate(df_emp.iterrows(), start=1):
            col1, col2, col3, col4, col5, col6, col7, col8 = st.columns([1, 2, 1, 2, 2, 2, 1, 1])
            with col1:
                st.write(num)
            with col2:
                st.write(row['name'])
            with col3:
                st.write(row.get('initials', '') or '—')
            with col4:
                st.write(row['role_name'])
            with col5:
                st.write(row.get('department', '') or '—')
            with col6:
                vacs = repository.get_employee_vacations(conn, row['id'])
                st.write(f"{len(vacs)} периодов")
            with col7:
                if st.button("✏️", key=f"edit_emp_{row['id']}"):
                    st.session_state[f'editing_emp_{row["id"]}'] = True
            with col8:
                if st.button("❌", key=f"del_emp_{row['id']}"):
                    success, msg = repository.delete_employee(conn, row['id'])
                    if success:
                        actions_log.info("Удалён сотрудник id=%s", row['id'])
                        st.cache_data.clear()
                        st.rerun()
                    elif msg:
                        log_user_facing_error(logging.ERROR, msg)
                        st.error(msg)
            if st.session_state.get(f'editing_emp_{row["id"]}', False):
                with st.form(key=f"edit_emp_form_{row['id']}"):
                    new_name = st.text_input("ФИО", value=row['name'])
                    new_initials = st.text_input("Инициалы", value=str(row.get('initials', '') or ''))
                    df_roles_sorted = df_roles.sort_values('name')
                    role_options = df_roles_sorted['id'].tolist()
                    current_role = row['role_id']
                    try:
                        default_idx = role_options.index(current_role) if current_role in role_options else 0
                    except (ValueError, TypeError):
                        default_idx = 0
                    new_role_id = st.selectbox(
                        "Роль", role_options,
                        format_func=lambda x: df_roles_sorted[df_roles_sorted['id'] == x]['name'].values[0],
                        index=default_idx
                    )
                    new_dept = st.text_input("Отдел", value=str(row.get('department', '') or ''))
                    new_load = st.number_input("Ставка, %", min_value=10, max_value=100, value=safe_int(row.get('default_load_percent'), 100) or 100, step=5)
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.form_submit_button("💾 Сохранить"):
                            cur.execute(
                                "UPDATE employees SET name = ?, role_id = ?, department = ?, default_load_percent = ?, initials = ? WHERE id = ?",
                                (new_name, new_role_id, new_dept.strip() or None, new_load, new_initials.strip() or None, row['id'])
                            )
                            conn.commit()
                            actions_log.info("Обновлён сотрудник id=%s", row['id'])
                            st.success("Данные сотрудника обновлены!")
                            st.session_state[f'editing_emp_{row["id"]}'] = False
                            st.cache_data.clear()
                            st.rerun()
                    with col2:
                        if st.form_submit_button("Отмена"):
                            st.session_state[f'editing_emp_{row["id"]}'] = False
                            st.rerun()
    else:
        st.info("Нет сотрудников. Добавьте первого сотрудника.")
