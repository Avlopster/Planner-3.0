# -*- coding: utf-8 -*-
"""Тесты парсинга и импорта из MS Project (MSPDI XML)."""
from __future__ import annotations

import os
import sys
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import msproject_import

NS = "http://schemas.microsoft.com/project"


def _mspdi_root(
    title: str = "Test Project",
    start_date: str = "2026-01-01T09:00:00",
    finish_date: str = "2026-12-31T18:00:00",
    tasks_xml: str = "",
    resources_xml: str = "",
    assignments_xml: str = "",
) -> ET.Element:
    """Собирает минимальный корень MSPDI из фрагментов."""
    xml_str = f"""<?xml version="1.0" encoding="UTF-8"?>
<Project xmlns="{NS}">
  <Title>{title}</Title>
  <StartDate>{start_date}</StartDate>
  <FinishDate>{finish_date}</FinishDate>
  <Tasks>{tasks_xml}</Tasks>
  <Resources>{resources_xml}</Resources>
  <Assignments>{assignments_xml}</Assignments>
</Project>"""
    return ET.fromstring(xml_str)


def _task_xml(uid: int, name: str, outline_level: int, summary: int, start: str, finish: str, percent: int = 0, executor: str | None = None) -> str:
    ext = ""
    if executor:
        ext = f"""
        <ExtendedAttribute>
          <FieldID>188743731</FieldID>
          <Value>{executor}</Value>
        </ExtendedAttribute>"""
    return f"""
    <Task>
      <UID>{uid}</UID>
      <Name>{name}</Name>
      <OutlineLevel>{outline_level}</OutlineLevel>
      <Summary>{summary}</Summary>
      <Start>{start}</Start>
      <Finish>{finish}</Finish>
      <PercentComplete>{percent}</PercentComplete>{ext}
    </Task>"""


def _resource_xml(uid: int, name: str) -> str:
    return f"""
    <Resource>
      <UID>{uid}</UID>
      <Name>{name}</Name>
    </Resource>"""


def _assignment_xml(task_uid: int, resource_uid: int, units: float = 1.0) -> str:
    return f"""
    <Assignment>
      <TaskUID>{task_uid}</TaskUID>
      <ResourceUID>{resource_uid}</ResourceUID>
      <Units>{units}</Units>
    </Assignment>"""


class TestParseProjectMeta:
    def test_returns_title_and_dates(self):
        root = _mspdi_root(title="Катока", start_date="2026-06-01T09:00:00", finish_date="2029-03-19T18:00:00")
        meta = msproject_import.parse_project_meta(root)
        assert meta["title"] == "Катока"
        assert meta["start_date"] == "2026-06-01"
        assert meta["finish_date"] == "2029-03-19"

    def test_empty_elements_return_none(self):
        root = ET.fromstring(f'<Project xmlns="{NS}"><Tasks/><Resources/><Assignments/></Project>')
        meta = msproject_import.parse_project_meta(root)
        assert meta["title"] is None
        assert meta["start_date"] is None
        assert meta["finish_date"] is None


class TestParseTasks:
    def test_parses_tasks_with_executor(self):
        tasks_xml = _task_xml(0, "Proj", 0, 1, "2026-01-01T09:00:00", "2026-12-31T18:00:00") + _task_xml(
            1, "Phase 1", 1, 0, "2026-01-01T09:00:00", "2026-01-15T18:00:00", executor="Иванов, Петров"
        )
        root = _mspdi_root(tasks_xml=tasks_xml, resources_xml="", assignments_xml="")
        tasks = msproject_import.parse_tasks(root)
        assert len(tasks) == 2
        assert tasks[0]["UID"] == 0
        assert tasks[0]["Name"] == "Proj"
        assert tasks[0]["OutlineLevel"] == 0
        assert tasks[0]["Start"] == "2026-01-01"
        assert tasks[0]["Finish"] == "2026-12-31"
        assert tasks[0].get("executor") is None
        assert tasks[1]["UID"] == 1
        assert tasks[1]["Name"] == "Phase 1"
        assert tasks[1]["executor"] == "Иванов, Петров"

    def test_empty_tasks(self):
        root = _mspdi_root(tasks_xml="", resources_xml="", assignments_xml="")
        tasks = msproject_import.parse_tasks(root)
        assert tasks == []


