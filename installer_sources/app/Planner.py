import os

from utils.app_logging import init_app_logging
init_app_logging()

import streamlit as st
import sqlite3
import math
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, date
import io
import calendar

import config as app_config
from utils.date_utils import date_range_list
from utils.type_utils import safe_int
from utils.app_logging import log_user_facing_error
import logging
import database as db
import repository
import load_calculator
import capacity as capacity_module

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


@st.cache_data(ttl=60)
def load_roles(db_path: str = ""):
    """db_path в ключе кеша — при смене БД кеш инвалидируется."""
    return repository.load_roles(conn)


@st.cache_data(ttl=60)
def load_employees(db_path: str = ""):
    return repository.load_employees(conn)


@st.cache_data(ttl=60)
def load_vacations(db_path: str = ""):
    return repository.load_vacations(conn)


def get_average_vacation_days_per_employee(year=None):
    return load_calculator.get_average_vacation_days_per_employee(conn, year)

@st.cache_data(ttl=60)
def load_projects(db_path: str = ""):
    return repository.load_projects(conn)


@st.cache_data(ttl=60)
def load_project_juniors(db_path: str = ""):
    return repository.load_project_juniors(conn)


@st.cache_data(ttl=60)
def load_phases(db_path: str = ""):
    return repository.load_phases(conn)


def gantt_project_completion_percent(project_id, display_date, phases_df):
    return repository.gantt_project_completion_percent(project_id, display_date, phases_df)


@st.cache_data(ttl=60)
def load_phase_assignments(db_path: str = ""):
    return repository.load_phase_assignments(conn)

def get_employee_name(emp_id):
    return repository.get_employee_name(conn, emp_id)

def get_project_name(proj_id):
    return repository.get_project_name(conn, proj_id)

def get_employee_vacations(emp_id):
    return repository.get_employee_vacations(conn, emp_id)

def check_vacation_overlap(emp_id, start_date, end_date, exclude_vacation_id=None):
    return repository.check_vacation_overlap(conn, emp_id, start_date, end_date, exclude_vacation_id)

def employee_load_by_day(employee_id, start_date, end_date, ignore_vacations=False):
    return load_calculator.employee_load_by_day(conn, employee_id, start_date, end_date, ignore_vacations)

def get_employee_load_sources_by_day(employee_id, day_date):
    return load_calculator.get_employee_load_sources_by_day(conn, employee_id, day_date)

def get_employee_phases_on_date(employee_id, day_date):
    return load_calculator.get_employee_phases_on_date(conn, employee_id, day_date)

def get_replacement_candidates_for_phase(phase_id, exclude_employee_id, day_date, max_candidates=3, load_threshold=0.8):
    return load_calculator.get_replacement_candidates_for_phase(conn, phase_id, exclude_employee_id, day_date, max_candidates, load_threshold)

def delete_project(project_id):
    repository.delete_project(conn, project_id)

def delete_employee(employee_id):
    success, msg = repository.delete_employee(conn, employee_id)
    if not success and msg:
        log_user_facing_error(logging.ERROR, msg)
        st.error(msg)
    return success

def delete_vacation(vacation_id):
    repository.delete_vacation(conn, vacation_id)

def delete_role(role_id):
    success, msg = repository.delete_role(conn, role_id)
    if not success and msg:
        log_user_facing_error(logging.ERROR, msg)
        st.error(msg)
    return success

def update_project_dates_from_phases(project_id):
    return repository.update_project_dates_from_phases(conn, project_id)

def get_config(key, default=None):
    return repository.get_config(conn, key, default)

def set_config(key, value):
    repository.set_config(conn, key, value)

def load_capacity_config():
    return repository.load_capacity_config(conn)

def annual_project_capacity(year=None):
    return capacity_module.annual_project_capacity(conn, year)

def department_load_summary(start_date, end_date):
    return load_calculator.department_load_summary(conn, start_date, end_date)

def overload_shortfall(start_date, end_date):
    return load_calculator.overload_shortfall(conn, start_date, end_date)


from components import ru_date_picker, menu_button

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