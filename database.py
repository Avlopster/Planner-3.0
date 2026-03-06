# -*- coding: utf-8 -*-
"""Слой БД: подключение, схема, миграции."""
import os
import sqlite3
from typing import Optional, Tuple

import pandas as pd

import config as app_config
import repository
from utils.app_logging import get_db_logger

logger = get_db_logger()


def _ensure_dir_and_connect(path: str):
    """Create parent directory if needed and open SQLite connection. Raises on failure."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.OperationalError as e:
        logger.debug("WAL checkpoint skipped: %s", e)
    conn.execute("PRAGMA journal_mode=DELETE")
    return conn


def _fallback_db_path() -> str:
    """Writable path for DB when default location is not writable (e.g. installed under Program Files)."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, "Planner")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "resource_planner.db")


def get_connection(db_path: Optional[str] = None) -> Tuple[sqlite3.Connection, str]:
    """Возвращает (подключение к SQLite, фактический путь к файлу БД).
    db_path по умолчанию из config. Путь всегда нормализуется до абсолютного.
    Создаёт каталог для файла БД при необходимости. При ошибке «unable to open database file»
    использует запасной путь в %LOCALAPPDATA%\\Planner (конфиг не изменяется).
    """
    raw = db_path or app_config.DB_PATH
    path = os.path.abspath(os.path.normpath(os.path.expanduser(raw)))
    try:
        conn = _ensure_dir_and_connect(path)
        logger.info("Подключение к БД: %s", path)
        return (conn, path)
    except sqlite3.OperationalError as e:
        if "unable to open database file" not in str(e).lower():
            raise
        logger.warning("Cannot open DB at %s (%s), using fallback in user profile.", path, e)
        fallback = _fallback_db_path()
        conn = _ensure_dir_and_connect(fallback)
        logger.info("Подключение к БД (fallback): %s", fallback)
        return (conn, fallback)


def update_project_status_on_disk(db_path: str, project_id: int, status_id: int) -> tuple[bool, str]:
    """
    Пишет status_id в файл БД по пути db_path (отдельное подключение, commit, close).
    Подключение без смены journal_mode, чтобы не трогать WAL/checkpoint — только UPDATE и commit.
    Затем открывает файл заново и проверяет запись. Возвращает (успех, путь_к_файлу).
    """
    path = os.path.abspath(os.path.normpath(os.path.expanduser(db_path)))
    # Подключение только для записи, без PRAGMA wal_checkpoint/journal_mode
    conn = sqlite3.connect(path, check_same_thread=False, timeout=15)
    try:
        conn.execute("PRAGMA synchronous=FULL")
        cur = conn.cursor()
        cur.execute("UPDATE projects SET status_id = ? WHERE id = ?", (status_id, project_id))
        conn.commit()
    finally:
        conn.close()
    # Проверка: открыть тот же файл и прочитать
    verify = sqlite3.connect(path, check_same_thread=False, timeout=5)
    try:
        row = verify.execute("SELECT status_id FROM projects WHERE id = ?", (project_id,)).fetchone()
        ok = row is not None and row[0] is not None and int(row[0]) == status_id
        return (ok, path)
    finally:
        verify.close()


