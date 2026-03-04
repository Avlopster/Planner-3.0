# Результаты выполнения рефакторинга Planner

Результаты тестирования после каждого этапа из [REFACTORING_EXECUTION.md](REFACTORING_EXECUTION.md).

---

## Этап 1.1 — config.py

- **Дата:** 26.02.2026
- **Тестирование:** Импорт Planner с config выполнен успешно (`python -c "import Planner; print('OK')"`).
- **Замечания:** Используется `import config as app_config` во избежание конфликта с функцией get_config.

---

## Этап 1.2 — utils/date_utils.py

- **Дата:** 26.02.2026
- **Тестирование:** 67 тестов пройдено (pytest tests/ -v). В Planner используется date_range_list из utils.date_utils. В тестовой схеме test_excel_import добавлена колонка completion_percent для project_phases.
- **Замечания:** Парсинг дат в excel_import переведён на date_utils в этапе 4.

---

## Этап 2 — database.py

- **Дата:** 26.02.2026
- **Тестирование:** Импорт Planner успешен; 67 тестов пройдено. Схема и миграции вынесены в database.py; bare except заменены на (ValueError, TypeError) и sqlite3.OperationalError.
- **Замечания:** Плейсхолдеры дат в миграциях берутся из app_config.

---

## Этап 3 — repository.py и load_calculator / capacity

- **Дата:** 26.02.2026
- **Тестирование:** 67 тестов пройдено; импорт Planner успешен. Вынесены repository.py, load_calculator.py, capacity.py; delete_employee/delete_role возвращают (success, message), UI выводит st.error при ошибке.
- **Замечания:** Константы (ACTIVE_STATUSES и др.) берутся из app_config; один вызов ACTIVE_STATUSES в Planner заменён на app_config.ACTIVE_STATUSES.

---

## Этап 4 — excel_import

- **Дата:** 26.02.2026
- **Тестирование:** 16 тестов test_excel_import пройдено; парсинг дат этапов переведён на utils.date_utils.parse_date_from_excel.
- **Замечания:** Конфиг в excel_import не используется (достаточно date_utils для этапов).

---

## Этап 5 — components.py и pages/

- **Дата:** 26.02.2026
- **Тестирование:** 67 тестов пройдено (pytest tests/ -v). Импорт всех страниц успешен. Planner.py — только точка входа, меню и диспетчер по `st.session_state.menu`; каждый раздел вынесен в `pages/*.py` с `render(conn)`.
- **Замечания:** Созданы: `components.py` (ru_date_picker, menu_button); `pages/dashboard.py`, `roles.py`, `employees.py`, `vacations.py`, `projects.py`, `import_excel.py`, `analytics.py`, `gantt.py`, `calendar.py`, `config_page.py`, `clear_data.py`. Логика импорта из Excel (шаблоны и import_* по сущностям) вынесена в `excel_import_ui.py`; страница «Импорт из Excel» использует её с `conn`. Календарь импортируется как `calendar as calendar_page` во избежание конфликта с stdlib.

---

## Этап 6 — типы и docstrings

- **Дата:** 26.02.2026
- **Тестирование:** 67 тестов пройдено; линтер без ошибок.
- **Замечания:** Добавлены type hints и docstrings в: utils/date_utils.py (parse_date_from_excel, normalize_date, date_range_list), components.py (ru_date_picker, menu_button), repository.py (_safe_int, _safe_date_series), capacity.py (annual_project_capacity), load_calculator.py (_working_days_in_range, get_average_vacation_days_per_employee, employee_load_by_day, department_load_summary, overload_shortfall, get_employee_load_sources_by_day), excel_import_ui.py (все функции импорта и download_template).

---

## Этап 7 — замена bare except

- **Дата:** 26.02.2026
- **Тестирование:** Поиск `except:` по коду — совпадений в .py нет (bare except отсутствуют).
- **Замечания:** В load_calculator.get_average_vacation_days_per_employee заменён `except Exception` на `except (ValueError, TypeError)` при разборе дат отпусков. В utils/date_utils.normalize_date — `except Exception` заменён на `except (ValueError, TypeError)`.

---

## Этап 8 — тесты под новую функциональность

- **Дата:** 26.02.2026
- **Тестирование:** 67 тестов пройдено (pytest tests/ -v). Существующие тесты покрывают: дашборд (статусы, команды, сроки, неполные проекты, этапы), excel_import (нормализация типов этапов, import_phases_core, import_phase_assignments_core), date_utils (normalize_date), load_calculator (sources, phases, candidates), репозиторий (vacation overlap, department_load_summary, annual capacity, Гант — высота, фильтр активных, мультиселект, gantt_project_completion_percent).
- **Замечания:** Дополнительные интеграционные тесты страниц не добавлялись; импорт всех модулей pages проверяется при запуске приложения.

---

## Этап 9 — Makefile и Planner.md

