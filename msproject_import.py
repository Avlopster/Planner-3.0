# -*- coding: utf-8 -*-
"""Парсинг XML Microsoft Project (MSPDI) и маппинг в структуры для импорта в Planner."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Optional
import xml.etree.ElementTree as ET

import repository

# Namespace MSPDI (Microsoft Project Data Interchange)
NS = {"pj": "http://schemas.microsoft.com/project"}

# FieldID расширенного атрибута «Исполнитель» (Текст1) в MS Project
EXTENDED_ATTR_EXECUTOR_FIELD_ID = 188743731


def _parse_date(value: Optional[str]) -> Optional[str]:
    """Приводит строку даты ISO (YYYY-MM-DDTHH:MM:SS) к дате, возвращает строку YYYY-MM-DD или None."""
    if not value or not value.strip():
        return None
    value = value.strip()
    try:
        if "T" in value:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.date().isoformat()
        return value[:10]
    except (ValueError, TypeError):
        return None


def _text(el: Optional[ET.Element], default: Optional[str] = None) -> Optional[str]:
    """Текст элемента или default."""
    if el is None:
        return default
    return (el.text or "").strip() or default


def _int_val(el: Optional[ET.Element], default: Optional[int] = None) -> Optional[int]:
    """Целое значение элемента."""
    t = _text(el)
    if t is None or t == "":
        return default
    try:
        return int(t)
    except (ValueError, TypeError):
        return default


def _float_val(el: Optional[ET.Element], default: Optional[float] = None) -> Optional[float]:
    """Вещественное значение элемента."""
    t = _text(el)
    if t is None or t == "":
        return default
    try:
        return float(t)
    except (ValueError, TypeError):
        return default


def parse_project_meta(root: ET.Element) -> dict[str, Any]:
    """
    Извлекает метаданные проекта из корня XML.
    Возвращает dict: title, start_date, finish_date (строки YYYY-MM-DD или None).
    """
    out = {"title": None, "start_date": None, "finish_date": None}
    # Корневой элемент может быть Project в default namespace
    for tag in ("Title", "StartDate", "FinishDate"):
        el = root.find(f".//pj:{tag}", NS)
        if el is None:
            el = root.find(f".//{{{NS['pj']}}}{tag}")
        if el is not None and el.text:
            val = el.text.strip()
            if tag == "Title":
                out["title"] = val
            elif tag == "StartDate":
                out["start_date"] = _parse_date(val)
            elif tag == "FinishDate":
                out["finish_date"] = _parse_date(val)
    return out


def parse_tasks(root: ET.Element) -> list[dict[str, Any]]:
    """
    Извлекает все задачи из Project/Tasks/Task.
    Каждая задача: UID, Name, OutlineLevel, Summary, Start, Finish, PercentComplete,
    extended_attributes (список dict с FieldID, Value), executor (значение поля «Исполнитель» если есть).
    """
    tasks = []
    tasks_el = root.find(".//pj:Tasks", NS)
    if tasks_el is None:
        tasks_el = root.find(f".//{{{NS['pj']}}}Tasks")
    if tasks_el is None:
        return tasks

    for task_el in tasks_el.findall("pj:Task", NS) or tasks_el.findall(f"{{{NS['pj']}}}Task") or []:
        uid = _int_val(task_el.find("pj:UID", NS) or task_el.find(f"{{{NS['pj']}}}UID"))
        name = _text(task_el.find("pj:Name", NS) or task_el.find(f"{{{NS['pj']}}}Name"))
        outline_level = _int_val(task_el.find("pj:OutlineLevel", NS) or task_el.find(f"{{{NS['pj']}}}OutlineLevel"), 0)
        summary = _int_val(task_el.find("pj:Summary", NS) or task_el.find(f"{{{NS['pj']}}}Summary"), 0)
        start_raw = _text(task_el.find("pj:Start", NS) or task_el.find(f"{{{NS['pj']}}}Start"))
        finish_raw = _text(task_el.find("pj:Finish", NS) or task_el.find(f"{{{NS['pj']}}}Finish"))
        percent = _int_val(task_el.find("pj:PercentComplete", NS) or task_el.find(f"{{{NS['pj']}}}PercentComplete"), 0)

        extended = []
        executor_value = None
        for ext in task_el.findall("pj:ExtendedAttribute", NS) or task_el.findall(f"{{{NS['pj']}}}ExtendedAttribute") or []:
            field_id = _int_val(ext.find("pj:FieldID", NS) or ext.find(f"{{{NS['pj']}}}FieldID"))
            value = _text(ext.find("pj:Value", NS) or ext.find(f"{{{NS['pj']}}}Value"))
            extended.append({"FieldID": field_id, "Value": value})
            if field_id == EXTENDED_ATTR_EXECUTOR_FIELD_ID and value:
                executor_value = value

        tasks.append({
            "UID": uid,
            "Name": name or "",
            "OutlineLevel": outline_level,
            "Summary": summary,
            "Start": _parse_date(start_raw),
            "Finish": _parse_date(finish_raw),
            "PercentComplete": percent,
            "extended_attributes": extended,
            "executor": executor_value,
        })
    return tasks


def parse_resources(root: ET.Element) -> list[dict[str, Any]]:
    """
    Извлекает ресурсы из Project/Resources/Resource.
    Каждый ресурс: UID, Name (может отсутствовать).
    """
    resources = []
    res_el = root.find(".//pj:Resources", NS)
    if res_el is None:
        res_el = root.find(f".//{{{NS['pj']}}}Resources")
    if res_el is None:
        return resources

    for r in res_el.findall("pj:Resource", NS) or res_el.findall(f"{{{NS['pj']}}}Resource") or []:
        uid = _int_val(r.find("pj:UID", NS) or r.find(f"{{{NS['pj']}}}UID"))
        name = _text(r.find("pj:Name", NS) or r.find(f"{{{NS['pj']}}}Name"))
        resources.append({"UID": uid, "Name": name})
    return resources


def parse_assignments(root: ET.Element) -> list[dict[str, Any]]:
    """
    Извлекает назначения из Project/Assignments/Assignment.
    Каждое: TaskUID, ResourceUID, Units (1 = 100%).
    """
    assignments = []
    assign_el = root.find(".//pj:Assignments", NS)
    if assign_el is None:
        assign_el = root.find(f".//{{{NS['pj']}}}Assignments")
    if assign_el is None:
        return assignments

    for a in assign_el.findall("pj:Assignment", NS) or assign_el.findall(f"{{{NS['pj']}}}Assignment") or []:
        task_uid = _int_val(a.find("pj:TaskUID", NS) or a.find(f"{{{NS['pj']}}}TaskUID"))
        resource_uid = _int_val(a.find("pj:ResourceUID", NS) or a.find(f"{{{NS['pj']}}}ResourceUID"))
        units = _float_val(a.find("pj:Units", NS) or a.find(f"{{{NS['pj']}}}Units"), 1.0)
        assignments.append({"TaskUID": task_uid, "ResourceUID": resource_uid, "Units": units})
    return assignments


def read_mspdi_file(file_path: str) -> ET.Element:
    """
    Читает XML-файл MSPDI и возвращает корневой элемент.
    При ошибке парсинга пробрасывает исключение ET.ParseError.
    """
    tree = ET.parse(file_path)
    return tree.getroot()


# Тип этапа по умолчанию при импорте из MSPDI (в XML нет аналога «Командировка»/«Обычная работа»)
DEFAULT_PHASE_TYPE = "Обычная работа"

# Специальный ResourceUID в MS Project — «назначение без ресурса»
RESOURCE_UID_UNASSIGNED = -65535


def _filter_phase_tasks(tasks: list[dict[str, Any]], only_leaf_tasks: bool) -> list[dict[str, Any]]:
    """Отбирает задачи, подходящие как этапы (тот же критерий, что в build_project_and_phases_from_mspdi)."""
    if only_leaf_tasks:
        return [
            t
            for t in tasks
            if t.get("OutlineLevel", 0) >= 1
            and t.get("Summary") == 0
            and t.get("Start")
            and t.get("Finish")
        ]
    return [
        t
        for t in tasks
        if t.get("OutlineLevel", 0) >= 1 and t.get("Start") and t.get("Finish")
    ]


def build_project_and_phases_from_mspdi(
    root: ET.Element,
    only_leaf_tasks: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Строит структуры «проект» и «этапы» из корня MSPDI.

    Проект: name (из Title или первой задачи OutlineLevel=0), start_date, finish_date
    (из метаданных или min/max по выбранным задачам).

    Этапы: задачи с OutlineLevel >= 1 и заполненными Start/Finish; при only_leaf_tasks=True
    — только задачи с Summary=0.

    Возвращает (project_dict, phases_list). project_dict: name, start_date, finish_date.
    phases_list: список dict с ключами name, start_date, end_date, completion_percent.
    """
    meta = parse_project_meta(root)
    tasks = parse_tasks(root)

    # Название проекта: из Title или из первой задачи уровня 0
    project_name = meta.get("title")
    if not project_name:
        for t in tasks:
            if t.get("OutlineLevel") == 0 and t.get("Name"):
                project_name = t["Name"]
                break
    if not project_name:
        project_name = "Проект из MS Project"

    # Фильтр задач для этапов
    phase_tasks = _filter_phase_tasks(tasks, only_leaf_tasks)

    # Даты проекта: из метаданных или min/max по этапам
    start_dates = [t["Start"] for t in phase_tasks if t.get("Start")]
    finish_dates = [t["Finish"] for t in phase_tasks if t.get("Finish")]
    if meta.get("start_date"):
        start_dates = start_dates or [meta["start_date"]]
    if meta.get("finish_date"):
        finish_dates = finish_dates or [meta["finish_date"]]
    project_start = min(start_dates) if start_dates else meta.get("start_date")
    project_finish = max(finish_dates) if finish_dates else meta.get("finish_date")
    if not project_start or not project_finish:
        project_start = project_start or meta.get("start_date")
        project_finish = project_finish or meta.get("finish_date")

    project_dict = {
        "name": project_name,
        "start_date": project_start,
        "finish_date": project_finish,
    }

    phases_list = [
        {
            "name": t["Name"],
            "start_date": t["Start"],
            "end_date": t["Finish"],
            "completion_percent": t.get("PercentComplete", 0),
        }
        for t in phase_tasks
    ]

    return project_dict, phases_list


