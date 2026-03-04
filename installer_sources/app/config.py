# -*- coding: utf-8 -*-
"""Конфигурация приложения Planner: путь к БД, константы расчёта ёмкости, плейсхолдеры дат, UI."""

import os

# Путь к БД: всегда абсолютный, относительно каталога проекта (не зависит от cwd при запуске Streamlit)
_root = os.path.dirname(os.path.abspath(__file__))
_db_env = os.environ.get('PLANNER_DB_PATH') or 'resource_planner.db'
DB_PATH = os.path.abspath(os.path.normpath(os.path.join(_root, _db_env)) if not os.path.isabs(_db_env) else os.path.normpath(_db_env))


def get_logs_dir() -> str:
    """Каталог для логов приложения. Если каталог приложения доступен для записи — logs рядом с приложением, иначе %LOCALAPPDATA%\\Planner\\Logs. Каталог не создаётся."""
    if os.access(_root, os.W_OK):
        return os.path.join(_root, "logs")
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Planner", "Logs")


LOGS_DIR = get_logs_dir()
DB_LOG_PATH = os.path.join(LOGS_DIR, "planner_db.log")
ACTIONS_LOG_PATH = os.path.join(LOGS_DIR, "planner_actions.log")
ERRORS_LOG_PATH = os.path.join(LOGS_DIR, "planner_errors.log")

# Кеш Streamlit (секунды)
CACHE_TTL = 60

# Плейсхолдеры дат при импорте (невалидные/пустые даты)
DATE_PLACEHOLDER_START = '1970-01-01'
DATE_PLACEHOLDER_END = '2099-12-31'

# Параметры годовой ёмкости (значения по умолчанию при отсутствии в таблице config)
ANNUAL_WORKING_DAYS_DEFAULT = 247
ANNUAL_VACATION_DAYS_DEFAULT = 28
TYPICAL_PROJECT_DAYS_DEFAULT = 30
TYPICAL_LEAD_SHARE_DEFAULT = 0.25
MAX_CONCURRENT_PROJECTS_DEFAULT = 4

# Роли для расчёта ёмкости (по имени)
ROLE_JUNIOR = 'Junior'
ROLE_SENIOR = 'Senior'

# Статусы проектов «активные» (для отчётов, годовой ёмкости и т.п.)
ACTIVE_STATUSES = ('В работе', 'Планируется')

# Статус «в работе» — для фильтра Ганта «Только активные» (планируемые исключаются)
GANTT_ONLY_ACTIVE_STATUSES = ('В работе',)

# Типы этапов (CHECK в БД)
PHASE_TYPES = ('Обычная работа', 'Командировка')

# Защищённые роли (не удалять при наличии сотрудников)
ROLES_PROTECTED = ('Senior', 'Junior')

# Русские названия месяцев (для выбора даты)
MONTHS_RU = [
    'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
    'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
]
MONTH_TO_NUM = {name: i + 1 for i, name in enumerate(MONTHS_RU)}
NUM_TO_MONTH = {i + 1: name for i, name in enumerate(MONTHS_RU)}