class TestParseResources:
    def test_parses_resources(self):
        resources_xml = _resource_xml(1, "Иванов") + _resource_xml(2, "Петров")
        root = _mspdi_root(tasks_xml="", resources_xml=resources_xml, assignments_xml="")
        resources = msproject_import.parse_resources(root)
        assert len(resources) == 2
        assert resources[0]["UID"] == 1 and resources[0]["Name"] == "Иванов"
        assert resources[1]["UID"] == 2 and resources[1]["Name"] == "Петров"

    def test_empty_resources(self):
        root = _mspdi_root(tasks_xml="", resources_xml="", assignments_xml="")
        resources = msproject_import.parse_resources(root)
        assert resources == []


class TestParseAssignments:
    def test_parses_assignments(self):
        assignments_xml = _assignment_xml(1, 1, 1.0) + _assignment_xml(1, 2, 0.5)
        root = _mspdi_root(tasks_xml="", resources_xml="", assignments_xml=assignments_xml)
        assignments = msproject_import.parse_assignments(root)
        assert len(assignments) == 2
        assert assignments[0]["TaskUID"] == 1 and assignments[0]["ResourceUID"] == 1 and assignments[0]["Units"] == 1.0
        assert assignments[1]["TaskUID"] == 1 and assignments[1]["ResourceUID"] == 2 and assignments[1]["Units"] == 0.5

    def test_empty_assignments(self):
        root = _mspdi_root(tasks_xml="", resources_xml="", assignments_xml="")
        assignments = msproject_import.parse_assignments(root)
        assert assignments == []


class TestBuildProjectAndPhasesFromMspdi:
    def test_project_name_from_title(self):
        tasks_xml = _task_xml(0, "Root", 0, 1, "2026-01-01T09:00:00", "2026-12-31T18:00:00")
        root = _mspdi_root(title="Катока", tasks_xml=tasks_xml)
        project_dict, phases_list = msproject_import.build_project_and_phases_from_mspdi(root, only_leaf_tasks=False)
        assert project_dict["name"] == "Катока"
        assert project_dict["start_date"] == "2026-01-01"
        assert project_dict["finish_date"] == "2026-12-31"
        assert len(phases_list) == 0

    def test_phases_includes_all_with_outline_level_ge_1(self):
        tasks_xml = (
            _task_xml(0, "Proj", 0, 1, "2026-01-01T09:00:00", "2026-12-31T18:00:00")
            + _task_xml(1, "Phase 1", 1, 1, "2026-01-01T09:00:00", "2026-06-30T18:00:00")
            + _task_xml(2, "Phase 2", 2, 0, "2026-02-01T09:00:00", "2026-02-28T18:00:00")
        )
        root = _mspdi_root(tasks_xml=tasks_xml)
        project_dict, phases_list = msproject_import.build_project_and_phases_from_mspdi(root, only_leaf_tasks=False)
        assert len(phases_list) == 2
        assert phases_list[0]["name"] == "Phase 1"
        assert phases_list[1]["name"] == "Phase 2"
        assert phases_list[1]["completion_percent"] == 0

    def test_only_leaf_tasks_excludes_summary(self):
        tasks_xml = (
            _task_xml(0, "Proj", 0, 1, "2026-01-01T09:00:00", "2026-12-31T18:00:00")
            + _task_xml(1, "Summary", 1, 1, "2026-01-01T09:00:00", "2026-06-30T18:00:00")
            + _task_xml(2, "Leaf", 2, 0, "2026-02-01T09:00:00", "2026-02-28T18:00:00")
        )
        root = _mspdi_root(tasks_xml=tasks_xml)
        _, phases_list = msproject_import.build_project_and_phases_from_mspdi(root, only_leaf_tasks=True)
        assert len(phases_list) == 1
        assert phases_list[0]["name"] == "Leaf"


