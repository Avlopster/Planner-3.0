# -*- coding: utf-8 -*-
"""Репозиторий: CRUD, загрузка данных из БД, конфиг. Все функции принимают conn."""
import sqlite3
from datetime import date
from typing import Any, List, Optional, Tuple

import pandas as pd

import config as app_config
from utils.app_logging import get_db_logger, record_error
from utils.type_utils import safe_date_series, safe_int

# Для обратной совместимости (app_pages могут импортировать _safe_int)
_safe_int = safe_int


def load_roles(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql("SELECT * FROM roles", conn)


def load_employees(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql("SELECT employees.*, roles.name as role_name FROM employees LEFT JOIN roles ON employees.role_id = roles.id", conn)
    df['role_name'] = df['role_name'].fillna('Без роли')
    if not df.empty:
        for col in ('id', 'role_id'):
            if col in df.columns:
                df[col] = df[col].apply(lambda x: safe_int(x))
    return df


def load_vacations(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql("SELECT * FROM vacations", conn)
    if not df.empty:
        df['start_date'] = safe_date_series(df['start_date'])
        df['end_date'] = safe_date_series(df['end_date'])
        if 'employee_id' in df.columns:
            df['employee_id'] = df['employee_id'].apply(lambda x: safe_int(x))
    return df


def load_project_statuses(conn: sqlite3.Connection) -> pd.DataFrame:
    """Справочник статусов проектов: id, code, name, is_active, is_gantt_active, is_capacity."""
    try:
        df = pd.read_sql(
            "SELECT id, code, name, is_active, is_gantt_active, is_capacity FROM project_statuses ORDER BY id",
            conn,
        )
    except sqlite3.OperationalError:
        # Для старых БД без колонки is_capacity.
        df = pd.read_sql("SELECT id, code, name, is_active, is_gantt_active FROM project_statuses ORDER BY id", conn)
        if 'is_capacity' not in df.columns:
            df['is_capacity'] = False
    if not df.empty:
        for col in ('id',):
            if col in df.columns:
                df[col] = df[col].apply(lambda x: safe_int(x))
        if 'is_active' in df.columns:
            df['is_active'] = df['is_active'].astype(bool)
        if 'is_gantt_active' in df.columns:
            df['is_gantt_active'] = df['is_gantt_active'].astype(bool)
        if 'is_capacity' in df.columns:
            df['is_capacity'] = df['is_capacity'].astype(bool)
    return df


def get_status_id_by_code(conn: sqlite3.Connection, code: str) -> Optional[int]:
    row = conn.cursor().execute("SELECT id FROM project_statuses WHERE code = ?", (code,)).fetchone()
    return safe_int(row[0]) if row else None


def get_status_name(conn: sqlite3.Connection, status_id: Optional[int]) -> str:
    if status_id is None or pd.isna(status_id):
        default_id = get_status_id_by_code(conn, 'in_progress')
        if default_id is not None:
            row = conn.cursor().execute("SELECT name FROM project_statuses WHERE id = ?", (default_id,)).fetchone()
            return row[0] if row else 'В работе'
        return 'В работе'
    row = conn.cursor().execute("SELECT name FROM project_statuses WHERE id = ?", (int(status_id),)).fetchone()
    return row[0] if row else 'В работе'


def get_project_status_id(conn: sqlite3.Connection, project_id: int) -> Optional[int]:
    """Возвращает текущий status_id проекта или None."""
    row = conn.cursor().execute("SELECT status_id FROM projects WHERE id = ?", (project_id,)).fetchone()
    return safe_int(row[0]) if row and row[0] is not None else None


def update_project_status(conn: sqlite3.Connection, project_id: int, status_id: int) -> bool:
    """Обновляет status_id проекта. Делает commit. Возвращает True, если запись прошла (проверка тем же conn)."""
    cur = conn.cursor()
    cur.execute("UPDATE projects SET status_id = ? WHERE id = ?", (status_id, project_id))
    conn.commit()
    row = cur.execute("SELECT status_id FROM projects WHERE id = ?", (project_id,)).fetchone()
    return row is not None and safe_int(row[0]) == status_id


def load_projects(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql(
        """SELECT p.*, ps.name as status_name, ps.code as status_code
           FROM projects p
           LEFT JOIN project_statuses ps ON p.status_id = ps.id""",
        conn,
    )
    if not df.empty:
        for col in ('id', 'lead_id', 'status_id'):
            if col in df.columns:
                df[col] = df[col].apply(lambda x: safe_int(x))
        if 'project_start' in df.columns:
            df['project_start'] = safe_date_series(df['project_start'])
        if 'project_end' in df.columns:
            df['project_end'] = safe_date_series(df['project_end'])
        if 'status_name' in df.columns:
            df['status_name'] = df['status_name'].fillna('Не указан')
        if 'status_code' in df.columns:
            df['status_code'] = df['status_code'].fillna('')
    return df


# Порядок статусов для отображения: В работе → Планируется → Завершён → Отменён
STATUS_DISPLAY_ORDER = ('in_progress', 'planned', 'completed', 'cancelled')


def sort_projects_by_status(df: pd.DataFrame) -> pd.DataFrame:
    """Сортирует DataFrame проектов по статусу: В работе, Планируется, Завершён, Отменён; остальные в конце по id."""
    if df.empty or 'status_code' not in df.columns:
        return df
    order_map = {code: i for i, code in enumerate(STATUS_DISPLAY_ORDER)}
    df = df.copy()
    df['_sort_key'] = df['status_code'].map(lambda c: order_map.get(c, 99))
    if 'id' in df.columns:
        df = df.sort_values(by=['_sort_key', 'id']).drop(columns=['_sort_key'])
    else:
        df = df.sort_values(by='_sort_key').drop(columns=['_sort_key'])
    return df.reset_index(drop=True)


def load_project_juniors(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql("SELECT * FROM project_juniors", conn)
    if not df.empty:
        for col in ('id', 'project_id', 'employee_id'):
            if col in df.columns:
                df[col] = df[col].apply(lambda x: safe_int(x))
    return df


def load_phases(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql("SELECT * FROM project_phases", conn)
    if not df.empty:
        df['start_date'] = safe_date_series(df['start_date'])
        df['end_date'] = safe_date_series(df['end_date'])
        if 'project_id' in df.columns:
            df['project_id'] = df['project_id'].apply(lambda x: safe_int(x))
        if 'completion_percent' in df.columns:
            df['completion_percent'] = df['completion_percent'].apply(lambda x: safe_int(x) if pd.notna(x) else 0)
        if 'parent_id' in df.columns:
            df['parent_id'] = df['parent_id'].apply(lambda x: safe_int(x) if pd.notna(x) and x is not None else None)
    return df


def phases_tree_order(proj_phases: pd.DataFrame) -> List[Tuple[pd.Series, int]]:
    """
    Возвращает список (phase_row, depth) в порядке обхода дерева сверху вниз (родитель → дети).
    depth=0 — верхний уровень, depth=1 — подэтап и т.д. Если parent_id нет или все пустые — все этапы с depth=0.
    """
    if proj_phases.empty:
        return []
    if "parent_id" not in proj_phases.columns or proj_phases["parent_id"].notna().sum() == 0:
        return [(row, 0) for _, row in proj_phases.sort_values("id").iterrows()]
    children_map: dict = {}
    for _, row in proj_phases.iterrows():
        pid = row.get("parent_id")
        if pid is not None and pd.notna(pid):
            pid = int(pid)
            children_map.setdefault(pid, []).append(int(row["id"]))
    for pid in children_map:
        children_map[pid].sort()
    by_id = proj_phases.set_index("id", drop=False)
    roots = proj_phases[proj_phases["parent_id"].isna()]["id"].tolist()
    roots.sort()
    result: List[Tuple[pd.Series, int]] = []

    def dfs(phase_id: int, depth: int) -> None:
        if phase_id not in by_id.index:
            return
        result.append((by_id.loc[phase_id], depth))
        for cid in children_map.get(phase_id, []):
            dfs(cid, depth + 1)

    for rid in roots:
        dfs(int(rid), 0)
    return result


def load_phase_assignments(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql("SELECT * FROM phase_assignments", conn)
    if not df.empty:
        for col in ('id', 'phase_id', 'employee_id'):
            if col in df.columns:
                df[col] = df[col].apply(lambda x: safe_int(x))
    return df


def get_employee_name(conn: sqlite3.Connection, emp_id: int) -> str:
    """Возвращает имя сотрудника по id (один запрос по БД)."""
    if conn is None or emp_id is None:
        return "Не найден"
    try:
        eid = int(emp_id)
    except (TypeError, ValueError):
        return "Не найден"
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM employees WHERE id = ?", (eid,))
        row = cur.fetchone()
        cur.close()
        return row[0] if row and row[0] else "Не найден"
    except (sqlite3.InterfaceError, sqlite3.ProgrammingError, sqlite3.OperationalError, sqlite3.Error, OSError, AttributeError):
        return "Не найден"


def get_project_name(conn: sqlite3.Connection, proj_id: int) -> str:
    """Возвращает название проекта по id (один запрос по БД)."""
    if conn is None or proj_id is None:
        return "Не найден"
    try:
        pid = int(proj_id)
    except (TypeError, ValueError):
        return "Не найден"
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM projects WHERE id = ?", (pid,))
        row = cur.fetchone()
        cur.close()
        return row[0] if row and row[0] else "Не найден"
    except (sqlite3.InterfaceError, sqlite3.ProgrammingError, sqlite3.OperationalError, sqlite3.Error, OSError, AttributeError):
        return "Не найден"


def get_employee_vacations(conn: sqlite3.Connection, emp_id: int) -> pd.DataFrame:
    df = load_vacations(conn)
    return df[df['employee_id'] == emp_id]


def check_vacation_overlap(conn: sqlite3.Connection, emp_id: int, start_date, end_date, exclude_vacation_id: Optional[int] = None) -> Tuple[bool, Optional[dict]]:
    vacs = get_employee_vacations(conn, emp_id)
    if isinstance(start_date, str):
        start_date = pd.to_datetime(start_date).date()
    elif hasattr(start_date, 'date'):
        start_date = start_date.date()
    if isinstance(end_date, str):
        end_date = pd.to_datetime(end_date).date()
    elif hasattr(end_date, 'date'):
        end_date = end_date.date()
    for _, vac in vacs.iterrows():
        if exclude_vacation_id is not None and vac['id'] == exclude_vacation_id:
            continue
        vac_start = vac['start_date']
        vac_end = vac['end_date']
        if hasattr(vac_start, 'date'):
            vac_start = vac_start.date() if isinstance(vac_start, pd.Timestamp) else vac_start
        if hasattr(vac_end, 'date'):
            vac_end = vac_end.date() if isinstance(vac_end, pd.Timestamp) else vac_end
        if start_date <= vac_end and end_date >= vac_start:
            return True, {'id': vac['id'], 'start_date': vac_start, 'end_date': vac_end}
    return False, None


def insert_project(
    conn: sqlite3.Connection,
    name: str,
    client_company: str,
    lead_id: Optional[int],
    lead_load_percent: float,
    project_start: str,
    project_end: str,
    auto_dates: bool,
    status_id: int,
) -> int:
    """Создаёт проект и возвращает его id (lastrowid). Делает commit."""
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO projects
           (name, client_company, lead_id, lead_load_percent, project_start, project_end, auto_dates, status_id)
           VALUES (?,?,?,?,?,?,?,?)""",
        (name, client_company, lead_id, lead_load_percent, project_start, project_end, auto_dates, status_id),
    )
    conn.commit()
    return cur.lastrowid


def add_project_juniors(
    conn: sqlite3.Connection,
    project_id: int,
    juniors: List[Tuple[int, float]],
) -> None:
    """Добавляет рядовых сотрудников к проекту. juniors — список (employee_id, load_percent). Делает commit."""
    cur = conn.cursor()
    for (employee_id, load_percent) in juniors:
        cur.execute(
            "INSERT INTO project_juniors (project_id, employee_id, load_percent) VALUES (?,?,?)",
            (project_id, employee_id, load_percent),
        )
    conn.commit()


def update_project(
    conn: sqlite3.Connection,
    project_id: int,
    name: str,
    client_company: str,
    lead_id: Optional[int],
    lead_load_percent: float,
    project_start: str,
    project_end: str,
    auto_dates: bool,
    status_id: int,
) -> None:
    """Обновляет запись проекта. Делает commit."""
    cur = conn.cursor()
    cur.execute(
        """UPDATE projects SET
           name=?, client_company=?, lead_id=?, lead_load_percent=?,
           project_start=?, project_end=?, auto_dates=?, status_id=?
           WHERE id=?""",
        (name, client_company, lead_id, lead_load_percent, project_start, project_end, auto_dates, status_id, project_id),
    )
    conn.commit()


def delete_project(conn: sqlite3.Connection, project_id: int) -> None:
    conn.cursor().execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()


def delete_employee(conn: sqlite3.Connection, employee_id: int) -> Tuple[bool, Optional[str]]:
    projs = load_projects(conn)
    juniors = load_project_juniors(conn)
    if not projs[projs['lead_id'] == employee_id].empty or not juniors[juniors['employee_id'] == employee_id].empty:
        return False, "Нельзя удалить сотрудника, который назначен на проекты или этапы. Сначала переназначьте проекты."
    conn.cursor().execute("DELETE FROM employees WHERE id = ?", (employee_id,))
    conn.commit()
    return True, None


def delete_vacation(conn: sqlite3.Connection, vacation_id: int) -> None:
    conn.cursor().execute("DELETE FROM vacations WHERE id = ?", (vacation_id,))
    conn.commit()


def delete_role(conn: sqlite3.Connection, role_id: int) -> Tuple[bool, Optional[str]]:
    employees = load_employees(conn)
    if not employees[employees['role_id'] == role_id].empty:
        return False, "Нельзя удалить роль, назначенную сотрудникам. Сначала переназначьте им другие роли."
    conn.cursor().execute("DELETE FROM roles WHERE id = ?", (role_id,))
    conn.commit()
    return True, None


def _date_to_str(val) -> str:
    """Приводит дату к строке YYYY-MM-DD для записи в БД."""
    if val is None:
        return ""
    if hasattr(val, "isoformat") and callable(getattr(val, "isoformat")):
        return val.isoformat()[:10]
    return str(val)[:10]


def update_parent_phase_dates_from_children(conn: sqlite3.Connection, project_id: int) -> None:
    """
    Пересчитывает даты родительских этапов снизу вверх: start_date = min(даты дочерних),
    end_date = max(даты дочерних). Обрабатывает этапы от листьев к корню. Делает commit.
    """
    phases = load_phases(conn)
    proj_phases = phases[phases["project_id"] == project_id].copy()
    if proj_phases.empty or "parent_id" not in proj_phases.columns:
        return
    proj_phases["start_date"] = pd.to_datetime(proj_phases["start_date"], errors="coerce")
    proj_phases["end_date"] = pd.to_datetime(proj_phases["end_date"], errors="coerce")
    children_map: dict = {}
    for _, row in proj_phases.iterrows():
        pid = row.get("parent_id")
        if pid is not None and pd.notna(pid):
            children_map.setdefault(int(pid), []).append(int(row["id"]))

    def depth(phase_id: int) -> int:
        kids = children_map.get(phase_id)
        if not kids:
            return 0
        return 1 + max(depth(kid) for kid in kids)

    phase_ids_by_depth = sorted(proj_phases["id"].tolist(), key=lambda pid: depth(int(pid)))
    cur = conn.cursor()
    by_id = proj_phases.set_index("id", drop=False)
    for phase_id in phase_ids_by_depth:
        kids = children_map.get(phase_id)
        if not kids:
            continue
        valid = [by_id.loc[kid] for kid in kids if kid in by_id.index]
        if not valid:
            continue
        starts = [r["start_date"] for r in valid if pd.notna(r.get("start_date"))]
        ends = [r["end_date"] for r in valid if pd.notna(r.get("end_date"))]
        if not starts or not ends:
            continue
        start = min(starts)
        end = max(ends)
        start_s = _date_to_str(start)
        end_s = _date_to_str(end)
        cur.execute(
            "UPDATE project_phases SET start_date = ?, end_date = ? WHERE id = ?",
            (start_s, end_s, phase_id),
        )
        by_id.loc[phase_id, "start_date"] = start
        by_id.loc[phase_id, "end_date"] = end
    conn.commit()


def update_project_dates_from_phases(conn: sqlite3.Connection, project_id: int) -> bool:
    """
    Пересчитывает даты проекта по этапам: сначала обновляет даты родительских этапов
    из подэтапов (снизу вверх), затем задаёт даты проекта по верхнеуровневым этапам
    (parent_id IS NULL): project_start = min(start), project_end = max(end).
    """
    update_parent_phase_dates_from_children(conn, project_id)
    phases = load_phases(conn)
    proj_phases = phases[phases["project_id"] == project_id]
    if "parent_id" in proj_phases.columns:
        top_level = proj_phases[proj_phases["parent_id"].isna()]
        if not top_level.empty:
            proj_phases = top_level
    if not proj_phases.empty:
        start = proj_phases["start_date"].min()
        end = proj_phases["end_date"].max()
        start_s = _date_to_str(start)
        end_s = _date_to_str(end)
        if start_s and end_s:
            conn.cursor().execute(
                "UPDATE projects SET project_start = ?, project_end = ? WHERE id = ?",
                (start_s, end_s, project_id),
            )
            conn.commit()
            return True
    return False


def delete_phase(conn: sqlite3.Connection, phase_id: int) -> None:
    """Удаляет этап по id. Делает commit."""
    cur = conn.cursor()
    cur.execute("DELETE FROM project_phases WHERE id = ?", (phase_id,))
    conn.commit()


def insert_phase(
    conn: sqlite3.Connection,
    project_id: int,
    name: str,
    phase_type: str,
    start_date: str,
    end_date: str,
    completion_percent: int,
    parent_id: Optional[int] = None,
) -> Optional[int]:
    """Добавляет этап к проекту. Делает commit. Возвращает id вставленного этапа (lastrowid)."""
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO project_phases (project_id, name, phase_type, start_date, end_date, completion_percent, parent_id)
           VALUES (?,?,?,?,?,?,?)""",
        (project_id, name, phase_type, start_date, end_date, completion_percent, parent_id),
    )
    conn.commit()
    return cur.lastrowid


def update_phase(
    conn: sqlite3.Connection,
    phase_id: int,
    name: str,
    phase_type: str,
    start_date: str,
    end_date: str,
    completion_percent: int,
    assignments: Optional[List[Tuple[int, float]]] = None,
    parent_id: Optional[int] = None,
) -> None:
    """Обновляет этап и его назначения. assignments — список (employee_id, load_percent); если None или пусто — все назначения удаляются. parent_id — родительский этап (None не меняет). Делает commit."""
    cur = conn.cursor()
    if parent_id is not None:
        cur.execute(
            """UPDATE project_phases SET
               name=?, phase_type=?, start_date=?, end_date=?, completion_percent=?, parent_id=?
               WHERE id=?""",
            (name, phase_type, start_date, end_date, completion_percent, parent_id, phase_id),
        )
    else:
        cur.execute(
            """UPDATE project_phases SET
               name=?, phase_type=?, start_date=?, end_date=?, completion_percent=?
               WHERE id=?""",
            (name, phase_type, start_date, end_date, completion_percent, phase_id),
        )
    cur.execute("DELETE FROM phase_assignments WHERE phase_id = ?", (phase_id,))
    if assignments:
        for (employee_id, load_percent) in assignments:
            cur.execute(
                "INSERT OR IGNORE INTO phase_assignments (phase_id, employee_id, load_percent) VALUES (?,?,?)",
                (phase_id, employee_id, load_percent),
            )
    conn.commit()


def get_config(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    row = conn.cursor().execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_config(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.cursor().execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()


def _config_status_list(conn: sqlite3.Connection, key: str, default_tuple: tuple) -> Tuple[str, ...]:
    """Читает из config ключ key как строку статусов через запятую; возвращает кортеж непустых строк (fallback)."""
    v = get_config(conn, key)
    if v is None or (isinstance(v, str) and not v.strip()):
        return default_tuple
    parts = [s.strip() for s in str(v).split(',') if s.strip()]
    return tuple(parts) if parts else default_tuple


def get_active_statuses(conn: sqlite3.Connection) -> Tuple[str, ...]:
    """Статусы проектов «активные» (для отчётов, годовой ёмкости). Из справочника project_statuses."""
    try:
        rows = conn.cursor().execute(
            "SELECT name FROM project_statuses WHERE is_active = 1 ORDER BY id"
        ).fetchall()
        if rows:
            return tuple(r[0] for r in rows)
    except sqlite3.OperationalError as e:
        record_error(e, user_message="Ошибка доступа к справочнику статусов проектов (активные).")
        get_db_logger().debug("get_active_statuses: %s", e)
    return _config_status_list(conn, 'active_statuses', app_config.ACTIVE_STATUSES)


def get_capacity_statuses(conn: sqlite3.Connection) -> Tuple[str, ...]:
    """Статусы проектов для расчёта годовой ёмкости. Из справочника project_statuses."""
    try:
        rows = conn.cursor().execute(
            "SELECT name FROM project_statuses WHERE is_capacity = 1 ORDER BY id"
        ).fetchall()
        if rows:
            return tuple(r[0] for r in rows)
    except sqlite3.OperationalError as e:
        record_error(e, user_message="Ошибка доступа к справочнику статусов проектов (ёмкость).")
        get_db_logger().debug("get_capacity_statuses: %s", e)
    # Обратная совместимость: для старых БД используем активные статусы.
    return get_active_statuses(conn)


def get_gantt_active_statuses(conn: sqlite3.Connection) -> Tuple[str, ...]:
    """Статусы для фильтра Ганта «Только активные». Из справочника project_statuses."""
    try:
        rows = conn.cursor().execute(
            "SELECT name FROM project_statuses WHERE is_gantt_active = 1 ORDER BY id"
        ).fetchall()
        if rows:
            return tuple(r[0] for r in rows)
    except sqlite3.OperationalError as e:
        record_error(e, user_message="Ошибка доступа к справочнику статусов проектов (Гантт).")
        get_db_logger().debug("get_gantt_active_statuses: %s", e)
    return _config_status_list(conn, 'gantt_active_statuses', app_config.GANTT_ONLY_ACTIVE_STATUSES)


def update_project_status_flags(
    conn: sqlite3.Connection,
    status_id: int,
    is_active: bool,
    is_gantt_active: bool,
    is_capacity: bool,
) -> None:
    """Обновляет флаги is_active, is_gantt_active и is_capacity для статуса в справочнике."""
    conn.cursor().execute(
        "UPDATE project_statuses SET is_active = ?, is_gantt_active = ?, is_capacity = ? WHERE id = ?",
        (1 if is_active else 0, 1 if is_gantt_active else 0, 1 if is_capacity else 0, status_id),
    )
    conn.commit()


def get_date_placeholders(conn: sqlite3.Connection) -> Tuple[str, str]:
    """Возвращает (date_placeholder_start, date_placeholder_end) для импорта/невалидных дат."""
    start = get_config(conn, 'date_placeholder_start')
    end = get_config(conn, 'date_placeholder_end')
    start = start if start and str(start).strip() else app_config.DATE_PLACEHOLDER_START
    end = end if end and str(end).strip() else app_config.DATE_PLACEHOLDER_END
    return (str(start).strip(), str(end).strip())


def load_capacity_config(conn: sqlite3.Connection) -> dict:
    def _int(k, default):
        v = get_config(conn, k)
        if v is None or (isinstance(v, str) and v.strip() == ''):
            return default
        try:
            return int(float(v))
        except (ValueError, TypeError):
            return default

    def _float(k, default):
        v = get_config(conn, k)
        if v is None or (isinstance(v, str) and v.strip() == ''):
            return default
        try:
            return float(v)
        except (ValueError, TypeError):
            return default

    def _role_id_list(k):
        v = get_config(conn, k)
        if v is None or (isinstance(v, str) and v.strip() == ''):
            return []
        out = []
        for part in str(v).split(','):
            part = part.strip()
            if not part:
                continue
            try:
                out.append(int(float(part)))
            except (ValueError, TypeError):
                pass
        return out

    def _role_id(k):
        v = get_config(conn, k)
        if v is None or (isinstance(v, str) and v.strip() == ''):
            return None
        try:
            return int(float(v))
        except (ValueError, TypeError):
            return None

    junior_ids = _role_id_list('capacity_role_junior_ids')
    if not junior_ids and _role_id('capacity_role_junior_id') is not None:
        junior_ids = [_role_id('capacity_role_junior_id')]
    senior_ids = _role_id_list('capacity_role_senior_ids')
    if not senior_ids and _role_id('capacity_role_senior_id') is not None:
        senior_ids = [_role_id('capacity_role_senior_id')]

    return {
        'annual_working_days': _int('annual_working_days', app_config.ANNUAL_WORKING_DAYS_DEFAULT),
        'typical_project_days': _int('typical_project_days', app_config.TYPICAL_PROJECT_DAYS_DEFAULT),
        'typical_lead_share': _float('typical_lead_share', app_config.TYPICAL_LEAD_SHARE_DEFAULT),
        'max_concurrent_projects': _int('max_concurrent_projects', app_config.MAX_CONCURRENT_PROJECTS_DEFAULT),
        'capacity_role_junior_ids': junior_ids,
        'capacity_role_senior_ids': senior_ids,
    }


def gantt_project_completion_percent(project_id: int, display_date, phases_df: pd.DataFrame) -> float:
    """Доля выполнения проекта по этапам (0.0–1.0). Использует completion_percent или дату."""
    if phases_df.empty:
        return 0.0
    proj_phases = phases_df[phases_df['project_id'] == project_id]
    if proj_phases.empty:
        return 0.0
    total_duration_days = 0
    completed_days = 0
    use_manual_percent = 'completion_percent' in proj_phases.columns
    for _, ph in proj_phases.iterrows():
        start_d = pd.to_datetime(ph['start_date']).date() if ph.get('start_date') else None
        end_d = pd.to_datetime(ph['end_date']).date() if ph.get('end_date') else None
        if start_d is None or end_d is None:
            continue
        d_phase = max(0, (end_d - start_d).days)
        total_duration_days += d_phase
        if use_manual_percent and ph.get('completion_percent') is not None:
            pct = safe_int(ph.get('completion_percent'), 0) or 0
            pct = min(100, max(0, pct))
            completed_days += d_phase * (pct / 100.0)
        else:
            d = display_date.date() if hasattr(display_date, 'date') else display_date
            if d >= end_d:
                completed_days += d_phase
            elif start_d <= d < end_d:
                completed_days += (d - start_d).days
    if total_duration_days <= 0:
        return 0.0
    return min(1.0, max(0.0, completed_days / total_duration_days))
