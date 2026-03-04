# -*- coding: utf-8 -*-
"""Страница «Очистить данные»: резервная копия БД и полная очистка."""
import os
from datetime import date

import streamlit as st

import config as app_config
from utils.app_logging import get_actions_logger


def render(conn):
    """Отрисовка страницы «Очистить данные»: резервная копия БД и полная очистка. conn — подключение к БД."""
    st.header("⚠️ Очистка всех данных")
    col_backup, col_clear = st.columns([1, 1])
    with col_backup:
        st.markdown("**Резервная копия**")
        db_path = app_config.DB_PATH
        if os.path.exists(db_path):
            with open(db_path, "rb") as f:
                db_bytes = f.read()
            st.download_button("📥 Скачать backup БД", data=db_bytes,
                               file_name=f"resource_planner_backup_{date.today().isoformat()}.db",
                               mime="application/x-sqlite3", key="backup_db")
        else:
            st.info("База данных ещё не создана.")
    with col_clear:
        st.markdown("**Очистка**")
        st.warning("Это действие удалит всех сотрудников, проекты, этапы, отпуска и роли (кроме базовых Senior/Junior).")
    if st.button("Удалить все данные"):
        cur = conn.cursor()
        cur.execute("DELETE FROM phase_assignments")
        cur.execute("DELETE FROM project_phases")
        cur.execute("DELETE FROM project_juniors")
        cur.execute("DELETE FROM projects")
        cur.execute("DELETE FROM vacations")
        cur.execute("DELETE FROM employees")
        cur.execute("DELETE FROM roles WHERE name NOT IN ('Senior', 'Junior')")
        conn.commit()
        get_actions_logger().info("Выполнена полная очистка данных")
        st.success("Все данные удалены. Базовые роли Senior и Junior сохранены.")
        st.cache_data.clear()
        st.rerun()