def _make_mspdi_conn() -> sqlite3.Connection:
    """In-memory DB с проектами, этапами, статусами, сотрудниками для тестов MSPDI."""
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute("CREATE TABLE roles (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL)")
    cur.execute("INSERT INTO roles (id, name) VALUES (1, 'Роль')")
    cur.execute(
        "CREATE TABLE employees (id INTEGER PRIMARY KEY, name TEXT NOT NULL, role_id INTEGER)"
    )
    cur.execute("INSERT INTO employees (id, name, role_id) VALUES (1, 'Иванов', 1), (2, 'Петров', 1)")
    cur.execute(
        """CREATE TABLE project_statuses (
           id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
           is_active BOOLEAN DEFAULT 1, is_gantt_active BOOLEAN DEFAULT 0)"""
    )
    cur.execute(
        "INSERT INTO project_statuses (id, code, name, is_active, is_gantt_active) VALUES (1, 'in_progress', 'В работе', 1, 0)"
    )
    cur.execute(
        """CREATE TABLE projects (
           id INTEGER PRIMARY KEY, name TEXT NOT NULL, client_company TEXT, lead_id INTEGER,
           lead_load_percent REAL DEFAULT 50, project_start DATE NOT NULL, project_end DATE NOT NULL,
           auto_dates BOOLEAN DEFAULT 0, status_id INTEGER)"""
    )
    cur.execute(
        """CREATE TABLE project_phases (
           id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, name TEXT NOT NULL,
           phase_type TEXT NOT NULL, start_date DATE NOT NULL, end_date DATE NOT NULL,
           completion_percent INTEGER DEFAULT 0)"""
    )
    cur.execute(
        """CREATE TABLE phase_assignments (
           id INTEGER PRIMARY KEY, phase_id INTEGER NOT NULL, employee_id INTEGER NOT NULL,
           load_percent REAL NOT NULL)"""
    )
    conn.commit()
    return conn


class TestImportMspdiProjectAndPhases:
    def test_creates_project_and_phases(self):
        tasks_xml = (
            _task_xml(0, "Proj", 0, 1, "2026-01-01T09:00:00", "2026-12-31T18:00:00")
            + _task_xml(1, "Phase 1", 1, 0, "2026-01-01T09:00:00", "2026-01-15T18:00:00", percent=10)
        )
        root = _mspdi_root(title="Import Project", tasks_xml=tasks_xml)
        conn = _make_mspdi_conn()
        project_id, phases_count, errors = msproject_import.import_mspdi_project_and_phases(conn, root, only_leaf_tasks=False)
        assert project_id is not None
        assert phases_count == 1
        row = conn.execute("SELECT name, project_start, project_end FROM projects WHERE id = ?", (project_id,)).fetchone()
        assert row[0] == "Import Project"
        assert row[1] == "2026-01-01"
        # После update_project_dates_from_phases даты проекта берутся из этапов (min/max)
        assert row[2] == "2026-01-15"
        phase_row = conn.execute("SELECT name, completion_percent FROM project_phases WHERE project_id = ?", (project_id,)).fetchone()
        assert phase_row[0] == "Phase 1"
        assert phase_row[1] == 10
        conn.close()


class TestImportMspdiAssignments:
    def test_assignments_from_executor_and_resources(self):
        tasks_xml = (
            _task_xml(0, "Proj", 0, 1, "2026-01-01T09:00:00", "2026-12-31T18:00:00")
            + _task_xml(1, "Phase 1", 1, 0, "2026-01-01T09:00:00", "2026-01-15T18:00:00", executor="Иванов, Петров")
        )
        resources_xml = _resource_xml(1, "Иванов")
        assignments_xml = _assignment_xml(1, 1, 0.5)
        root = _mspdi_root(tasks_xml=tasks_xml, resources_xml=resources_xml, assignments_xml=assignments_xml)
        conn = _make_mspdi_conn()
        project_id, _, _ = msproject_import.import_mspdi_project_and_phases(conn, root, only_leaf_tasks=False)
        assert project_id is not None
        success, err = msproject_import.import_mspdi_assignments(conn, root, project_id, only_leaf_tasks=False)
        assert success >= 1
        rows = conn.execute("SELECT COUNT(*) FROM phase_assignments").fetchone()[0]
        assert rows >= 1
        conn.close()


@pytest.mark.skipif(
    not Path(r"d:\NextCloud\Проектный офис\Проекты_Project\Катока 2026-2028.xml").exists(),
    reason="Файл Катока 2026-2028.xml отсутствует",
)
class TestMspdiRealFileKatoka:
    def test_build_from_real_file(self):
        path = Path(r"d:\NextCloud\Проектный офис\Проекты_Project\Катока 2026-2028.xml")
        root = msproject_import.read_mspdi_file(str(path))
        meta = msproject_import.parse_project_meta(root)
        assert meta.get("title") == "Катока" or "Катока" in (meta.get("title") or "")
        tasks = msproject_import.parse_tasks(root)
        assert len(tasks) > 0
        project_dict, phases_list = msproject_import.build_project_and_phases_from_mspdi(root, only_leaf_tasks=False)
        assert project_dict["name"]
        assert len(phases_list) > 0
