# -*- coding: utf-8 -*-
"""Парсинг XML Microsoft Project (MSPDI) и маппинг в структуры для импорта в Planner."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Optional
import xml.etree.ElementTree as ET

import pandas as pd
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
    Каждый ресурс: UID, Name (может отсутствовать), Initials (может отсутствовать).
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
        initials = _text(r.find("pj:Initials", NS) or r.find(f"{{{NS['pj']}}}Initials"))
        resources.append({"UID": uid, "Name": name, "Initials": initials})
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


def get_mspdi_assigned_resources_by_task(root: ET.Element) -> dict:
    """По Assignments, Resources и полю «Исполнитель» возвращает для каждого TaskUID список имён (для предпросмотра). Name или Initials."""
    resources = parse_resources(root)
    assignments = parse_assignments(root)
    tasks = parse_tasks(root)
    resource_uid_to_name = {}
    for r in resources:
        if r.get("UID") is None:
            continue
        display = (r.get("Name") or r.get("Initials") or "").strip()
        if display:
            resource_uid_to_name[r["UID"]] = display
    task_uid_to_names = {}
    for a in assignments:
        task_uid = a.get("TaskUID")
        if task_uid is None:
            continue
        name = resource_uid_to_name.get(a.get("ResourceUID"))
        if not name:
            continue
        if name not in task_uid_to_names.setdefault(task_uid, []):
            task_uid_to_names[task_uid].append(name)
    for t in tasks:
        uid = t.get("UID")
        executor = t.get("executor")
        if uid is None or not executor or not (executor or "").strip():
            continue
        for part in (executor or "").split(","):
            name = (part or "").strip()
            if name and name not in task_uid_to_names.setdefault(uid, []):
                task_uid_to_names[uid].append(name)
    return task_uid_to_names


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


def _compute_parent_uid_for_tasks(tasks: list[dict[str, Any]]) -> None:
    """Для каждой задачи с OutlineLevel >= 1 проставляет parent_uid (UID последней предыдущей задачи с уровнем - 1)."""
    last_by_level: dict[int, int] = {}
    for t in tasks:
        level = t.get("OutlineLevel", 0)
        if level < 1:
            continue
        parent_uid = last_by_level.get(level - 1)
        t["parent_uid"] = parent_uid
        last_by_level[level] = t.get("UID")


def _fill_summary_dates_from_children(tasks: list[dict[str, Any]]) -> None:
    """Для сводных задач (Summary=1) без Start или Finish вычисляет даты по дочерним. Ожидает parent_uid."""
    uid_to_task = {t["UID"]: t for t in tasks}
    children: dict[int, list[dict[str, Any]]] = {}
    for t in tasks:
        pu = t.get("parent_uid")
        if pu is not None:
            children.setdefault(pu, []).append(t)

    def get_descendant_dates(uid: int) -> tuple[Optional[str], Optional[str]]:
        start_dates, finish_dates = [], []
        stack = [c["UID"] for c in children.get(uid, [])]
        while stack:
            u = stack.pop()
            task = uid_to_task.get(u)
            if not task:
                continue
            if task.get("Start"):
                start_dates.append(task["Start"])
            if task.get("Finish"):
                finish_dates.append(task["Finish"])
            for c in children.get(u, []):
                stack.append(c["UID"])
        return (min(start_dates) if start_dates else None, max(finish_dates) if finish_dates else None)

    for t in tasks:
        if t.get("Summary") != 1 or (t.get("Start") and t.get("Finish")):
            continue
        start_d, finish_d = get_descendant_dates(t["UID"])
        if start_d:
            t["Start"] = start_d
        if finish_d:
            t["Finish"] = finish_d


def build_project_and_phases_from_mspdi(
    root: ET.Element,
    only_leaf_tasks: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Строит структуры «проект» и «этапы» из корня MSPDI.
    При only_leaf_tasks=False возвращает этапы с uid и parent_uid для иерархии; даты сводных — по дочерним.
    """
    meta = parse_project_meta(root)
    tasks = parse_tasks(root)

    project_name = meta.get("title")
    if not project_name:
        for t in tasks:
            if t.get("OutlineLevel") == 0 and t.get("Name"):
                project_name = t["Name"]
                break
    if not project_name:
        project_name = "Проект из MS Project"

    if only_leaf_tasks:
        phase_tasks = _filter_phase_tasks(tasks, only_leaf_tasks=True)
        phases_list = [
            {"name": t["Name"], "start_date": t["Start"], "end_date": t["Finish"], "completion_percent": t.get("PercentComplete", 0)}
            for t in phase_tasks
        ]
    else:
        phase_tasks = []
        for i, t in enumerate(tasks):
            if t.get("OutlineLevel", 0) >= 1:
                t = {**t, "_index": i}
                phase_tasks.append(t)
        _compute_parent_uid_for_tasks(phase_tasks)
        _fill_summary_dates_from_children(phase_tasks)
        phase_tasks = [t for t in phase_tasks if t.get("Start") and t.get("Finish")]
        phase_tasks_sorted = sorted(phase_tasks, key=lambda t: (t.get("OutlineLevel", 1), t.get("_index", 0)))
        phases_list = [
            {
                "name": t["Name"], "start_date": t["Start"], "end_date": t["Finish"],
                "completion_percent": t.get("PercentComplete", 0), "uid": t["UID"], "parent_uid": t.get("parent_uid"),
            }
            for t in phase_tasks_sorted
        ]

    start_dates = [p["start_date"] for p in phases_list if p.get("start_date")]
    finish_dates = [p["end_date"] for p in phases_list if p.get("end_date")]
    if meta.get("start_date"):
        start_dates = start_dates or [meta["start_date"]]
    if meta.get("finish_date"):
        finish_dates = finish_dates or [meta["finish_date"]]
    project_start = min(start_dates) if start_dates else meta.get("start_date")
    project_finish = max(finish_dates) if finish_dates else meta.get("finish_date")
    if not project_start or not project_finish:
        project_start = project_start or meta.get("start_date")
        project_finish = project_finish or meta.get("finish_date")

    project_dict = {"name": project_name, "start_date": project_start, "finish_date": project_finish}
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
    uid_to_phase_id: dict[int, int] = {}
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
        parent_id = uid_to_phase_id.get(ph["parent_uid"]) if ph.get("parent_uid") is not None else None
        try:
            phase_id = repository.insert_phase(
                conn, project_id, name, DEFAULT_PHASE_TYPE,
                start_d, end_d, ph.get("completion_percent", 0), parent_id=parent_id,
            )
            if phase_id is not None and ph.get("uid") is not None:
                uid_to_phase_id[ph["uid"]] = phase_id
            success_phases += 1
        except Exception as e:
            errors.append(f"Этап «{name}»: {e}")

    if success_phases > 0:
        repository.update_project_dates_from_phases(conn, project_id)

    return project_id, success_phases, errors


