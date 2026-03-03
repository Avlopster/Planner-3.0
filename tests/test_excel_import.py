# -*- coding: utf-8 -*-
"""Тесты импорта этапов и назначений на этапы из Excel (ядро без Streamlit)."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pandas as pd
import sqlite3
from datetime import date

from excel_import import (
    normalize_phase_type,
    import_phases_core,
    import_phase_assignments_core,
)


def _make_memory_conn():
    """In-memory DB с минимальной схемой для этапов и назначений."""
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute("""CREATE TABLE roles (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL)""")
    cur.execute("""CREATE TABLE employees (id INTEGER PRIMARY KEY, name TEXT NOT NULL, role_id INTEGER)""")
    cur.execute("""
        CREATE TABLE projects (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            client_company TEXT,
            lead_id INTEGER,
            lead_load_percent REAL DEFAULT 50,
            project_start DATE NOT NULL,
            project_end DATE NOT NULL,
            auto_dates BOOLEAN DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE project_phases (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            phase_type TEXT NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            completion_percent INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE phase_assignments (
            id INTEGER PRIMARY KEY,
            phase_id INTEGER NOT NULL,
            employee_id INTEGER NOT NULL,
            load_percent REAL NOT NULL
        )
    """)
    conn.commit()
    return conn, cur


class TestNormalizePhaseType:
    def test_usual_work(self):
        assert normalize_phase_type("Обычная работа") == "Обычная работа"
        assert normalize_phase_type("обычная работа") == "Обычная работа"
        assert normalize_phase_type("  Обычная работа  ") == "Обычная работа"

    def test_komandirovka(self):
        assert normalize_phase_type("Командировка") == "Командировка"
        assert normalize_phase_type("командировка") == "Командировка"

    def test_invalid(self):
        assert normalize_phase_type("") is None
        assert normalize_phase_type("Другое") is None
        assert normalize_phase_type(None) is None


class TestImportPhasesCore:
    def test_empty_dataframe(self):
        conn, cur = _make_memory_conn()
        cur.execute(
            "INSERT INTO projects (name, project_start, project_end, auto_dates) VALUES (?,?,?,?)",
            ("Proj1", "2025-01-01", "2025-12-31", 0),
        )
        conn.commit()
        projects_df = pd.read_sql("SELECT * FROM projects", conn)
        df = pd.DataFrame(columns=["Проект", "Название этапа", "Тип этапа", "Дата начала", "Дата окончания"])
        succ, err = import_phases_core(conn, cur, df, projects_df, None)
        assert succ == 0
        assert len(err) == 0
        conn.close()

    def test_success_one_phase(self):
        conn, cur = _make_memory_conn()
        cur.execute(
            "INSERT INTO projects (name, project_start, project_end, auto_dates) VALUES (?,?,?,?)",
            ("Proj1", "2025-01-01", "2025-12-31", 0),
        )
        conn.commit()
        projects_df = pd.read_sql("SELECT * FROM projects", conn)
        df = pd.DataFrame([
            ["Proj1", "Этап 1", "Обычная работа", "01.02.2025", "28.02.2025"],
        ], columns=["Проект", "Название этапа", "Тип этапа", "Дата начала", "Дата окончания"])
        succ, err = import_phases_core(conn, cur, df, projects_df, None)
        assert succ == 1
        assert len(err) == 0
        rows = cur.execute("SELECT * FROM project_phases").fetchall()
        assert len(rows) == 1
        assert rows[0][2] == "Этап 1"
        assert rows[0][3] == "Обычная работа"
        conn.close()

    def test_phase_type_normalized(self):
        conn, cur = _make_memory_conn()
        cur.execute(
            "INSERT INTO projects (name, project_start, project_end, auto_dates) VALUES (?,?,?,?)",
            ("Proj1", "2025-01-01", "2025-12-31", 0),
        )
        conn.commit()
        projects_df = pd.read_sql("SELECT * FROM projects", conn)
        df = pd.DataFrame([
            ["Proj1", "Этап 1", "командировка", "01.02.2025", "28.02.2025"],
        ], columns=["Проект", "Название этапа", "Тип этапа", "Дата начала", "Дата окончания"])
        succ, err = import_phases_core(conn, cur, df, projects_df, None)
        assert succ == 1
        rows = cur.execute("SELECT * FROM project_phases").fetchall()
        assert rows[0][3] == "Командировка"
        conn.close()

    def test_empty_project_name(self):
        conn, cur = _make_memory_conn()
        cur.execute(
            "INSERT INTO projects (name, project_start, project_end, auto_dates) VALUES (?,?,?,?)",
            ("Proj1", "2025-01-01", "2025-12-31", 0),
        )
        conn.commit()
        projects_df = pd.read_sql("SELECT * FROM projects", conn)
        df = pd.DataFrame([
            ["", "Этап 1", "Обычная работа", "01.02.2025", "28.02.2025"],
        ], columns=["Проект", "Название этапа", "Тип этапа", "Дата начала", "Дата окончания"])
        succ, err = import_phases_core(conn, cur, df, projects_df, None)
        assert succ == 0
        assert any("пустое название проекта" in e for e in err)
        conn.close()

    def test_nan_dates(self):
        conn, cur = _make_memory_conn()
        cur.execute(
            "INSERT INTO projects (name, project_start, project_end, auto_dates) VALUES (?,?,?,?)",
            ("Proj1", "2025-01-01", "2025-12-31", 0),
        )
        conn.commit()
        projects_df = pd.read_sql("SELECT * FROM projects", conn)
        df = pd.DataFrame([
            ["Proj1", "Этап 1", "Обычная работа", float("nan"), "28.02.2025"],
        ], columns=["Проект", "Название этапа", "Тип этапа", "Дата начала", "Дата окончания"])
        succ, err = import_phases_core(conn, cur, df, projects_df, None)
        assert succ == 0
        assert any("даты" in e for e in err)
        conn.close()

    def test_project_not_found(self):
        conn, cur = _make_memory_conn()
        cur.execute(
            "INSERT INTO projects (name, project_start, project_end, auto_dates) VALUES (?,?,?,?)",
            ("Proj1", "2025-01-01", "2025-12-31", 0),
        )
        conn.commit()
        projects_df = pd.read_sql("SELECT * FROM projects", conn)
        df = pd.DataFrame([
            ["NoSuchProject", "Этап 1", "Обычная работа", "01.02.2025", "28.02.2025"],
        ], columns=["Проект", "Название этапа", "Тип этапа", "Дата начала", "Дата окончания"])
        succ, err = import_phases_core(conn, cur, df, projects_df, None)
        assert succ == 0
        assert any("не найден" in e for e in err)
        conn.close()

    def test_invalid_phase_type(self):
        conn, cur = _make_memory_conn()
        cur.execute(
            "INSERT INTO projects (name, project_start, project_end, auto_dates) VALUES (?,?,?,?)",
            ("Proj1", "2025-01-01", "2025-12-31", 0),
        )
        conn.commit()
        projects_df = pd.read_sql("SELECT * FROM projects", conn)
        df = pd.DataFrame([
            ["Proj1", "Этап 1", "Другое", "01.02.2025", "28.02.2025"],
        ], columns=["Проект", "Название этапа", "Тип этапа", "Дата начала", "Дата окончания"])
        succ, err = import_phases_core(conn, cur, df, projects_df, None)
        assert succ == 0
        assert any("тип этапа" in e for e in err)
        conn.close()

    def test_start_after_end(self):
        conn, cur = _make_memory_conn()
        cur.execute(
            "INSERT INTO projects (name, project_start, project_end, auto_dates) VALUES (?,?,?,?)",
            ("Proj1", "2025-01-01", "2025-12-31", 0),
        )
        conn.commit()
        projects_df = pd.read_sql("SELECT * FROM projects", conn)
        df = pd.DataFrame([
            ["Proj1", "Этап 1", "Обычная работа", "28.02.2025", "01.02.2025"],
        ], columns=["Проект", "Название этапа", "Тип этапа", "Дата начала", "Дата окончания"])
        succ, err = import_phases_core(conn, cur, df, projects_df, None)
        assert succ == 0
        assert any("дата начала позже" in e for e in err)
        conn.close()

    def test_auto_dates_callback_called(self):
        conn, cur = _make_memory_conn()
        cur.execute(
            "INSERT INTO projects (name, project_start, project_end, auto_dates) VALUES (?,?,?,?)",
            ("Proj1", "2020-01-01", "2030-12-31", 1),
        )
        conn.commit()
        projects_df = pd.read_sql("SELECT * FROM projects", conn)
        df = pd.DataFrame([
            ["Proj1", "Этап 1", "Обычная работа", "01.02.2025", "28.02.2025"],
        ], columns=["Проект", "Название этапа", "Тип этапа", "Дата начала", "Дата окончания"])
        called = []

        def track(proj_id):
            called.append(proj_id)

        succ, err = import_phases_core(conn, cur, df, projects_df, track)
        assert succ == 1
        assert called == [1]
        conn.close()


class TestImportPhaseAssignmentsCore:
    def test_missing_columns(self):
        conn, cur = _make_memory_conn()
        df = pd.DataFrame(columns=["Проект", "Сотрудник"])
        projects_df = pd.read_sql("SELECT * FROM projects", conn)
        phases_df = pd.read_sql("SELECT * FROM project_phases", conn)
        employees_df = pd.read_sql("SELECT * FROM employees", conn)
        succ, err = import_phase_assignments_core(conn, cur, df, projects_df, phases_df, employees_df)
        assert succ == 0
        assert any("Требуются колонки" in e for e in err)
        conn.close()

    def test_success_one_assignment(self):
        conn, cur = _make_memory_conn()
        cur.execute("INSERT INTO roles (name) VALUES (?)", ("Lead",))
        cur.execute("INSERT INTO employees (name, role_id) VALUES (?,?)", ("Ivan", 1))
        cur.execute(
            "INSERT INTO projects (name, project_start, project_end, auto_dates) VALUES (?,?,?,?)",
            ("Proj1", "2025-01-01", "2025-12-31", 0),
        )
        cur.execute(
            "INSERT INTO project_phases (project_id, name, phase_type, start_date, end_date) VALUES (?,?,?,?,?)",
            (1, "Этап 1", "Обычная работа", "2025-02-01", "2025-02-28"),
        )
        conn.commit()
        projects_df = pd.read_sql("SELECT * FROM projects", conn)
        phases_df = pd.read_sql("SELECT * FROM project_phases", conn)
        employees_df = pd.read_sql("SELECT * FROM employees", conn)
        df = pd.DataFrame([
            ["Proj1", "Этап 1", "Ivan", 50],
        ], columns=["Проект", "Название этапа", "Сотрудник", "Загрузка %"])
        succ, err = import_phase_assignments_core(conn, cur, df, projects_df, phases_df, employees_df)
        assert succ == 1
        assert len(err) == 0
        rows = cur.execute("SELECT * FROM phase_assignments").fetchall()
        assert len(rows) == 1
        # employee_id (column index 2) may be int or bytes depending on SQLite/settings
        eid = rows[0][2]
        assert eid == 1 or (isinstance(eid, bytes) and int.from_bytes(eid, "little") == 1)
        assert rows[0][3] == 50.0
        conn.close()

    def test_phase_not_found(self):
        conn, cur = _make_memory_conn()
        cur.execute("INSERT INTO roles (name) VALUES (?)", ("Lead",))
        cur.execute("INSERT INTO employees (name, role_id) VALUES (?,?)", ("Ivan", 1))
        cur.execute(
            "INSERT INTO projects (name, project_start, project_end, auto_dates) VALUES (?,?,?,?)",
            ("Proj1", "2025-01-01", "2025-12-31", 0),
        )
        cur.execute(
            "INSERT INTO project_phases (project_id, name, phase_type, start_date, end_date) VALUES (?,?,?,?,?)",
            (1, "Этап 1", "Обычная работа", "2025-02-01", "2025-02-28"),
        )
        conn.commit()
        projects_df = pd.read_sql("SELECT * FROM projects", conn)
        phases_df = pd.read_sql("SELECT * FROM project_phases", conn)
        employees_df = pd.read_sql("SELECT * FROM employees", conn)
        df = pd.DataFrame([
            ["Proj1", "Несуществующий этап", "Ivan", 50],
        ], columns=["Проект", "Название этапа", "Сотрудник", "Загрузка %"])
        succ, err = import_phase_assignments_core(conn, cur, df, projects_df, phases_df, employees_df)
        assert succ == 0
        assert any("этап" in e and "не найден" in e for e in err)
        conn.close()

    def test_duplicate_assignment(self):
        conn, cur = _make_memory_conn()
        cur.execute("INSERT INTO roles (name) VALUES (?)", ("Lead",))
        cur.execute("INSERT INTO employees (name, role_id) VALUES (?,?)", ("Ivan", 1))
        cur.execute(
            "INSERT INTO projects (name, project_start, project_end, auto_dates) VALUES (?,?,?,?)",
            ("Proj1", "2025-01-01", "2025-12-31", 0),
        )
        cur.execute(
            "INSERT INTO project_phases (project_id, name, phase_type, start_date, end_date) VALUES (?,?,?,?,?)",
            (1, "Этап 1", "Обычная работа", "2025-02-01", "2025-02-28"),
        )
        cur.execute("INSERT INTO phase_assignments (phase_id, employee_id, load_percent) VALUES (1, 1, 100)")
        conn.commit()
        projects_df = pd.read_sql("SELECT * FROM projects", conn)
        phases_df = pd.read_sql("SELECT * FROM project_phases", conn)
        employees_df = pd.read_sql("SELECT * FROM employees", conn)
        df = pd.DataFrame([
            ["Proj1", "Этап 1", "Ivan", 50],
        ], columns=["Проект", "Название этапа", "Сотрудник", "Загрузка %"])
        succ, err = import_phase_assignments_core(conn, cur, df, projects_df, phases_df, employees_df)
        assert succ == 0, err
        assert any("уже назначен" in e for e in err), err
        conn.close()
