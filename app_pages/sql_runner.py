# -*- coding: utf-8 -*-
"""Страница «SQL-запросы»: ввод запросов к SQLite и табличный вывод результатов."""
import logging
import sqlite3

import pandas as pd
import streamlit as st

import config as app_config
from utils.app_logging import log_user_facing_error, record_error


def _first_statement(text: str) -> str:
    """Возвращает первый SQL-оператор (до первой точки с запятой или весь текст)."""
    if not text or not text.strip():
        return ""
    parts = text.strip().split(";")
    first = parts[0].strip()
    return first if first else ""


def render(conn):
    st.header("🔍 SQL-запросы")
    st.markdown(
        "Инструмент для проверки наличия и корректности данных после импортов и для выгрузок. "
        "Запросы выполняются к текущей БД приложения (SQLite)."
    )
    st.warning(
        "Запросы выполняются в текущей БД приложения. Будьте осторожны с изменяющими запросами (INSERT, UPDATE, DELETE)."
    )

    # Путь к БД (опционально по плану)
    try:
        db_path = getattr(app_config, "DB_PATH", "resource_planner.db")
        st.caption(f"База данных: {db_path}")
    except Exception:
        pass

    sql = st.text_area(
        "SQL-запрос",
        value=st.session_state.get("sql_runner_last_query", ""),
        height=120,
        placeholder="SELECT * FROM roles LIMIT 10",
        key="sql_runner_query",
    )

    if st.button("Выполнить", key="sql_runner_run"):
        statement = _first_statement(sql)
        if not statement:
            msg = "Введите непустой SQL-запрос."
            log_user_facing_error(logging.WARNING, msg)
            st.error(msg)
            return

        try:
            cursor = conn.execute(statement)
            if cursor.description:
                # Результирующий набор (SELECT, PRAGMA и т.п.)
                rows = cursor.fetchall()
                columns = [d[0] for d in cursor.description]
                df = pd.DataFrame(rows, columns=columns)
                st.session_state["sql_runner_last_query"] = sql
                st.caption(f"Строк: {len(df)}")
                st.dataframe(df, width="stretch", hide_index=True)
            else:
                # INSERT / UPDATE / DELETE
                conn.commit()
                st.session_state["sql_runner_last_query"] = sql
                st.success(f"Выполнено. Затронуто строк: {cursor.rowcount}")
        except sqlite3.Error as e:
            msg_sql = f"Ошибка SQL: {e}"
            record_error(e, user_message=msg_sql)
            st.error(msg_sql)
            st.code(str(e), language="text")
        except Exception as e:
            record_error(e, user_message=f"Ошибка: {e}")
            st.error(f"Ошибка: {e}")
            st.code(str(e), language="text")

    # До первого выполнения — нейтральный текст
    if "sql_runner_last_query" not in st.session_state and not sql.strip():
        st.info("Введите запрос в поле выше и нажмите **Выполнить**.")