def import_mspdi_project_and_phases(
    conn: sqlite3.Connection,
    root: ET.Element,
    only_leaf_tasks: bool = False,
    default_status_code: str = "in_progress",
) -> tuple[Optional[int], int, list[str]]:
    """
    Импортирует из MSPDI один проект и его этапы в БД.

    Создаёт запись в projects (lead_id и client_company — NULL/пусто), затем вставляет этапы
    в project_phases. После вставки этапов обновляет даты проекта через
    update_project_dates_from_phases.

    Возвращает (project_id, success_phases_count, list_of_errors).
    При ошибке создания проекта project_id будет None, errors непустой.
    """
    errors: list[str] = []
    project_dict, phases_list = build_project_and_phases_from_mspdi(root, only_leaf_tasks)

    if not project_dict.get("name"):
        errors.append("Не удалось определить название проекта из XML")
        return None, 0, errors

    start_str = project_dict.get("start_date")
    finish_str = project_dict.get("finish_date")
    if not start_str or not finish_str:
        errors.append("Не удалось определить даты проекта (метаданные или задачи)")
        return None, 0, errors

    status_id = repository.get_status_id_by_code(conn, default_status_code)
    cur = conn.cursor()

    try:
        cur.execute(
            """
            INSERT INTO projects
            (name, client_company, lead_id, lead_load_percent, project_start, project_end, auto_dates, status_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_dict["name"],
                None,
                None,
                50.0,
                start_str,
                finish_str,
                1,
                status_id,
            ),
        )
        conn.commit()
        project_id = cur.lastrowid
    except Exception as e:
        errors.append(f"Ошибка создания проекта: {e}")
        return None, 0, errors

    success_phases = 0
    for ph in phases_list:
        name = (ph.get("name") or "").strip()
        if not name:
            errors.append("Пропущен этап с пустым названием")
            continue
        start_d = ph.get("start_date")
        end_d = ph.get("end_date")
        if not start_d or not end_d:
            errors.append(f"Этап «{name}»: отсутствуют даты")
            continue
        if start_d > end_d:
            errors.append(f"Этап «{name}»: дата начала позже даты окончания")
            continue
        try:
            cur.execute(
                """
                INSERT INTO project_phases (project_id, name, phase_type, start_date, end_date, completion_percent)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    name,
                    DEFAULT_PHASE_TYPE,
                    start_d,
                    end_d,
                    ph.get("completion_percent", 0),
                ),
            )
            conn.commit()
            success_phases += 1
        except Exception as e:
            errors.append(f"Этап «{name}»: {e}")

    if success_phases > 0:
        repository.update_project_dates_from_phases(conn, project_id)

    return project_id, success_phases, errors


