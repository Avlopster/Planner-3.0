# -*- coding: utf-8 -*-
"""Функции импорта из Excel для UI: шаблоны и импорт по сущностям (принимают conn)."""
import io
import sqlite3
from datetime import datetime
from typing import Callable, Optional, Tuple

import pandas as pd

import repository
from excel_import import import_phases_core, import_phase_assignments_core


def download_template(table_name: str) -> io.BytesIO:
    """Возвращает BytesIO с xlsx-шаблоном для указанной сущности."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        if table_name == 'employees':
            df = pd.DataFrame(columns=['ФИО', 'Роль', 'Отдел', 'Ставка %'])
            df.to_excel(writer, sheet_name='Сотрудники', index=False)
        elif table_name == 'vacations':
            df = pd.DataFrame(columns=['Сотрудник', 'Дата начала', 'Дата окончания'])
            df.to_excel(writer, sheet_name='Отпуска', index=False)
        elif table_name == 'projects':
            df = pd.DataFrame(columns=[
                'Название проекта', 'Компания клиента',
                'Ведущий', 'Загрузка ведущего %',
                'Дата начала', 'Дата окончания',
                'Автоопределение дат'
            ])
            df.to_excel(writer, sheet_name='Проекты', index=False)
        elif table_name == 'juniors':
            df = pd.DataFrame(columns=['Проект', 'Сотрудник', 'Загрузка %'])
            df.to_excel(writer, sheet_name='Рядовые', index=False)
        elif table_name == 'phases':
            df = pd.DataFrame(columns=['Проект', 'Название этапа', 'Тип этапа', 'Дата начала', 'Дата окончания'])
            df.to_excel(writer, sheet_name='Этапы', index=False)
        elif table_name == 'phase_assignments':
            df = pd.DataFrame(columns=['Проект', 'Название этапа', 'Сотрудник', 'Загрузка %'])
            df.to_excel(writer, sheet_name='Назначения на этапы', index=False)
    output.seek(0)
    return output


def import_employees(conn: sqlite3.Connection, df: pd.DataFrame) -> Tuple[int, list]:
    """Импорт сотрудников из DataFrame. Возвращает (success_count, list_of_errors)."""
    roles_df = repository.load_roles(conn)
    cur = conn.cursor()
    success = 0
    errors = []
    for idx, row in df.iterrows():
        name = str(row['ФИО']).strip()
        role_name = str(row['Роль']).strip()
        department = str(row.get('Отдел', '')).strip() if pd.notna(row.get('Отдел')) else ''
        default_load = float(row.get('Ставка %', 100)) if pd.notna(row.get('Ставка %')) else 100.0
        if not name or not role_name:
            errors.append(f"Строка {idx+2}: пустое имя или роль")
            continue
        role_id = None
        role_row = roles_df[roles_df['name'] == role_name]
        if not role_row.empty:
            role_id = role_row.iloc[0]['id']
        else:
            try:
                cur.execute("INSERT INTO roles (name) VALUES (?)", (role_name,))
                conn.commit()
                role_id = cur.lastrowid
                new_role = pd.DataFrame([{'id': role_id, 'name': role_name}])
                roles_df = pd.concat([roles_df, new_role], ignore_index=True)
            except sqlite3.IntegrityError:
                errors.append(f"Строка {idx+2}: роль '{role_name}' уже существует, но не найдена в справочнике")
                continue
        cur.execute("INSERT INTO employees (name, role_id, department, default_load_percent) VALUES (?,?,?,?)",
                   (name, role_id, department or None, default_load))
        conn.commit()
        success += 1
    return success, errors


def import_vacations(conn: sqlite3.Connection, df: pd.DataFrame) -> Tuple[int, list]:
    employees_df = repository.load_employees(conn)
    cur = conn.cursor()
    success = 0
    errors = []
    for idx, row in df.iterrows():
        emp_name = str(row['Сотрудник']).strip()
        start = row['Дата начала']
        end = row['Дата окончания']
        try:
            if isinstance(start, str):
                start = datetime.strptime(start, "%d.%m.%Y").date()
            else:
                start = pd.to_datetime(start).date()
            if isinstance(end, str):
                end = datetime.strptime(end, "%d.%m.%Y").date()
            else:
                end = pd.to_datetime(end).date()
        except Exception as e:
            errors.append(f"Строка {idx+2}: неверный формат даты ({e})")
            continue
        if start > end:
            errors.append(f"Строка {idx+2}: дата начала позже даты окончания")
            continue
        emp_row = employees_df[employees_df['name'] == emp_name]
        if emp_row.empty:
            errors.append(f"Строка {idx+2}: сотрудник '{emp_name}' не найден")
            continue
        emp_id = emp_row.iloc[0]['id']

        has_overlap, conflicting = repository.check_vacation_overlap(conn, emp_id, start, end)
        if has_overlap:
            conf = conflicting
            conf_start = conf['start_date'].strftime("%d.%m.%Y") if hasattr(conf['start_date'], 'strftime') else str(conf['start_date'])
            conf_end = conf['end_date'].strftime("%d.%m.%Y") if hasattr(conf['end_date'], 'strftime') else str(conf['end_date'])
            errors.append(f"Строка {idx+2}: период отпуска пересекается с существующим отпуском сотрудника '{emp_name}' ({conf_start} — {conf_end})")
            continue

        cur.execute("INSERT INTO vacations (employee_id, start_date, end_date) VALUES (?,?,?)",
                   (emp_id, start.isoformat(), end.isoformat()))
        conn.commit()
        success += 1
    return success, errors


def import_projects(conn: sqlite3.Connection, df: pd.DataFrame) -> Tuple[int, list]:
    employees_df = repository.load_employees(conn)
    cur = conn.cursor()
    success = 0
    errors = []
    for idx, row in df.iterrows():
        name = str(row['Название проекта']).strip()
        client = str(row['Компания клиента']).strip() if pd.notna(row.get('Компания клиента')) else ""
        lead_name = str(row['Ведущий']).strip()
        lead_load = float(row['Загрузка ведущего %']) if pd.notna(row.get('Загрузка ведущего %')) else 50.0
        auto_dates = row.get('Автоопределение дат')
        if isinstance(auto_dates, str):
            auto_dates = auto_dates.lower() in ['да', 'yes', 'true', '1', 'включено']
        else:
            auto_dates = bool(auto_dates)

        if not auto_dates:
            try:
                if pd.isna(row.get('Дата начала')) or pd.isna(row.get('Дата окончания')):
                    errors.append(f"Строка {idx+2}: при выключенном автоопределении даты начала и окончания обязательны")
                    continue
                start = row['Дата начала']
                end = row['Дата окончания']
                if isinstance(start, str):
                    start = datetime.strptime(start, "%d.%m.%Y").date()
                else:
                    start = pd.to_datetime(start).date()
                if isinstance(end, str):
                    end = datetime.strptime(end, "%d.%m.%Y").date()
                else:
                    end = pd.to_datetime(end).date()
                start_str = start.isoformat()
                end_str = end.isoformat()
            except Exception as e:
                errors.append(f"Строка {idx+2}: неверный формат даты ({e})")
                continue
        else:
            start_str, end_str = repository.get_date_placeholders(conn)

        lead_row = employees_df[employees_df['name'] == lead_name]
        if lead_row.empty:
            errors.append(f"Строка {idx+2}: ведущий '{lead_name}' не найден")
            continue
        lead_id = lead_row.iloc[0]['id']

        cur.execute("""
            INSERT INTO projects
            (name, client_company, lead_id, lead_load_percent, project_start, project_end, auto_dates)
            VALUES (?,?,?,?,?,?,?)
        """, (name, client, lead_id, lead_load, start_str, end_str, auto_dates))
        conn.commit()
        success += 1
    return success, errors


def import_juniors(conn: sqlite3.Connection, df: pd.DataFrame) -> Tuple[int, list]:
    projects_df = repository.load_projects(conn)
    employees_df = repository.load_employees(conn)
    cur = conn.cursor()
    success = 0
    errors = []
    for idx, row in df.iterrows():
        proj_name = str(row['Проект']).strip()
        emp_name = str(row['Сотрудник']).strip()
        load_pct = float(row['Загрузка %']) if pd.notna(row.get('Загрузка %')) else 100.0
        proj_row = projects_df[projects_df['name'] == proj_name]
        if proj_row.empty:
            errors.append(f"Строка {idx+2}: проект '{proj_name}' не найден")
            continue
        emp_row = employees_df[employees_df['name'] == emp_name]
        if emp_row.empty:
            errors.append(f"Строка {idx+2}: сотрудник '{emp_name}' не найден")
            continue
        proj_id = proj_row.iloc[0]['id']
        emp_id = emp_row.iloc[0]['id']
        existing = cur.execute(
            "SELECT 1 FROM project_juniors WHERE project_id=? AND employee_id=?",
            (proj_id, emp_id)
        ).fetchone()
        if not existing:
            cur.execute("""
                INSERT INTO project_juniors (project_id, employee_id, load_percent)
                VALUES (?,?,?)
            """, (proj_id, emp_id, load_pct))
            conn.commit()
            success += 1
        else:
            errors.append(f"Строка {idx+2}: сотрудник '{emp_name}' уже назначен на проект '{proj_name}'")
    return success, errors


def import_phases(
    conn: sqlite3.Connection,
    df: pd.DataFrame,
    update_dates_callback: Optional[Callable[[int], None]] = None,
) -> Tuple[int, list]:
    """
    Импорт этапов из DataFrame.
    update_dates_callback(proj_id) вызывается после вставки этапа для проектов с auto_dates.
    Возвращает (success_count, list_of_errors).
    """
    projects_df = repository.load_projects(conn)
    cur = conn.cursor()

    def callback(proj_id):
        if update_dates_callback:
            update_dates_callback(proj_id)

    return import_phases_core(conn, cur, df, projects_df, callback)


def import_phase_assignments(conn: sqlite3.Connection, df: pd.DataFrame) -> Tuple[int, list]:
    """Импорт назначений на этапы из DataFrame. Возвращает (success_count, list_of_errors)."""
    projects_df = repository.load_projects(conn)
    phases_df = repository.load_phases(conn)
    employees_df = repository.load_employees(conn)
    return import_phase_assignments_core(conn, conn.cursor(), df, projects_df, phases_df, employees_df)
