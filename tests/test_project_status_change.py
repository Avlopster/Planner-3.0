# -*- coding: utf-8 -*-
"""Тест смены статуса проекта: В работе -> Планируется.
Проверяет: обновление в БД, отображение в load_projects (список проектов), счётчики на Дашборде."""
import os
import sys
import sqlite3

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as app_config
import database as db
import repository


def _dashboard_status_counts(df_projects):
    """Логика KPI Дашборда по статусам (как в app_pages/dashboard.py)."""
    if df_projects.empty:
        return {'В работе': 0, 'Планируется': 0, 'Завершён': 0, 'Отменён': 0, 'Всего': 0}
    status_fill = df_projects['status_name'].fillna('В работе')
    status_counts = status_fill.value_counts()
    return {
        'В работе': int(status_counts.get('В работе', 0)) if 'В работе' in status_counts.index else 0,
        'Планируется': int(status_counts.get('Планируется', 0)) if 'Планируется' in status_counts.index else 0,
        'Завершён': int(status_counts.get('Завершён', 0)) if 'Завершён' in status_counts.index else 0,
        'Отменён': int(status_counts.get('Отменён', 0)) if 'Отменён' in status_counts.index else 0,
        'Всего': len(df_projects),
    }


@pytest.fixture(scope="module")
def conn():
    path = getattr(app_config, 'DB_PATH', 'resource_planner.db')
    conn = sqlite3.connect(path)
    db.init_schema(conn)
    db.run_migrations(conn)
    yield conn
    conn.close()


def test_project_status_change_in_progress_to_planned(conn):
    """Смена статуса проекта с «В работе» на «Планируется»:
    - в БД projects.status_id обновляется;
    - load_projects возвращает новый status_name;
    - в списке проектов в квадратных скобках отображается «Планируется»;
    - на Дашборде счётчик «В работе» уменьшается, «Планируется» увеличивается."""
    cur = conn.cursor()
    id_in_progress = repository.get_status_id_by_code(conn, 'in_progress')
    id_planned = repository.get_status_id_by_code(conn, 'planned')
    assert id_in_progress is not None, "В справочнике должен быть статус in_progress"
    assert id_planned is not None, "В справочнике должен быть статус planned"

    df_before = repository.load_projects(conn)
    counts_before = _dashboard_status_counts(df_before)

    # Найти проект со статусом «В работе» (или первый проект и перевести его в «В работе» для теста)
    proj_in_work = df_before[(df_before['status_name'].fillna('В работе') == 'В работе')]
    if proj_in_work.empty:
        # Нет проектов «В работе» — взять любой проект и поставить «В работе», затем сменить на «Планируется»
        if df_before.empty:
            pytest.skip("В БД нет проектов — создайте проект вручную и повторите тест")
        proj_id = int(df_before.iloc[0]['id'])
        cur.execute("UPDATE projects SET status_id = ? WHERE id = ?", (id_in_progress, proj_id))
        conn.commit()
        in_work_before = counts_before.get('В работе', 0)
        planned_before = counts_before.get('Планируется', 0)
        # после принудительной установки «В работе» пересчитаем
        df_before = repository.load_projects(conn)
        counts_before = _dashboard_status_counts(df_before)
    else:
        proj_id = int(proj_in_work.iloc[0]['id'])
        in_work_before = counts_before['В работе']
        planned_before = counts_before['Планируется']

    # Действие: сменить статус на «Планируется»
    cur.execute("UPDATE projects SET status_id = ? WHERE id = ?", (id_planned, proj_id))
    conn.commit()

    # 1) В БД поле status_id обновлено
    row = cur.execute("SELECT status_id FROM projects WHERE id = ?", (proj_id,)).fetchone()
    assert row is not None
    assert int(row[0]) == id_planned, "В таблице projects поле status_id должно быть id статуса «Планируется»"

    # 2) load_projects возвращает status_name «Планируется» для этого проекта
    df_after = repository.load_projects(conn)
    proj_after = df_after[df_after['id'] == proj_id].iloc[0]
    assert proj_after['status_name'] == 'Планируется', (
        "В списке проектов (и в наименовании в квадратных скобках) должен отображаться статус «Планируется»"
    )

    # 3) Дашборд: «В работе» уменьшился на 1, «Планируется» увеличился на 1
    counts_after = _dashboard_status_counts(df_after)
    assert counts_after['В работе'] == in_work_before - 1, (
        "На Дашборде колонка «В работе» должна уменьшиться на 1"
    )
    assert counts_after['Планируется'] == planned_before + 1, (
        "На Дашборде колонка «Планируется» должна увеличиться на 1"
    )

    # Вернуть статус обратно, чтобы не менять данные пользователя
    cur.execute("UPDATE projects SET status_id = ? WHERE id = ?", (id_in_progress, proj_id))
    conn.commit()
