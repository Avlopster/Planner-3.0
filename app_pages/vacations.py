# -*- coding: utf-8 -*-
"""Страница «Отпуска»: периоды отпусков, добавление, редактирование, удаление."""
import logging
from datetime import date, timedelta

import streamlit as st

from components import ru_date_picker
import repository
from utils.app_logging import get_actions_logger, log_user_facing_error

actions_log = get_actions_logger()


def render(conn):
    """Отрисовка страницы «Отпуска»: периоды отпусков, добавление и редактирование. conn — подключение к БД."""
    st.header("🏖️ Отпуска сотрудников")
    df_emp = repository.load_employees(conn)
    cur = conn.cursor()
    if df_emp.empty:
        msg = "Сначала добавьте сотрудников."
        log_user_facing_error(logging.WARNING, msg)
        st.warning(msg)
        return
    with st.expander("➕ Добавить период отпуска", expanded=True):
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            df_emp_sorted = df_emp.sort_values('name')
            if 'new_vacation_emp_id' not in st.session_state:
                st.session_state.new_vacation_emp_id = df_emp_sorted['id'].tolist()[0] if not df_emp_sorted.empty else None
            emp_id = st.selectbox(
                "Сотрудник", df_emp_sorted['id'].tolist(),
                format_func=lambda x: df_emp_sorted[df_emp_sorted['id'] == x]['name'].values[0],
                index=df_emp_sorted['id'].tolist().index(st.session_state.new_vacation_emp_id) if st.session_state.new_vacation_emp_id in df_emp_sorted['id'].tolist() else 0,
                key="new_vac_emp_select"
            )
        with col2:
            st.markdown("**Дата начала**")
            if 'new_vacation_start' not in st.session_state:
                st.session_state.new_vacation_start = date.today()
            start_date = ru_date_picker("", default=st.session_state.new_vacation_start, key_prefix="vac_add_start")
            st.markdown("**Дата окончания**")
            if 'new_vacation_end' not in st.session_state:
                st.session_state.new_vacation_end = date.today() + timedelta(days=14)
            end_date = ru_date_picker("", default=st.session_state.new_vacation_end, key_prefix="vac_add_end")
        with col3:
            st.write("")
            if st.button("Добавить", key="add_vac_btn"):
                if start_date <= end_date:
                    has_overlap, conflicting = repository.check_vacation_overlap(conn, emp_id, start_date, end_date)
                    if has_overlap:
                        conf = conflicting
                        conf_start = conf['start_date'].strftime("%d.%m.%Y") if hasattr(conf['start_date'], 'strftime') else str(conf['start_date'])
                        conf_end = conf['end_date'].strftime("%d.%m.%Y") if hasattr(conf['end_date'], 'strftime') else str(conf['end_date'])
                        err_msg = f"Период отпуска пересекается с существующим отпуском: {conf_start} — {conf_end}"
                        log_user_facing_error(logging.ERROR, err_msg)
                        st.error(err_msg)
                    else:
                        cur.execute("INSERT INTO vacations (employee_id, start_date, end_date) VALUES (?,?,?)", (emp_id, start_date.isoformat(), end_date.isoformat()))
                        conn.commit()
                        actions_log.info("Добавлен отпуск: employee_id=%s %s — %s", emp_id, start_date, end_date)
                        st.success("Отпуск добавлен!")
                        if not df_emp_sorted.empty:
                            st.session_state.new_vacation_emp_id = df_emp_sorted['id'].tolist()[0]
                        st.session_state.new_vacation_start = date.today()
                        st.session_state.new_vacation_end = date.today() + timedelta(days=14)
                        for key in ['vac_add_start_day', 'vac_add_start_month', 'vac_add_start_year', 'vac_add_end_day', 'vac_add_end_month', 'vac_add_end_year']:
                            if key in st.session_state:
                                del st.session_state[key]
                        st.cache_data.clear()
                        st.rerun()
                else:
                    msg_date = "Дата начала должна быть раньше даты окончания."
                    log_user_facing_error(logging.ERROR, msg_date)
                    st.error(msg_date)
    st.subheader("Все периоды отпусков")
    df_vac = repository.load_vacations(conn)
    if not df_vac.empty:
        df_vac = df_vac.copy()
        df_vac['employee_name'] = df_vac['employee_id'].apply(lambda eid: repository.get_employee_name(conn, eid))
        for num, (idx, row) in enumerate(df_vac.iterrows(), start=1):
            col1, col2, col3, col4, col5, col6 = st.columns([1, 3, 2, 2, 2, 1])
            with col1:
                st.write(num)
            with col2:
                st.write(row['employee_name'])
            with col3:
                st.write(row['start_date'].strftime("%d.%m.%Y") if hasattr(row['start_date'], 'strftime') else str(row['start_date']))
            with col4:
                st.write(row['end_date'].strftime("%d.%m.%Y") if hasattr(row['end_date'], 'strftime') else str(row['end_date']))
            with col5:
                if st.button("✏️", key=f"edit_vac_{row['id']}"):
                    st.session_state[f'editing_vac_{row["id"]}'] = True
            with col6:
                if st.button("❌", key=f"del_vac_{row['id']}"):
                    repository.delete_vacation(conn, row['id'])
                    actions_log.info("Удалён отпуск id=%s", row['id'])
                    st.cache_data.clear()
                    st.rerun()
            if st.session_state.get(f'editing_vac_{row["id"]}', False):
                with st.form(key=f"edit_vac_form_{row['id']}"):
                    st.markdown("**Новая дата начала**")
                    new_start = ru_date_picker("", default=row['start_date'], key_prefix=f"edit_vac_start_{row['id']}")
                    st.markdown("**Новая дата окончания**")
                    new_end = ru_date_picker("", default=row['end_date'], key_prefix=f"edit_vac_end_{row['id']}")
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.form_submit_button("💾 Сохранить"):
                            if new_start <= new_end:
                                has_overlap, conflicting = repository.check_vacation_overlap(conn, row['employee_id'], new_start, new_end, exclude_vacation_id=row['id'])
                                if has_overlap:
                                    conf = conflicting
                                    conf_start = conf['start_date'].strftime("%d.%m.%Y") if hasattr(conf['start_date'], 'strftime') else str(conf['start_date'])
                                    conf_end = conf['end_date'].strftime("%d.%m.%Y") if hasattr(conf['end_date'], 'strftime') else str(conf['end_date'])
                                    err_edit = f"Период отпуска пересекается с существующим отпуском: {conf_start} — {conf_end}"
                                    log_user_facing_error(logging.ERROR, err_edit)
                                    st.error(err_edit)
                                else:
                                    cur.execute("UPDATE vacations SET start_date = ?, end_date = ? WHERE id = ?", (new_start.isoformat(), new_end.isoformat(), row['id']))
                                    conn.commit()
                                    actions_log.info("Обновлён отпуск id=%s", row['id'])
                                    st.success("Отпуск обновлён!")
                                    st.session_state[f'editing_vac_{row["id"]}'] = False
                                    st.cache_data.clear()
                                    st.rerun()
                            else:
                                msg_edit_date = "Дата начала должна быть раньше даты окончания."
                                log_user_facing_error(logging.ERROR, msg_edit_date)
                                st.error(msg_edit_date)
                    with col2:
                        if st.form_submit_button("Отмена"):
                            st.session_state[f'editing_vac_{row["id"]}'] = False
                            st.rerun()
    else:
        st.info("Нет записей об отпусках.")
