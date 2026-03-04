"""
Точка входа приложения Planner: инициализация логов, БД, меню и роутинг по разделам.
Страницы (app_pages) получают conn и вызывают repository / load_calculator / capacity напрямую.
"""
import os

from utils.app_logging import init_app_logging
init_app_logging()

import streamlit as st

import config as app_config
import database as db
from components import menu_button

# Одно подключение к БД на всю сессию; фактический путь (в т.ч. fallback) хранится в session_state
_initial_db_path = os.path.abspath(app_config.DB_PATH)
if "_db_conn" not in st.session_state:
    conn, actual_path = db.get_connection(_initial_db_path)
    st.session_state["_db_conn"] = conn
    st.session_state["_db_path"] = actual_path
    db.init_schema(conn)
    db.run_migrations(conn)
conn = st.session_state["_db_conn"]
_db_path = st.session_state.get("_db_path", _initial_db_path)

# ---------------------------
# 4. ФИКСИРОВАННОЕ МЕНЮ
# ---------------------------
st.set_page_config(page_title="Планировщик ресурсов", layout="wide")

# Централизованные стили из .streamlit/styles.css
_css_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".streamlit", "styles.css")
if os.path.isfile(_css_path):
    with open(_css_path, "r", encoding="utf-8") as f:
        st.markdown(f"<style>\n{f.read()}\n</style>", unsafe_allow_html=True)

st.title("📊 Планировщик ресурсов отдела")
st.markdown("Управление сотрудниками, ролями, проектами, этапами и отпусками. Доступен импорт из Excel.")

if 'menu' not in st.session_state:
    st.session_state.menu = "Дашборд"

st.sidebar.title("📌 Навигация")
row1 = st.sidebar.columns(3)
with row1[0]: menu_button("Дашборд", "🖥️")
with row1[1]: menu_button("Роли", "📋")
with row1[2]: menu_button("Сотрудники", "👥")
row2 = st.sidebar.columns(3)
with row2[0]: menu_button("Отпуска", "🏖️")
with row2[1]: menu_button("Проекты и этапы", "📌")
with row2[2]: menu_button("Импорт из Excel", "📥")
row3 = st.sidebar.columns(3)
with row3[0]: menu_button("Аналитика", "📈")
with row3[1]: menu_button("Диаграмма Ганта", "📊")
with row3[2]: menu_button("Календарь", "🗓️")
row4 = st.sidebar.columns(3)
with row4[0]: menu_button("Конфигурация", "⚙️")
with row4[1]: menu_button("Очистить данные", "⚠️")
with row4[2]: menu_button("SQL-запросы", "🔍")
st.sidebar.divider()
st.sidebar.caption(f"Текущий раздел: **{st.session_state.menu}**")
st.sidebar.caption(f"БД: `{_db_path}`")

# ---------------------------
# 6. ОТОБРАЖЕНИЕ РАЗДЕЛОВ
# ---------------------------

# ---------- ДАШБОРД ----------
if st.session_state.menu == "Дашборд":
    from app_pages import dashboard
    dashboard.render(conn)
# ---------- РОЛИ ----------
elif st.session_state.menu == "Роли":
    from app_pages import roles
    roles.render(conn)
# ---------- СОТРУДНИКИ ----------
elif st.session_state.menu == "Сотрудники":
    from app_pages import employees
    employees.render(conn)
# ---------- ОТПУСКА ----------
elif st.session_state.menu == "Отпуска":
    from app_pages import vacations
    vacations.render(conn)
# ---------- ПРОЕКТЫ И ЭТАПЫ ----------
elif st.session_state.menu == "Проекты и этапы":
    from app_pages import projects
    projects.render(conn, db_path=_db_path)

# ---------- ИМПОРТ ИЗ EXCEL ----------
elif st.session_state.menu == "Импорт из Excel":
    from app_pages import import_excel
    import_excel.render(conn)

# ---------- АНАЛИТИКА ----------
elif st.session_state.menu == "Аналитика":
    from app_pages import analytics
    analytics.render(conn)

# ---------- ДИАГРАММА ГАНТА ----------
elif st.session_state.menu == "Диаграмма Ганта":
    from app_pages import gantt
    gantt.render(conn)

# ---------- КАЛЕНДАРЬ ----------
elif st.session_state.menu == "Календарь":
    from app_pages import calendar as calendar_page
    calendar_page.render(conn)

# ---------- КОНФИГУРАЦИЯ ----------
elif st.session_state.menu == "Конфигурация":
    from app_pages import config_page
    config_page.render(conn, db_path=_db_path)

# ---------- SQL-ЗАПРОСЫ ----------
elif st.session_state.menu == "SQL-запросы":
    from app_pages import sql_runner
    sql_runner.render(conn)

# ---------- ОЧИСТКА ДАННЫХ ----------
elif st.session_state.menu == "Очистить данные":
    from app_pages import clear_data
    clear_data.render(conn)