def _normalize_resource_name(name: Optional[str]) -> str:
    """Нормализует имя ресурса для сопоставления с справочником: trim, схлопывание пробелов."""
    if not name:
        return ""
    s = (name or "").strip()
    return " ".join(s.split()) if s else ""


def _normalize_initials(value: Optional[str]) -> str:
    """Нормализует инициалы для сопоставления: trim, схлопывание пробелов."""
    if not value:
        return ""
    s = (value or "").strip()
    return " ".join(s.split()) if s else ""


def _find_employee_id_by_name(employees_df, name: str):
    """Ищет id сотрудника по имени: нормализация, при неудаче — без учёта регистра."""
    norm = _normalize_resource_name(name)
    if not norm:
        return None
    match = employees_df[employees_df["name"].apply(lambda x: _normalize_resource_name(str(x)) == norm)]
    if not match.empty:
        return int(match.iloc[0]["id"])
    norm_lower = norm.lower()
    for _, row in employees_df.iterrows():
        if _normalize_resource_name(str(row.get("name", ""))).lower() == norm_lower:
            return int(row["id"])
    return None


def _find_employee_id(employees_df, name=None, initials=None):
    """
    Ищет id сотрудника по инициалам (приоритет) и/или имени.
    Сначала по полю initials в БД, при неудаче — по name.
    """
    if "initials" in employees_df.columns:
        init_norm = _normalize_initials(initials)
        if init_norm:
            match = employees_df[
                employees_df["initials"].fillna("").apply(
                    lambda x: _normalize_initials(str(x)) == init_norm
                )
            ]
            if not match.empty:
                return int(match.iloc[0]["id"])
            init_lower = init_norm.lower()
            for _, row in employees_df.iterrows():
                if _normalize_initials(str(row.get("initials", "") or "")).lower() == init_lower:
                    return int(row["id"])
    if name:
        return _find_employee_id_by_name(employees_df, name)
    return None


