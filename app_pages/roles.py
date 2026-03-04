# -*- coding: utf-8 -*-
"""Страница «Роли»: справочник ролей, добавление, редактирование, удаление."""
import logging
import sqlite3

import streamlit as st

import repository
from utils.app_logging import get_actions_logger, log_user_facing_error

actions_log = get_actions_logger()


def render(conn):
    """Отрисовка страницы «Роли»: справочник ролей, добавление и редактирование. conn — подключение к БД."""
    st.header("📋 Справочник ролей")
    col1, col2 = st.columns([3, 1])
    with col1:
        new_role = st.text_input("Название новой роли")
    with col2:
        if st.button("➕ Добавить роль"):
            if new_role:
                try:
                    cur = conn.cursor()
                    cur.execute("INSERT INTO roles (name) VALUES (?)", (new_role,))
                    conn.commit()
                    actions_log.info("Добавлена роль '%s'", new_role)
                    st.success(f"Роль '{new_role}' добавлена!")
                    st.cache_data.clear()
                    st.rerun()
                except sqlite3.IntegrityError:
                    msg = "Такая роль уже существует."
                    log_user_facing_error(logging.ERROR, msg)
                    st.error(msg)
            else:
                warn_msg = "Введите название роли"
                log_user_facing_error(logging.WARNING, warn_msg)
                st.warning(warn_msg)
    st.subheader("Существующие роли")
    df_roles = repository.load_roles(conn)
    if not df_roles.empty:
        for idx, row in df_roles.iterrows():
            col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
            with col1:
                st.write(row['name'])
            with col2:
                emp = repository.load_employees(conn)
                cnt = len(emp[emp['role_id'] == row['id']])
                st.write(f"👥 {cnt} сотрудников")
            with col3:
                if row['name'] not in ['Senior', 'Junior']:
                    if st.button("✏️", key=f"edit_role_{row['id']}"):
                        st.session_state[f'editing_role_{row["id"]}'] = True
                else:
                    st.write("—")
            with col4:
                if row['name'] not in ['Senior', 'Junior']:
                    if st.button("❌", key=f"del_role_{row['id']}"):
                        success, msg = repository.delete_role(conn, row['id'])
                        if success:
                            actions_log.info("Удалена роль '%s' (id=%s)", row['name'], row['id'])
                            st.success(f"Роль '{row['name']}' удалена")
                            st.cache_data.clear()
                            st.rerun()
                        elif msg:
                            log_user_facing_error(logging.ERROR, msg)
                            st.error(msg)
                else:
                    st.write("—")
            if st.session_state.get(f'editing_role_{row["id"]}', False):
                with st.form(key=f"edit_role_form_{row['id']}"):
                    new_name = st.text_input("Новое название роли", value=row['name'])
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.form_submit_button("💾 Сохранить"):
                            try:
                                cur = conn.cursor()
                                cur.execute("UPDATE roles SET name = ? WHERE id = ?", (new_name, row['id']))
                                conn.commit()
                                actions_log.info("Роль обновлена: id=%s -> '%s'", row['id'], new_name)
                                st.success("Роль обновлена!")
                                st.session_state[f'editing_role_{row["id"]}'] = False
                                st.cache_data.clear()
                                st.rerun()
                            except sqlite3.IntegrityError:
                                msg_dup = "Роль с таким именем уже существует."
                                log_user_facing_error(logging.ERROR, msg_dup)
                                st.error(msg_dup)
                    with col2:
                        if st.form_submit_button("Отмена"):
                            st.session_state[f'editing_role_{row["id"]}'] = False
                            st.rerun()
    else:
        st.info("Нет ролей. Добавьте первую роль.")