def import_mspdi_assignments(
    conn: sqlite3.Connection,
    root: ET.Element,
    project_id: int,
    only_leaf_tasks: bool = False,
    default_load_percent: float = 100.0,
) -> tuple[int, list[str]]:
    """
    Импортирует назначения на этапы из MSPDI: из Assignments (TaskUID, ResourceUID, Units)
    и при отсутствии реальных ресурсов — из ExtendedAttribute «Исполнитель» у задач.

    Сопоставление Task UID → phase_id выполняется по порядку этапов (этапы в БД в том же
    порядке, что и отфильтрованные задачи в XML). ResourceUID=-65535 пропускается.

    Возвращает (success_count, list_of_errors).
    """
    errors: list[str] = []
    tasks = parse_tasks(root)
    resources = parse_resources(root)
    assignments = parse_assignments(root)
    phase_tasks = _filter_phase_tasks(tasks, only_leaf_tasks)

    phases_df = repository.load_phases(conn)
    phases_df = phases_df[phases_df["project_id"] == project_id].sort_values("id").reset_index(drop=True)
    employees_df = repository.load_employees(conn)

    if len(phase_tasks) != len(phases_df):
        errors.append(
            f"Количество этапов в XML ({len(phase_tasks)}) не совпадает с количеством в БД ({len(phases_df)})"
        )
        return 0, errors

    task_uid_to_phase_id: dict[int, int] = {}
    for i, task in enumerate(phase_tasks):
        if i < len(phases_df):
            task_uid_to_phase_id[task["UID"]] = int(phases_df.iloc[i]["id"])

    resource_uid_to_name = {r["UID"]: r["Name"] for r in resources if r.get("Name")}
    cur = conn.cursor()
    success = 0
    seen_assignments: set[tuple[int, int]] = set()

    for a in assignments:
        if a.get("ResourceUID") is None or a["ResourceUID"] == RESOURCE_UID_UNASSIGNED:
            continue
        resource_name = resource_uid_to_name.get(a["ResourceUID"])
        if not resource_name or not (resource_name or "").strip():
            continue
        phase_id = task_uid_to_phase_id.get(a["TaskUID"])
        if phase_id is None:
            continue
        emp_row = employees_df[employees_df["name"] == resource_name.strip()]
        if emp_row.empty:
            errors.append(f"Сотрудник «{resource_name}» не найден в справочнике")
            continue
        employee_id = int(emp_row.iloc[0]["id"])
        load_pct = round((a.get("Units") or 1.0) * 100.0, 1)
        key = (phase_id, employee_id)
        if key in seen_assignments:
            continue
        existing = cur.execute(
            "SELECT 1 FROM phase_assignments WHERE phase_id=? AND employee_id=?",
            (phase_id, employee_id),
        ).fetchone()
        if existing:
            seen_assignments.add(key)
            continue
        try:
            cur.execute(
                "INSERT INTO phase_assignments (phase_id, employee_id, load_percent) VALUES (?, ?, ?)",
                (phase_id, employee_id, load_pct),
            )
            conn.commit()
            seen_assignments.add(key)
            success += 1
        except Exception as e:
            errors.append(f"Назначение {resource_name} на этап: {e}")

    for task in phase_tasks:
        executor = task.get("executor")
        if not executor or not (executor or "").strip():
            continue
        phase_id = task_uid_to_phase_id.get(task["UID"])
        if phase_id is None:
            continue
        names = [n.strip() for n in executor.split(",") if n.strip()]
        if not names:
            continue
        load_each = default_load_percent if len(names) == 1 else round(default_load_percent / len(names), 1)
        for emp_name in names:
            emp_row = employees_df[employees_df["name"] == emp_name]
            if emp_row.empty:
                errors.append(f"Сотрудник «{emp_name}» (Исполнитель) не найден в справочнике")
                continue
            employee_id = int(emp_row.iloc[0]["id"])
            key = (phase_id, employee_id)
            if key in seen_assignments:
                continue
            existing = cur.execute(
                "SELECT 1 FROM phase_assignments WHERE phase_id=? AND employee_id=?",
                (phase_id, employee_id),
            ).fetchone()
            if existing:
                seen_assignments.add(key)
                continue
            try:
                cur.execute(
                    "INSERT INTO phase_assignments (phase_id, employee_id, load_percent) VALUES (?, ?, ?)",
                    (phase_id, employee_id, load_each),
                )
                conn.commit()
                seen_assignments.add(key)
                success += 1
            except Exception as e:
                errors.append(f"Назначение «{emp_name}» (Исполнитель): {e}")

    return success, errors
