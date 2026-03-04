# -*- coding: utf-8 -*-
"""Страница «SQL-запросы»: ввод запросов к SQLite и табличный вывод результатов.

По умолчанию разрешены только запросы на чтение (SELECT, PRAGMA и т.п.).
Для INSERT/UPDATE/DELETE требуется явное подтверждение пользователя.
Текст запроса не логируется (возможны чувствительные данные).
"""
import logging
import re
import sqlite3

import pandas as pd
import streamlit as st

import config as app_config
from utils.app_logging import log_user_facing_error, record_error

# Ключевые слова запросов на запись (проверяется первый токен после комментариев/пробелов)
_WRITE_KEYWORDS = frozenset({"insert", "update", "delete", "replace", "create", "drop", "alter"})


def _first_statement(text: str) -> str:
    """Возвращает первый SQL-оператор (до первой точки с запятой или весь текст)."""
    if not text or not text.strip():
        return ""
    parts = text.strip().split(";")
    first = parts[0].strip()
    return first if first else ""


def _is_read_only_statement(statement: str) -> bool:
    """Определяет, является ли оператор только чтением (SELECT, PRAGMA, с комментариями)."""
    if not statement or not statement.strip():
        return True
    # Убираем однострочные и многстрочные комментарии, берём первый токен
    s = re.sub(r"--[^\n]*", "", statement)
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.DOTALL)
    s = s.strip().lower()
    if not s:
        return True
    first_token = s.split()[0] if s.split() else ""
    return first_token not in _WRITE_KEYWORDS


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

    allow_write = st.checkbox(
        "Разрешить изменение данных (INSERT, UPDATE, DELETE и т.д.)",
        value=False,
        key="sql_runner_allow_write",
        help="Без этой отметки выполняются только запросы на чтение (SELECT, PRAGMA).",
    )

    if st.button("Выполнить", key="sql_runner_run"):
        statement = _first_statement(sql)
        if not statement:
            msg = "Введите непустой SQL-запрос."
            log_user_facing_error(logging.WARNING, msg)
            st.error(msg)
            return

        if not _is_read_only_statement(statement) and not allow_write:
            st.error(
                "Этот запрос изменяет данные. Включите «Разрешить изменение данных» и повторите выполнение."
            )
            log_user_facing_error(logging.WARNING, "SQL runner: запрос на запись отклонён (подтверждение не дано).")
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
