# -*- coding: utf-8 -*-
"""Ядро импорта из Excel без зависимости от Streamlit (для тестов и вызова из Planner)."""
import pandas as pd

from utils.date_utils import parse_date_from_excel


def normalize_phase_type(phase_type):
    """Приводит тип этапа к одному из 'Обычная работа' или 'Командировка'."""
    t = str(phase_type).strip().lower() if phase_type is not None and pd.notna(phase_type) else ''
    if not t:
        return None
    if t in ('обычная работа', 'обычная'):
        return 'Обычная работа'
    if t == 'командировка':
        return 'Командировка'
    return None


def import_phases_core(conn, cursor, df, projects_df, update_project_dates_callback):
    """
    Импорт этапов из DataFrame в БД.
    update_project_dates_callback(proj_id) вызывается после каждой вставки, если у проекта auto_dates.
    Возвращает (success_count, list_of_errors).
    """
    success = 0
    errors = []
    for idx, row in df.iterrows():
        proj_name = str(row['Проект']).strip() if pd.notna(row.get('Проект')) else ''
        phase_name = str(row['Название этапа']).strip() if pd.notna(row.get('Название этапа')) else ''
        if not proj_name or proj_name.lower() == 'nan':
            errors.append(f"Строка {idx+2}: пустое название проекта")
            continue
        if not phase_name or phase_name.lower() == 'nan':
            errors.append(f"Строка {idx+2}: пустое название этапа")
            continue
        raw_type = str(row['Тип этапа']).strip() if pd.notna(row.get('Тип этапа')) else ''
        phase_type = normalize_phase_type(raw_type)
        if phase_type is None:
            errors.append(f"Строка {idx+2}: тип этапа должен быть 'Обычная работа' или 'Командировка' (получено: '{raw_type or 'пусто'}')")
            continue
        start_val = row['Дата начала']
        end_val = row['Дата окончания']
        if pd.isna(start_val) or pd.isna(end_val):
            errors.append(f"Строка {idx+2}: даты начала и окончания обязательны")
            continue
        try:
            start = parse_date_from_excel(start_val)
            end = parse_date_from_excel(end_val)
            start_str = start.isoformat()
            end_str = end.isoformat()
        except (ValueError, TypeError) as e:
            errors.append(f"Строка {idx+2}: неверный формат даты ({e})")
            continue
        if start > end:
            errors.append(f"Строка {idx+2}: дата начала позже даты окончания")
            continue
        proj_row = projects_df[projects_df['name'] == proj_name]
        if proj_row.empty:
            errors.append(f"Строка {idx+2}: проект '{proj_name}' не найден")
            continue
        proj_id = proj_row.iloc[0]['id']
        cursor.execute("""
            INSERT INTO project_phases (project_id, name, phase_type, start_date, end_date, completion_percent)
            VALUES (?,?,?,?,?,?)
        """, (proj_id, phase_name, phase_type, start_str, end_str, 0))
        conn.commit()
        proj = proj_row.iloc[0]
        auto_dates = proj.get('auto_dates')
        try:
            use_auto = bool(auto_dates) if auto_dates is not None and not pd.isna(auto_dates) else False
        except (ValueError, TypeError):
            use_auto = False
        if use_auto and update_project_dates_callback:
            update_project_dates_callback(proj_id)
        success += 1
    return success, errors


def import_phase_assignments_core(conn, cursor, df, projects_df, phases_df, employees_df):
    """
    Импорт назначений на этапы из DataFrame в БД.
    Возвращает (success_count, list_of_errors).
    """
    success = 0
    errors = []
    required_cols = ['Проект', 'Название этапа', 'Сотрудник', 'Загрузка %']
    if not all(c in df.columns for c in required_cols):
        return 0, [f"Требуются колонки: {', '.join(required_cols)}"]
    for idx, row in df.iterrows():
        proj_name = str(row['Проект']).strip() if pd.notna(row.get('Проект')) else ''
        phase_name = str(row['Название этапа']).strip() if pd.notna(row.get('Название этапа')) else ''
        emp_name = str(row['Сотрудник']).strip() if pd.notna(row.get('Сотрудник')) else ''
        if not proj_name or proj_name.lower() == 'nan':
            errors.append(f"Строка {idx+2}: пустые Проект, Название этапа или Сотрудник")
            continue
        if not phase_name or phase_name.lower() == 'nan':
            errors.append(f"Строка {idx+2}: пустые Проект, Название этапа или Сотрудник")
            continue
        if not emp_name or emp_name.lower() == 'nan':
            errors.append(f"Строка {idx+2}: пустые Проект, Название этапа или Сотрудник")
            continue
        load_pct = float(row['Загрузка %']) if pd.notna(row['Загрузка %']) else 100.0
        proj_row = projects_df[projects_df['name'] == proj_name]
        if proj_row.empty:
            errors.append(f"Строка {idx+2}: проект '{proj_name}' не найден")
            continue
        proj_id = proj_row.iloc[0]['id']
        phase_row = phases_df[(phases_df['project_id'] == proj_id) & (phases_df['name'] == phase_name)]
        if phase_row.empty:
            errors.append(f"Строка {idx+2}: этап '{phase_name}' в проекте '{proj_name}' не найден")
            continue
        emp_row = employees_df[employees_df['name'] == emp_name]
        if emp_row.empty:
            errors.append(f"Строка {idx+2}: сотрудник '{emp_name}' не найден")
            continue
        phase_id = int(phase_row.iloc[0]['id'])
        emp_id = int(emp_row.iloc[0]['id'])
        existing = cursor.execute(
            "SELECT 1 FROM phase_assignments WHERE phase_id=? AND employee_id=?",
            (phase_id, emp_id)
        ).fetchone()
        if not existing:
            cursor.execute("""
                INSERT INTO phase_assignments (phase_id, employee_id, load_percent)
                VALUES (?,?,?)
            """, (phase_id, emp_id, load_pct))
            conn.commit()
            success += 1
        else:
            errors.append(f"Строка {idx+2}: сотрудник '{emp_name}' уже назначен на этап '{phase_name}' в проекте '{proj_name}'")
    return success, errors
