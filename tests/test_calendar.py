# -*- coding: utf-8 -*-
"""Тесты страницы Календарь: события по сотрудникам, фильтры, период, проекты vs отпуска, конфликты, экспорт."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pandas as pd
from datetime import date, timedelta


# --- Логика календаря (копия расчётов из app_pages/calendar.py для тестов без Streamlit) ---

def calendar_period_filter(df, start_str, end_str, start_col="Начало", end_col="Окончание"):
    """Фильтр: оставляем события, которые пересекаются с периодом [start_str, end_str]."""
    if df.empty:
        return df
    start_dt = pd.to_datetime(start_str)
    end_dt = pd.to_datetime(end_str)
    return df[(df[end_col] >= start_dt) & (df[start_col] <= end_dt)]


def calendar_events_tab1(
    df_vac,
    projects,
    juniors,
    phases_df,
    emp_id_to_name,
    show_vacations=True,
    show_projects=True,
    selected_projects=None,
):
    """Строит список событий для вкладки «Отпуска + проекты (по сотрудникам)» до фильтра по периоду."""
    events = []
    if selected_projects is None:
        selected_projects = []

    if show_vacations and not df_vac.empty:
        for _, vac in df_vac.iterrows():
            emp_id = vac["employee_id"]
            emp_name = emp_id_to_name.get(emp_id, "Не найден")
            events.append(
                dict(
                    Сотрудник=emp_name,
                    Начало=pd.to_datetime(vac["start_date"]),
                    Окончание=pd.to_datetime(vac["end_date"]),
                    Тип="Отпуск",
                    Проект="",
                )
            )

    if show_projects and not projects.empty:
        for _, proj in projects.iterrows():
            if selected_projects and proj["name"] not in selected_projects:
                continue
            if proj.get("auto_dates"):
                proj_phases = phases_df[phases_df["project_id"] == proj["id"]]
                if proj_phases.empty:
                    continue
                proj_start = proj_phases["start_date"].min()
                proj_end = proj_phases["end_date"].max()
            else:
                proj_start = proj.get("project_start")
                proj_end = proj.get("project_end")
                if not proj_start or not proj_end:
                    continue

            lead_id = proj.get("lead_id")
            if lead_id is not None:
                lead_name = emp_id_to_name.get(lead_id, "Не найден")
                events.append(
                    dict(
                        Сотрудник=lead_name,
                        Начало=pd.to_datetime(proj_start),
                        Окончание=pd.to_datetime(proj_end),
                        Тип="Проект (вед.)",
                        Проект=proj["name"],
                    )
                )
            proj_jun = juniors[juniors["project_id"] == proj["id"]]
            for _, j in proj_jun.iterrows():
                jun_name = emp_id_to_name.get(j["employee_id"], "Не найден")
                events.append(
                    dict(
                        Сотрудник=jun_name,
                        Начало=pd.to_datetime(proj_start),
                        Окончание=pd.to_datetime(proj_end),
                        Тип="Проект",
                        Проект=proj["name"],
                    )
                )

    return pd.DataFrame(events)


def calendar_tasks_tab2_left(
    projects,
    phases_df,
    emp_id_to_name,
    selected_projects_dual=None,
):
    """Строит задачи (проекты + этапы) для левого окна вкладки «Проекты vs отпуска» до фильтра по периоду."""
    tasks = []
    if selected_projects_dual is None:
        selected_projects_dual = []

    for _, proj in projects.iterrows():
        if selected_projects_dual and proj["name"] not in selected_projects_dual:
            continue
        if proj.get("auto_dates"):
            proj_phases = phases_df[phases_df["project_id"] == proj["id"]]
            if proj_phases.empty:
                continue
            proj_start = proj_phases["start_date"].min()
            proj_end = proj_phases["end_date"].max()
        else:
            proj_start = proj.get("project_start")
            proj_end = proj.get("project_end")
            if not proj_start or not proj_end:
                continue

        lead_name = emp_id_to_name.get(proj.get("lead_id"), "—") if proj.get("lead_id") else "—"
        tasks.append(
            dict(
                Задача=f"📁 {proj['name']}",
                Начало=pd.to_datetime(proj_start),
                Окончание=pd.to_datetime(proj_end),
                Тип="Проект",
                Описание=f"Ведущий: {lead_name}",
            )
        )
        proj_phases = phases_df[phases_df["project_id"] == proj["id"]]
        for _, ph in proj_phases.iterrows():
            tasks.append(
                dict(
                    Задача=f"  • {proj['name']} — {ph['name']}",
                    Начало=pd.to_datetime(ph["start_date"]),
                    Окончание=pd.to_datetime(ph["end_date"]),
                    Тип=ph.get("phase_type", "Этап"),
                    Описание="",
                )
            )

    return pd.DataFrame(tasks)


def calendar_vac_events_tab2_right(df_vac, employees_to_show_ids, emp_id_to_name):
    """Строит события отпусков для правого окна (до фильтра по периоду)."""
    vac_events = []
    for _, vac in df_vac.iterrows():
        emp_id = vac["employee_id"]
        if employees_to_show_ids is not None and emp_id not in employees_to_show_ids:
            continue
        emp_name = emp_id_to_name.get(emp_id, "Не найден")
        vac_events.append(
            dict(
                Сотрудник=emp_name,
                Начало=pd.to_datetime(vac["start_date"]),
                Окончание=pd.to_datetime(vac["end_date"]),
                Тип="Отпуск",
            )
        )
    return pd.DataFrame(vac_events)


def calendar_employees_to_show(
    df_emp,
    projects,
    juniors,
    filter_employees_by_projects,
    selected_projects_dual,
):
    """Список id сотрудников для отображения в двухоконном режиме и в конфликтах."""
    if not filter_employees_by_projects or not selected_projects_dual:
        return set(df_emp["id"].tolist()) if not df_emp.empty else set()

    project_ids = projects[projects["name"].isin(selected_projects_dual)]["id"].tolist()
    employee_ids = set()
    for proj_id in project_ids:
        proj = projects[projects["id"] == proj_id].iloc[0]
        if proj.get("lead_id"):
            employee_ids.add(proj["lead_id"])
        proj_jun = juniors[juniors["project_id"] == proj_id]
        for _, j in proj_jun.iterrows():
            employee_ids.add(j["employee_id"])
    return employee_ids


def conflict_day_check(day_date, emp_vacations, day_load):
    """Проверка одного дня на конфликт: отпуск и загрузка > 0."""
    if day_load <= 0:
        return False
    for _, vac in emp_vacations.iterrows():
        vs = pd.to_datetime(vac["start_date"]).date() if hasattr(pd.to_datetime(vac["start_date"]), "date") else pd.to_datetime(vac["start_date"])
        if hasattr(vs, "date"):
            vs = vs.date()
        ve = pd.to_datetime(vac["end_date"]).date() if hasattr(pd.to_datetime(vac["end_date"]), "date") else pd.to_datetime(vac["end_date"])
        if hasattr(ve, "date"):
            ve = ve.date()
        if vs <= day_date <= ve:
            return True
    return False


def conflicts_excel_columns():
    """Колонки для экспорта конфликтов в Excel (как в calendar.py)."""
    return ["Сотрудник", "Дата", "Загрузка", "Проект", "Этап", "Рекомендуемая замена"]


# --- Условие отображения предупреждения «Нет сотрудников» ---

def calendar_should_show_no_employees_warning(df_emp):
    """True, если нужно показать предупреждение «Нет сотрудников.» (логика из calendar.render)."""
    return df_emp.empty


# --- Тесты: навигация и период ---

class TestCalendarNoEmployees:
    """Пустой список сотрудников — показ предупреждения."""

    def test_show_warning_when_no_employees(self):
        df_emp = pd.DataFrame(columns=["id", "name"])
        assert calendar_should_show_no_employees_warning(df_emp) is True

    def test_no_warning_when_employees_exist(self):
        df_emp = pd.DataFrame([{"id": 1, "name": "Иванов"}])
        assert calendar_should_show_no_employees_warning(df_emp) is False


class TestCalendarPeriodFilter:
    """Проверка влияния периода на отображаемые события."""

    def test_empty_df(self):
        df = pd.DataFrame(columns=["Начало", "Окончание"])
        out = calendar_period_filter(df, "2025-06-01", "2025-06-30")
        assert out.empty

    def test_event_fully_inside_period(self):
        df = pd.DataFrame(
            [
                {
                    "Начало": pd.to_datetime("2025-06-10"),
                    "Окончание": pd.to_datetime("2025-06-15"),
                }
            ]
        )
        out = calendar_period_filter(df, "2025-06-01", "2025-06-30")
        assert len(out) == 1

    def test_event_start_before_period_excluded(self):
        """Событие начинается до периода и заканчивается внутри — должно быть показано (частичное пересечение)."""
        df = pd.DataFrame(
            [
                {
                    "Начало": pd.to_datetime("2025-05-25"),
                    "Окончание": pd.to_datetime("2025-06-05"),
                }
            ]
        )
        out = calendar_period_filter(df, "2025-06-01", "2025-06-30")
        assert len(out) == 1

    def test_event_end_after_period_excluded(self):
        """Событие начинается в период и заканчивается после него — должно быть показано (частичное пересечение)."""
        df = pd.DataFrame(
            [
                {
                    "Начало": pd.to_datetime("2025-06-25"),
                    "Окончание": pd.to_datetime("2025-07-10"),
                }
            ]
        )
        out = calendar_period_filter(df, "2025-06-01", "2025-06-30")
        assert len(out) == 1

    def test_multiple_events_mixed(self):
        df = pd.DataFrame(
            [
                {"Начало": pd.to_datetime("2025-05-20"), "Окончание": pd.to_datetime("2025-06-05")},
                {"Начало": pd.to_datetime("2025-06-10"), "Окончание": pd.to_datetime("2025-06-20")},
                {"Начало": pd.to_datetime("2025-07-01"), "Окончание": pd.to_datetime("2025-07-05")},
            ]
        )
        out = calendar_period_filter(df, "2025-06-01", "2025-06-30")
        # Первое и второе события пересекают период, третье — нет
        assert len(out) == 2


# --- Тесты: вкладка 1 «Отпуска + проекты (по сотрудникам)» ---

class TestCalendarEventsTab1:
    """Базовое отображение и фильтры вкладки 1."""

    def test_no_employees_empty_events(self):
        df_vac = pd.DataFrame(columns=["employee_id", "start_date", "end_date"])
        projects = pd.DataFrame(columns=["id", "name", "lead_id", "auto_dates", "project_start", "project_end"])
        juniors = pd.DataFrame(columns=["project_id", "employee_id"])
        phases_df = pd.DataFrame(columns=["project_id", "start_date", "end_date", "name", "phase_type"])
        emp_id_to_name = {}
        df = calendar_events_tab1(df_vac, projects, juniors, phases_df, emp_id_to_name)
        assert df.empty

    def test_vacations_only(self):
        df_vac = pd.DataFrame(
            [
                {"employee_id": 1, "start_date": date(2025, 6, 1), "end_date": date(2025, 6, 10)},
            ]
        )
        projects = pd.DataFrame()
        juniors = pd.DataFrame()
        phases_df = pd.DataFrame()
        emp_id_to_name = {1: "Иванов"}
        df = calendar_events_tab1(df_vac, projects, juniors, phases_df, emp_id_to_name, show_projects=False)
        assert len(df) == 1
        assert df.iloc[0]["Сотрудник"] == "Иванов"
        assert df.iloc[0]["Тип"] == "Отпуск"
        assert df.iloc[0]["Проект"] == ""

    def test_projects_only_manual_dates(self):
        df_vac = pd.DataFrame()
        projects = pd.DataFrame(
            [
                {
                    "id": 1,
                    "name": "Проект А",
                    "lead_id": 10,
                    "auto_dates": False,
                    "project_start": date(2025, 6, 1),
                    "project_end": date(2025, 6, 30),
                }
            ]
        )
        juniors = pd.DataFrame([{"project_id": 1, "employee_id": 20}])
        phases_df = pd.DataFrame()
        emp_id_to_name = {10: "Ведущий", 20: "Рядовой"}
        df = calendar_events_tab1(df_vac, projects, juniors, phases_df, emp_id_to_name, show_vacations=False)
        assert len(df) == 2
        types = df["Тип"].tolist()
        assert "Проект (вед.)" in types
        assert "Проект" in types
        assert set(df["Проект"].tolist()) == {"Проект А"}

    def test_filter_by_selected_projects(self):
        df_vac = pd.DataFrame()
        projects = pd.DataFrame(
            [
                {"id": 1, "name": "A", "lead_id": 10, "auto_dates": False, "project_start": date(2025, 6, 1), "project_end": date(2025, 6, 30)},
                {"id": 2, "name": "B", "lead_id": 10, "auto_dates": False, "project_start": date(2025, 6, 1), "project_end": date(2025, 6, 30)},
            ]
        )
        juniors = pd.DataFrame(columns=["project_id", "employee_id"])
        phases_df = pd.DataFrame(columns=["project_id", "start_date", "end_date", "name", "phase_type"])
        emp_id_to_name = {10: "Lead"}
        df = calendar_events_tab1(
            df_vac, projects, juniors, phases_df, emp_id_to_name,
            show_vacations=False, selected_projects=["A"],
        )
        assert len(df) == 1
        assert df.iloc[0]["Проект"] == "A"

    def test_show_vacations_show_projects_both_off(self):
        df_vac = pd.DataFrame([{"employee_id": 1, "start_date": date(2025, 6, 1), "end_date": date(2025, 6, 5)}])
        projects = pd.DataFrame([{"id": 1, "name": "P", "lead_id": 1, "auto_dates": False, "project_start": date(2025, 6, 1), "project_end": date(2025, 6, 30)}])
        juniors = pd.DataFrame()
        phases_df = pd.DataFrame()
        emp_id_to_name = {1: "Иванов"}
        df = calendar_events_tab1(df_vac, projects, juniors, phases_df, emp_id_to_name, show_vacations=False, show_projects=False)
        assert df.empty

    def test_auto_dates_from_phases(self):
        df_vac = pd.DataFrame()
        projects = pd.DataFrame([{"id": 1, "name": "P", "lead_id": 10, "auto_dates": True}])
        juniors = pd.DataFrame(columns=["project_id", "employee_id"])
        phases_df = pd.DataFrame(
            [
                {"project_id": 1, "start_date": date(2025, 6, 5), "end_date": date(2025, 6, 15), "name": "Э1", "phase_type": "Этап"},
                {"project_id": 1, "start_date": date(2025, 6, 20), "end_date": date(2025, 6, 25), "name": "Э2", "phase_type": "Этап"},
            ]
        )
        emp_id_to_name = {10: "Lead"}
        df = calendar_events_tab1(df_vac, projects, juniors, phases_df, emp_id_to_name, show_vacations=False)
        assert len(df) == 1
        assert df.iloc[0]["Начало"].date() == date(2025, 6, 5)
        assert df.iloc[0]["Окончание"].date() == date(2025, 6, 25)


# --- Тесты: вкладка 2 «Проекты vs отпуска (два окна)» ---

class TestCalendarTasksTab2Left:
    """Левое окно: проекты и этапы."""

    def test_projects_and_phases_rows(self):
        projects = pd.DataFrame(
            [
                {"id": 1, "name": "Проект X", "lead_id": 10, "auto_dates": True},
            ]
        )
        phases_df = pd.DataFrame(
            [
                {"project_id": 1, "start_date": date(2025, 6, 1), "end_date": date(2025, 6, 10), "name": "Этап 1", "phase_type": "Разработка"},
                {"project_id": 1, "start_date": date(2025, 6, 15), "end_date": date(2025, 6, 25), "name": "Этап 2", "phase_type": "Тест"},
            ]
        )
        emp_id_to_name = {10: "Ведущий"}
        df = calendar_tasks_tab2_left(projects, phases_df, emp_id_to_name)
        assert len(df) == 3
        tasks = df["Задача"].tolist()
        assert any("📁" in t and "Проект X" in t for t in tasks)
        assert any("Этап 1" in t for t in tasks)
        assert any("Этап 2" in t for t in tasks)

    def test_filter_by_selected_projects_dual(self):
        projects = pd.DataFrame(
            [
                {"id": 1, "name": "A", "lead_id": 10, "auto_dates": False, "project_start": date(2025, 6, 1), "project_end": date(2025, 6, 30)},
                {"id": 2, "name": "B", "lead_id": 10, "auto_dates": False, "project_start": date(2025, 6, 1), "project_end": date(2025, 6, 30)},
            ]
        )
        phases_df = pd.DataFrame(columns=["project_id", "start_date", "end_date", "name", "phase_type"])
        emp_id_to_name = {10: "Lead"}
        df = calendar_tasks_tab2_left(projects, phases_df, emp_id_to_name, selected_projects_dual=["B"])
        assert len(df) == 1
        assert "B" in df.iloc[0]["Задача"]


class TestCalendarVacEventsTab2Right:
    """Правое окно: отпуска сотрудников."""

    def test_all_employees_when_no_filter(self):
        df_vac = pd.DataFrame(
            [
                {"employee_id": 1, "start_date": date(2025, 6, 1), "end_date": date(2025, 6, 5)},
                {"employee_id": 2, "start_date": date(2025, 6, 10), "end_date": date(2025, 6, 12)},
            ]
        )
        df = calendar_vac_events_tab2_right(df_vac, None, {1: "Иванов", 2: "Петров"})
        assert len(df) == 2

    def test_only_selected_employees(self):
        df_vac = pd.DataFrame(
            [
                {"employee_id": 1, "start_date": date(2025, 6, 1), "end_date": date(2025, 6, 5)},
                {"employee_id": 2, "start_date": date(2025, 6, 10), "end_date": date(2025, 6, 12)},
            ]
        )
        df = calendar_vac_events_tab2_right(df_vac, {1}, {1: "Иванов", 2: "Петров"})
        assert len(df) == 1
        assert df.iloc[0]["Сотрудник"] == "Иванов"


class TestCalendarEmployeesToShow:
    """Фильтр «Показывать только сотрудников выбранных проектов»."""

    def test_all_employees_when_filter_off(self):
        df_emp = pd.DataFrame([{"id": 1}, {"id": 2}])
        projects = pd.DataFrame()
        juniors = pd.DataFrame()
        ids = calendar_employees_to_show(df_emp, projects, juniors, False, [])
        assert ids == {1, 2}

    def test_only_project_members_when_filter_on(self):
        df_emp = pd.DataFrame([{"id": 1}, {"id": 2}, {"id": 3}])
        projects = pd.DataFrame([{"id": 10, "name": "P", "lead_id": 1}])
        juniors = pd.DataFrame([{"project_id": 10, "employee_id": 2}])
        ids = calendar_employees_to_show(df_emp, projects, juniors, True, ["P"])
        assert ids == {1, 2}
        assert 3 not in ids


# --- Тесты: конфликты отпуск/проект ---

class TestConflictDayCheck:
    """Проверка одного дня на конфликт (отпуск + загрузка > 0)."""

    def test_no_conflict_no_vacation(self):
        emp_vacations = pd.DataFrame(columns=["start_date", "end_date"])
        assert conflict_day_check(date(2025, 6, 15), emp_vacations, 0.5) is False

    def test_no_conflict_zero_load(self):
        emp_vacations = pd.DataFrame([{"start_date": date(2025, 6, 1), "end_date": date(2025, 6, 10)}])
        assert conflict_day_check(date(2025, 6, 5), emp_vacations, 0.0) is False

    def test_conflict_vacation_and_load(self):
        emp_vacations = pd.DataFrame([{"start_date": date(2025, 6, 1), "end_date": date(2025, 6, 10)}])
        assert conflict_day_check(date(2025, 6, 5), emp_vacations, 0.5) is True

    def test_no_conflict_day_outside_vacation(self):
        emp_vacations = pd.DataFrame([{"start_date": date(2025, 6, 1), "end_date": date(2025, 6, 10)}])
        assert conflict_day_check(date(2025, 6, 15), emp_vacations, 0.5) is False


# --- Тесты: экспорт Excel (структура колонок) ---

class TestConflictsExcelExport:
    """Колонки выгрузки конфликтов."""

    def test_excel_columns_match_display(self):
        cols = conflicts_excel_columns()
        assert "Сотрудник" in cols
        assert "Дата" in cols
        assert "Загрузка" in cols
        assert "Проект" in cols
        assert "Этап" in cols
        assert "Рекомендуемая замена" in cols
        assert len(cols) == 6


# --- Интеграция: полный сценарий вкладки 1 с периодом ---

class TestCalendarTab1FullFlow:
    """Полный сценарий: события + фильтр по периоду."""

    def test_events_filtered_by_period(self):
        df_vac = pd.DataFrame(
            [
                {"employee_id": 1, "start_date": date(2025, 5, 1), "end_date": date(2025, 5, 10)},
                {"employee_id": 1, "start_date": date(2025, 6, 10), "end_date": date(2025, 6, 15)},
                {"employee_id": 1, "start_date": date(2025, 7, 1), "end_date": date(2025, 7, 5)},
            ]
        )
        projects = pd.DataFrame()
        juniors = pd.DataFrame()
        phases_df = pd.DataFrame()
        emp_id_to_name = {1: "Иванов"}
        df = calendar_events_tab1(df_vac, projects, juniors, phases_df, emp_id_to_name, show_projects=False)
        df = calendar_period_filter(df, "2025-06-01", "2025-06-30")
        assert len(df) == 1
        assert df.iloc[0]["Начало"].date() == date(2025, 6, 10)
        assert df.iloc[0]["Окончание"].date() == date(2025, 6, 15)