- **Дата:** 26.02.2026
- **Тестирование:** Makefile присутствует (цели run, install, test). При наличии make: `make test`, `make run`; иначе: `pytest tests/ -v`, `python -m streamlit run Planner.py`. В Planner.md добавлен раздел «Структура проекта» с перечислением модулей (config, database, repository, load_calculator, capacity, excel_import, excel_import_ui, utils/date_utils, components, pages/*).
- **Замечания:** Документация приведена в соответствие с фактической структурой после этапа 5.

---

## Актуализация документации (26.02.2026)

- **Обновлены:** Planner.md (структура: одно подключение к БД на сессию в `st.session_state["_db_conn"]`; config: путь к БД абсолютный относительно каталога проекта; модель данных: справочник `project_statuses`, таблица `projects.status_id`; миграции; раздел «Интерфейс» — подключение к БД; раздел «Проекты и этапы» — сохранение статуса), What's new.md (блок «Сохранение статуса проекта и единое подключение к БД»), logic.md (п. 9 и 10.2 — статус проектов через `status_name` из JOIN с `project_statuses`), test.md (п. 8.1 — сохранение статуса проекта после «Обновить данные» и на дашборде).
- **Причина:** исправление сохранения статуса проекта (одно подключение на сессию, путь к БД в config относительно каталога проекта).

---

## Рефакторинг по Analyze_Plan (п. 3 и п. 5)

**Дата:** 27.02.2026  
**План:** [.cursor/plans/Analyze_Plan.md](../.cursor/plans/Analyze_Plan.md). Вариант A для п. 4 (оптимизация в рамках Streamlit).

### Выполненные изменения

- **3.1 database.py:** сужен `except Exception` до `sqlite3.OperationalError` при WAL checkpoint; добавлены индексы `idx_projects_status`, `idx_projects_dates`.
- **3.2 repository.py + utils/type_utils.py:** вынесены `safe_int` и `safe_date_series` (с поддержкой bytes) в `utils/type_utils.py`; `get_employee_name` и `get_project_name` переведены на точечные запросы по id; в repository используется общий type_utils.
- **3.3 load_calculator.py:** добавлена `employee_load_by_day_batch(conn, employee_ids, start_date, end_date)`; `department_load_summary` и `overload_shortfall` переведены на один батч по всем сотрудникам.
- **3.4 capacity.py:** сужен `except Exception` до `(ValueError, TypeError)` при разборе дат; добавлены проверки на пустой DataFrame и наличие колонок `role_id`/`role_name`.
- **3.5 Planner.py:** удалены локальные `_safe_int`/`_safe_date_series`, используется `utils.type_utils.safe_int`; кешируемые функции принимают аргумент `db_path` для ключа кеша.
- **3.6 app_pages:** в dashboard, employees, gantt, projects используется `safe_int` из `utils.type_utils`; аналитика переведена на один вызов `employee_load_by_day_batch` и построение графиков/отчёта перегрузок из результата; в projects добавлен комментарий о пересоздании conn после rerun и сужен except до `sqlite3.OperationalError`.
- **3.7 excel_import_ui.py:** при создании новой роли при импорте сотрудников локальный `roles_df` дополняется новой строкой вместо полной перезагрузки из БД.
- **3.8 Тесты:** в test_planner используются `utils.date_utils.date_range_list` и `utils.type_utils.safe_int`; добавлен `tests/test_load_calculator.py` с интеграционными тестами (in-memory SQLite) для `employee_load_by_day`, `employee_load_by_day_batch`, `department_load_summary`.
- **5. Дополнительно:** в `requirements.txt` заданы верхние границы (`pandas`, `streamlit` <3); результаты тестов зафиксированы в [testres.md](../testres.md).

### Тестирование

- **Команда:** `python -m pytest tests/ -v`
- **Результат:** 96 passed. Сводка — в [testres.md](../testres.md).

---

## Рефакторинг Planner 3.0 (март 2025)

План: [REFACTORING_STAGES.md](REFACTORING_STAGES.md). Выполнены этапы 0–8.

### Этап 1 — Безопасность sql_runner

- По умолчанию выполняются только запросы на чтение (SELECT, PRAGMA). Для INSERT/UPDATE/DELETE требуется чекбокс «Разрешить изменение данных».
- Добавлена проверка первого токена запроса (`_is_read_only_statement`); текст запроса не логируется.

### Этап 2 — Слой данных: этапы и назначения

- В `repository.py` добавлены: `insert_project`, `add_project_juniors`, `update_project`, `get_project_status_id`, `delete_phase`, `insert_phase`, `update_phase`.
- Вся работа с БД по проектам/этапам/назначениям в `app_pages/projects.py` переведена на вызовы repository (прямые SQL удалены).

### Этап 3 — Мутация конфига

- `database.get_connection()` возвращает `(conn, actual_path)` и больше не изменяет `app_config.DB_PATH`. Фактический путь (в т.ч. fallback) хранится в `st.session_state["_db_path"]` и передаётся в `projects.render(conn, db_path=_db_path)`.

### Этап 4 — Точка входа Planner.py

- Удалены неиспользуемые обёртки и кеш (`load_roles`, `load_employees`, … и все делегирующие функции). Страницы вызывают `repository` и `load_calculator`/`capacity` напрямую.
- Planner.py сведён к: инициализация логов и БД, меню, роутинг по `st.session_state.menu`.

### Этап 5 — DRY в load_calculator

- Выделены общие хелперы: `_to_date`, `_project_bounds`, `_find_day_phase`, `_load_for_day_from_phase`. Функции `employee_load_by_day` и `employee_load_by_day_batch` переписаны с их использованием (устранено дублирование логики дат и этапов).

### Этап 6 — Поддерживаемость projects.py

- Разбиение длинной страницы на подфункции: `_render_new_project_form`, `_render_project_header`, `_render_phases_section`. Функция `render()` сокращена и читается по шагам.

### Этап 7 — Тесты

- Тесты пересечения отпусков переведены на `repository.check_vacation_overlap` с in-memory БД (хелпер `_vacation_conn`). Добавлены классы `TestPhaseCrud` (insert/load, update, delete этапов) и `TestLoadCalculator` (employee_load_by_day и batch при пустой БД).

### Этап 8 — Качество кода

- Добавлен `pyproject.toml` с настройками black (line-length 120), isort (profile black), ruff (E, F, I, W). Для всех страниц app_pages добавлены docstrings у `render(conn)` (назначение страницы и параметр conn).

### Тестирование

- **Команда:** `python -m pytest tests/ -q`
- **Результат:** 126 passed, 1 skipped.