def import_mspdi_assignments(
    conn: sqlite3.Connection,
    root: ET.Element,
    project_id: int,
    only_leaf_tasks: bool = False,
    default_load_percent: float = 100.0,
) -> tuple[int, list[str], list[str]]:
    """
    Импортирует назначения на этапы из MSPDI: из Assignments (TaskUID, ResourceUID, Units)
    и при отсутствии реальных ресурсов — из ExtendedAttribute «Исполнитель» у задач.

    Сопоставление с сотрудниками в БД — по полю Initials (если задано), иначе по имени (нормализация пробелов/регистра).
    Возвращает (success_count, list_of_errors, list_of_not_found_names).
    """
    errors: list[str] = []
    not_found: list[str] = []
    tasks = parse_tasks(root)
    resources = parse_resources(root)
    assignments = parse_assignments(root)

    phases_df = repository.load_phases(conn)
    phases_df = phases_df[phases_df["project_id"] == project_id].sort_values("id").reset_index(drop=True)
    employees_df = repository.load_employees(conn)

    _, phases_list_for_order = build_project_and_phases_from_mspdi(root, only_leaf_tasks)
    if len(phases_list_for_order) != len(phases_df):
        errors.append(
            f"Количество этапов в XML ({len(phases_list_for_order)}) не совпадает с количеством в БД ({len(phases_df)})"
        )
        return 0, errors, not_found

    task_uid_to_phase_id: dict[int, int] = {}
    if phases_list_for_order and phases_list_for_order[0].get("uid") is not None:
        for i, ph in enumerate(phases_list_for_order):
            if i < len(phases_df) and ph.get("uid") is not None:
                task_uid_to_phase_id[ph["uid"]] = int(phases_df.iloc[i]["id"])
    else:
        phase_tasks = _filter_phase_tasks(tasks, only_leaf_tasks)
        for i, task in enumerate(phase_tasks):
            if i < len(phases_df):
                task_uid_to_phase_id[task["UID"]] = int(phases_df.iloc[i]["id"])

    resource_uid_to_resource = {r["UID"]: r for r in resources if r.get("UID") is not None}
    cur = conn.cursor()
    success = 0
    seen_assignments: set[tuple[int, int]] = set()
    seen_not_found: set[str] = set()

    for a in assignments:
        if a.get("ResourceUID") is None or a["ResourceUID"] == RESOURCE_UID_UNASSIGNED:
            continue
        resource = resource_uid_to_resource.get(a["ResourceUID"])
        if not resource:
            continue
        resource_name = (resource.get("Name") or "").strip()
        resource_initials = (resource.get("Initials") or "").strip()
        display_name = resource_name or resource_initials or ""
        if not display_name:
            continue
        phase_id = task_uid_to_phase_id.get(a["TaskUID"])
        if phase_id is None:
            continue
        employee_id = _find_employee_id(
            employees_df,
            name=resource_name if resource_name else None,
            initials=resource_initials if resource_initials else None,
        )
        if employee_id is None:
            if display_name not in seen_not_found:
                seen_not_found.add(display_name)
                not_found.append(display_name)
            continue
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
            errors.append(f"Назначение {display_name} на этап: {e}")

    uid_to_task = {t["UID"]: t for t in tasks}
    executor_items: list[tuple[Optional[int], Optional[str]]] = []
    if phases_list_for_order and phases_list_for_order[0].get("uid") is not None:
        for ph in phases_list_for_order:
            pid = task_uid_to_phase_id.get(ph["uid"]) if ph.get("uid") is not None else None
            task = uid_to_task.get(ph["uid"]) if ph.get("uid") is not None else None
            executor_items.append((pid, task.get("executor") if task else None))
    else:
        phase_tasks = _filter_phase_tasks(tasks, only_leaf_tasks)
        for task in phase_tasks:
            executor_items.append((task_uid_to_phase_id.get(task["UID"]), task.get("executor")))

    for phase_id, executor in executor_items:
        if not executor or not (executor or "").strip():
            continue
        if phase_id is None:
            continue
        names = [_normalize_resource_name(n) for n in executor.split(",") if _normalize_resource_name(n)]
        if not names:
            continue
        load_each = default_load_percent if len(names) == 1 else round(default_load_percent / len(names), 1)
        for emp_name in names:
            employee_id = _find_employee_id_by_name(employees_df, emp_name)
            if employee_id is None:
                if emp_name not in seen_not_found:
                    seen_not_found.add(emp_name)
                    not_found.append(emp_name)
                continue
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

    return success, errors, not_found