def init_schema(conn: sqlite3.Connection) -> None:
    """Создаёт таблицы и индексы, если их ещё нет."""
    c = conn.cursor()
    # Роли
    c.execute('''CREATE TABLE IF NOT EXISTS roles
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT UNIQUE NOT NULL)''')
    # Сотрудники
    c.execute('''CREATE TABLE IF NOT EXISTS employees
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  role_id INTEGER,
                  FOREIGN KEY(role_id) REFERENCES roles(id))''')
    c.execute("CREATE INDEX IF NOT EXISTS idx_employees_role ON employees(role_id)")
    # Отпуска
    c.execute('''CREATE TABLE IF NOT EXISTS vacations
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  employee_id INTEGER NOT NULL,
                  start_date DATE NOT NULL,
                  end_date DATE NOT NULL,
                  FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE)''')
    c.execute("CREATE INDEX IF NOT EXISTS idx_vacations_employee ON vacations(employee_id)")
    # Справочник статусов проектов
    c.execute('''CREATE TABLE IF NOT EXISTS project_statuses
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  code TEXT UNIQUE NOT NULL,
                  name TEXT NOT NULL,
                  is_active BOOLEAN DEFAULT 1,
                  is_gantt_active BOOLEAN DEFAULT 0,
                  is_capacity BOOLEAN DEFAULT 0)''')
    # Проекты
    c.execute('''CREATE TABLE IF NOT EXISTS projects
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  client_company TEXT,
                  lead_id INTEGER,
                  lead_load_percent REAL DEFAULT 50,
                  project_start DATE NOT NULL,
                  project_end DATE NOT NULL,
                  auto_dates BOOLEAN DEFAULT 0,
                  FOREIGN KEY(lead_id) REFERENCES employees(id))''')
    # Рядовые сотрудники проекта
    c.execute('''CREATE TABLE IF NOT EXISTS project_juniors
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  project_id INTEGER NOT NULL,
                  employee_id INTEGER NOT NULL,
                  load_percent REAL DEFAULT 100,
                  FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                  FOREIGN KEY(employee_id) REFERENCES employees(id),
                  UNIQUE(project_id, employee_id))''')
    c.execute("CREATE INDEX IF NOT EXISTS idx_project_juniors_project ON project_juniors(project_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_project_juniors_employee ON project_juniors(employee_id)")
    # Этапы проекта
    c.execute('''CREATE TABLE IF NOT EXISTS project_phases
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  project_id INTEGER NOT NULL,
                  name TEXT NOT NULL,
                  phase_type TEXT NOT NULL CHECK(phase_type IN ('Обычная работа','Командировка')),
                  start_date DATE NOT NULL,
                  end_date DATE NOT NULL,
                  FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE)''')
    c.execute("CREATE INDEX IF NOT EXISTS idx_project_phases_project ON project_phases(project_id)")
    # Назначения на этапы
    c.execute('''CREATE TABLE IF NOT EXISTS phase_assignments
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  phase_id INTEGER NOT NULL,
                  employee_id INTEGER NOT NULL,
                  load_percent REAL NOT NULL,
                  FOREIGN KEY(phase_id) REFERENCES project_phases(id) ON DELETE CASCADE,
                  FOREIGN KEY(employee_id) REFERENCES employees(id))''')
    c.execute("CREATE INDEX IF NOT EXISTS idx_phase_assignments_phase ON phase_assignments(phase_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_phase_assignments_employee ON phase_assignments(employee_id)")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_phase_assignments_unique ON phase_assignments(phase_id, employee_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_projects_dates ON projects(project_start, project_end)")
    conn.commit()


def run_migrations(conn: sqlite3.Connection) -> None:
    """Применяет миграции: новые колонки, конфиг, перенос из старой схемы. Без bare except."""
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS _migrations_done (name TEXT PRIMARY KEY)")
    conn.commit()

    # Миграция: колонки projects
    c.execute("PRAGMA table_info(projects)")
    proj_columns = [col[1] for col in c.fetchall()]
    if 'lead_id' not in proj_columns:
        c.execute("ALTER TABLE projects ADD COLUMN lead_id INTEGER REFERENCES employees(id)")
    if 'lead_load_percent' not in proj_columns:
        c.execute("ALTER TABLE projects ADD COLUMN lead_load_percent REAL DEFAULT 50")
    if 'auto_dates' not in proj_columns:
        c.execute("ALTER TABLE projects ADD COLUMN auto_dates BOOLEAN DEFAULT 0")
    if 'status' not in proj_columns:
        c.execute("ALTER TABLE projects ADD COLUMN status TEXT DEFAULT 'В работе'")
    if 'status_id' not in proj_columns:
        c.execute("ALTER TABLE projects ADD COLUMN status_id INTEGER REFERENCES project_statuses(id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status_id)")
    conn.commit()

    # Миграция: колонка is_capacity в project_statuses
    c.execute("PRAGMA table_info(project_statuses)")
    status_columns = [col[1] for col in c.fetchall()]
    if 'is_capacity' not in status_columns:
        c.execute("ALTER TABLE project_statuses ADD COLUMN is_capacity BOOLEAN DEFAULT 0")
        # Для существующих БД: в расчёте ёмкости участвует только «В работе».
        c.execute("UPDATE project_statuses SET is_capacity = 1 WHERE code = 'in_progress'")
        c.execute("UPDATE project_statuses SET is_capacity = 0 WHERE code <> 'in_progress'")
    conn.commit()

    # Справочник статусов: заполнить по умолчанию, если пусто
    c.execute("SELECT COUNT(*) FROM project_statuses")
    if c.fetchone()[0] == 0:
        for code, name, is_active, is_gantt, is_capacity in [
            ('planned', 'Планируется', 1, 0, 0),
            ('in_progress', 'В работе', 1, 1, 1),
            ('completed', 'Завершён', 0, 0, 0),
            ('cancelled', 'Отменён', 0, 0, 0),
        ]:
            c.execute(
                "INSERT INTO project_statuses (code, name, is_active, is_gantt_active, is_capacity) VALUES (?, ?, ?, ?, ?)",
                (code, name, is_active, is_gantt, is_capacity),
            )
        conn.commit()

    # Миграция: projects.status -> projects.status_id (только один раз, иначе при каждом запуске перезаписывается status_id)
    c.execute("SELECT 1 FROM _migrations_done WHERE name = 'projects_status_to_status_id'")
    if c.fetchone() is None:
        c.execute("PRAGMA table_info(projects)")
        proj_columns = [col[1] for col in c.fetchall()]
        if 'status_id' in proj_columns and 'status' in proj_columns:
            status_rows = c.execute("SELECT id, name FROM project_statuses").fetchall()
            name_to_id = {row[1].strip().lower(): row[0] for row in status_rows}
            # Варианты написания «Планирование» → id статуса «Планируется»
            id_planned = next((r[0] for r in status_rows if (r[1] or '').strip() == 'Планируется'), None)
            if id_planned is not None:
                name_to_id['планирование'] = id_planned
            default_id = name_to_id.get('в работе', next((row[0] for row in status_rows if row[1] == 'В работе'), None))
            if default_id is None and status_rows:
                default_id = status_rows[0][0]
            for row in c.execute("SELECT id, status FROM projects").fetchall():
                proj_id, status_val = row[0], row[1]
                if status_val is None or (isinstance(status_val, str) and not status_val.strip()):
                    sid = default_id
                else:
                    key = str(status_val).strip().lower().replace(' ', '')
                    sid = name_to_id.get(key)
                    if sid is None:
                        for nm, sid_cand in [(r[1], r[0]) for r in status_rows]:
                            if (nm or '').strip().lower().replace(' ', '') == key:
                                sid = sid_cand
                                break
                    if sid is None:
                        sid = default_id
                c.execute("UPDATE projects SET status_id = ? WHERE id = ?", (sid, proj_id))
            conn.commit()
            try:
                c.execute("ALTER TABLE projects DROP COLUMN status")
                conn.commit()
            except sqlite3.OperationalError:
                pass
            c.execute("INSERT OR IGNORE INTO _migrations_done (name) VALUES ('projects_status_to_status_id')")
            conn.commit()

    # Миграция: колонки employees
    c.execute("PRAGMA table_info(employees)")
    emp_columns = [col[1] for col in c.fetchall()]
    if 'department' not in emp_columns:
        c.execute("ALTER TABLE employees ADD COLUMN department TEXT")
    if 'default_load_percent' not in emp_columns:
        c.execute("ALTER TABLE employees ADD COLUMN default_load_percent REAL DEFAULT 100")
    if 'initials' not in emp_columns:
        c.execute("ALTER TABLE employees ADD COLUMN initials TEXT")
    conn.commit()

    # Миграция: completion_percent в project_phases
    c.execute("PRAGMA table_info(project_phases)")
    phase_columns = [col[1] for col in c.fetchall()]
    if 'completion_percent' not in phase_columns:
        c.execute("ALTER TABLE project_phases ADD COLUMN completion_percent INTEGER DEFAULT 0")
    if 'parent_id' not in phase_columns:
        c.execute("ALTER TABLE project_phases ADD COLUMN parent_id INTEGER REFERENCES project_phases(id)")
    conn.commit()

    # Таблица config
    c.execute('''CREATE TABLE IF NOT EXISTS config (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    conn.commit()

    # Значения по умолчанию config
    c.execute("SELECT COUNT(*) FROM config")
    if c.fetchone()[0] == 0:
        defaults = [
            ('annual_working_days', '247'),
            ('annual_vacation_days', '28'),
            ('typical_project_days', '30'),
            ('typical_lead_share', '0.25'),
            ('max_concurrent_projects', '4'),
            ('capacity_role_junior_id', ''),
            ('capacity_role_senior_id', ''),
            ('capacity_role_junior_ids', ''),
            ('capacity_role_senior_ids', ''),
            ('date_placeholder_start', app_config.DATE_PLACEHOLDER_START),
            ('date_placeholder_end', app_config.DATE_PLACEHOLDER_END),
            ('active_statuses', ','.join(app_config.ACTIVE_STATUSES)),
            ('gantt_active_statuses', ','.join(app_config.GANTT_ONLY_ACTIVE_STATUSES)),
        ]
        for k, v in defaults:
            c.execute("INSERT INTO config (key, value) VALUES (?, ?)", (k, v))
        roles = c.execute("SELECT id, name FROM roles").fetchall()
        for rid, rname in roles:
            if rname == 'Junior':
                c.execute("UPDATE config SET value = ? WHERE key = 'capacity_role_junior_id'", (str(rid),))
                c.execute("UPDATE config SET value = ? WHERE key = 'capacity_role_junior_ids'", (str(rid),))
            elif rname == 'Senior':
                c.execute("UPDATE config SET value = ? WHERE key = 'capacity_role_senior_id'", (str(rid),))
                c.execute("UPDATE config SET value = ? WHERE key = 'capacity_role_senior_ids'", (str(rid),))
        conn.commit()

    # Миграция: ключи списков ролей
    for list_key, single_key in [('capacity_role_junior_ids', 'capacity_role_junior_id'), ('capacity_role_senior_ids', 'capacity_role_senior_id')]:
        row = c.execute("SELECT value FROM config WHERE key = ?", (list_key,)).fetchone()
        if row is None:
            single_row = c.execute("SELECT value FROM config WHERE key = ?", (single_key,)).fetchone()
            val = single_row[0] if single_row and single_row[0] and str(single_row[0]).strip() else ''
            c.execute("INSERT INTO config (key, value) VALUES (?, ?)", (list_key, val))
    conn.commit()

    # Миграция: ключи плейсхолдеров дат и статусов (для существующих БД)
    for key, default in [
        ('date_placeholder_start', app_config.DATE_PLACEHOLDER_START),
        ('date_placeholder_end', app_config.DATE_PLACEHOLDER_END),
        ('active_statuses', ','.join(app_config.ACTIVE_STATUSES)),
        ('gantt_active_statuses', ','.join(app_config.GANTT_ONLY_ACTIVE_STATUSES)),
    ]:
        row = c.execute("SELECT 1 FROM config WHERE key = ?", (key,)).fetchone()
        if not row:
            c.execute("INSERT INTO config (key, value) VALUES (?, ?)", (key, default))
    conn.commit()

    # Миграция из старой схемы (если нет проектов в новом формате)
    c.execute("SELECT COUNT(*) FROM projects WHERE lead_id IS NOT NULL")
    if c.fetchone()[0] == 0:
        c.execute("SELECT COUNT(*) FROM roles")
        if c.fetchone()[0] == 0:
            c.execute("INSERT OR IGNORE INTO roles (name) VALUES ('Senior')")
            c.execute("INSERT OR IGNORE INTO roles (name) VALUES ('Junior')")
            conn.commit()

        c.execute("PRAGMA table_info(projects)")
        old_columns = [col[1] for col in c.fetchall()]
        if 'senior_id' in old_columns and 'junior_id' in old_columns:
            old_projects = pd.read_sql("SELECT * FROM projects", conn)
            for _, row in old_projects.iterrows():
                lead_id = row['senior_id'] if pd.notna(row.get('senior_id')) else None
                lead_load = row['senior_load_percent'] if pd.notna(row.get('senior_load_percent')) else 50.0

                placeholder_start = repository.get_config(conn, 'date_placeholder_start', app_config.DATE_PLACEHOLDER_START)
                placeholder_end = repository.get_config(conn, 'date_placeholder_end', app_config.DATE_PLACEHOLDER_END)
                if pd.notna(row.get('project_start')):
                    try:
                        dt = pd.to_datetime(row['project_start']).date()
                        proj_start = dt.isoformat()
                    except (ValueError, TypeError):
                        proj_start = placeholder_start
                else:
                    proj_start = placeholder_start

                if pd.notna(row.get('project_end')):
                    try:
                        dt = pd.to_datetime(row['project_end']).date()
                        proj_end = dt.isoformat()
                    except (ValueError, TypeError):
                        proj_end = placeholder_end
                else:
                    proj_end = placeholder_end

                client_company = row.get('client_company') if pd.notna(row.get('client_company')) else ""
                auto_dates = row.get('auto_dates', 0) or 0

                c.execute("""
                    INSERT OR IGNORE INTO projects (id, name, client_company, lead_id, lead_load_percent, project_start, project_end, auto_dates)
                    VALUES (?,?,?,?,?,?,?,?)
                """, (row['id'], row['name'], client_company, lead_id, lead_load, proj_start, proj_end, auto_dates))

                if pd.notna(row.get('junior_id')):
                    junior_load = row.get('junior_load_percent', 100.0) if pd.notna(row.get('junior_load_percent')) else 100.0
                    existing = c.execute(
                        "SELECT 1 FROM project_juniors WHERE project_id=? AND employee_id=?",
                        (row['id'], row['junior_id'])
                    ).fetchone()
                    if not existing:
                        c.execute("""
                            INSERT INTO project_juniors (project_id, employee_id, load_percent)
                            VALUES (?,?,?)
                        """, (row['id'], row['junior_id'], junior_load))
            conn.commit()

            try:
                c.execute("ALTER TABLE projects DROP COLUMN senior_id")
                c.execute("ALTER TABLE projects DROP COLUMN junior_id")
                c.execute("ALTER TABLE projects DROP COLUMN senior_load_percent")
                c.execute("ALTER TABLE projects DROP COLUMN junior_load_percent")
                conn.commit()
            except sqlite3.OperationalError:
                pass

        # business_trips
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='business_trips'")
        if c.fetchone():
            c.execute("""INSERT INTO project_phases (project_id, name, phase_type, start_date, end_date, completion_percent)
                         SELECT project_id, 'Командировка', 'Командировка', trip_start, trip_end, 0 FROM business_trips""")
            c.execute("DROP TABLE business_trips")
            conn.commit()

        # vacation_start/vacation_end в employees
        c.execute("PRAGMA table_info(employees)")
        emp_columns = [col[1] for col in c.fetchall()]
        if 'vacation_start' in emp_columns or 'vacation_end' in emp_columns:
            df_emp_old = pd.read_sql(
                "SELECT id, vacation_start, vacation_end FROM employees WHERE vacation_start IS NOT NULL AND vacation_end IS NOT NULL",
                conn
            )
            for _, row in df_emp_old.iterrows():
                try:
                    start_str = pd.to_datetime(row['vacation_start']).date().isoformat()
                    end_str = pd.to_datetime(row['vacation_end']).date().isoformat()
                except (ValueError, TypeError):
                    continue
                c.execute("INSERT INTO vacations (employee_id, start_date, end_date) VALUES (?,?,?)",
                          (row['id'], start_str, end_str))
            try:
                c.execute("ALTER TABLE employees DROP COLUMN vacation_start")
                c.execute("ALTER TABLE employees DROP COLUMN vacation_end")
                conn.commit()
            except sqlite3.OperationalError:
                pass

    conn.commit()
