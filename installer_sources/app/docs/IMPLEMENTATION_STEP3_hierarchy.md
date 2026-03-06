# Реализация плана — Пункт 3: Иерархия этапов при импорте из XML

## Статус: Выполнено

## Краткое содержание

**Цель:** При импорте из MS Project (XML) выстраивать иерархию этапов/подэтапов в соответствии с файлом (OutlineLevel), сохранять связь родитель–потомок в БД и считать сроки проекта и верхнеуровневых задач по иерархии.

**Сделано:**

1. **Схема БД**
   - В таблицу `project_phases` добавлена колонка `parent_id INTEGER NULL REFERENCES project_phases(id)` (миграция в `database.run_migrations`).

2. **Репозиторий**
   - `load_phases`: чтение и приведение `parent_id` (int или None).
   - `insert_phase`: добавлен параметр `parent_id: Optional[int] = None`; возвращает `lastrowid` для построения маппинга UID → phase_id при импорте.
   - `update_phase`: добавлен параметр `parent_id: Optional[int] = None`; при переданном значении обновляется колонка.

3. **Построение иерархии в XML (msproject_import)**
   - `_compute_parent_uid_for_tasks(tasks)`: по порядку задач и полю OutlineLevel проставляет каждой задаче `parent_uid` (UID последней предыдущей задачи с уровнем на 1 меньше).
   - `_fill_summary_dates_from_children(tasks)`: для сводных задач (Summary=1) без дат вычисляет Start/Finish как min/max дат по всем потомкам.

4. **build_project_and_phases_from_mspdi**
   - При `only_leaf_tasks=False`: в этапы попадают все задачи с OutlineLevel >= 1; для каждой задаче задаётся parent_uid; даты сводных при отсутствии считаются по дочерним; этапы возвращаются в порядке «родитель перед детьми» (сортировка по outline_level и исходному индексу в XML) с полями `uid` и `parent_uid`.
   - При `only_leaf_tasks=True`: поведение без изменений (плоский список без uid/parent_uid).

5. **import_mspdi_project_and_phases**
   - Вставка этапов через `repository.insert_phase` с передачей `parent_id`; ведётся маппинг `uid_to_phase_id` для проставления parent_id дочерних этапов. После вставки по-прежнему вызывается `update_project_dates_from_phases` (срок проекта = min/max по всем этапам).

6. **import_mspdi_assignments**
   - Маппинг TaskUID → phase_id при иерархии строится по порядку этапов из `build_project_and_phases_from_mspdi` (совпадает с порядком вставки в БД). Цикл по назначениям из поля «Исполнитель» использует общий список `executor_items` (phase_id, executor), формируемый из `phases_list_for_order` или из `_filter_phase_tasks` в зависимости от режима.

7. **Тесты**
   - В тестовой БД (`_make_mspdi_conn`) в таблицу `project_phases` добавлена колонка `parent_id`.

## Изменённые файлы

- **database.py** — миграция: добавление `parent_id` в `project_phases`.
- **repository.py** — `load_phases` (parent_id), `insert_phase` (parent_id, возврат lastrowid), `update_phase` (parent_id).
- **msproject_import.py** — функции иерархии, новая логика `build_project_and_phases_from_mspdi`, вставка этапов с parent_id, обновлённый маппинг в `import_mspdi_assignments`.
- **installer_sources**: те же изменения в database, repository, msproject_import.
- **tests/test_msproject_import.py** — схема тестовой БД с `parent_id`.

## Проверка

При импорте XML с несколькими уровнями (например, фаза уровня 1 и подзадачи уровня 2) без опции «только листовые» в БД создаются этапы с заполненным `parent_id`; даты сводных задач и проекта соответствуют min/max по дочерним/всем этапам.
