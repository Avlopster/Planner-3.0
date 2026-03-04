# Пошаговый документ выполнения рефакторинга Planner

Документ задаёт порядок выполнения плана рефакторинга (модульная структура + исправление проблем из таблицы 3 + тесты). После каждого пункта проводится тестирование и результат фиксируется в [REFACTORING_RESULTS.md](REFACTORING_RESULTS.md).

---

## Этап 1.1 — config.py

- **Задача:** Создать `config.py` с константами: DB_PATH, магические числа (247, 28, 30, 0.25, 4), плейсхолдеры дат (DATE_PLACEHOLDER_START, DATE_PLACEHOLDER_END), MONTHS_RU, типы этапов, защищённые роли и т.д.
- **Файлы:** новый `config.py`.
- **Критерий завершения:** Импорт config в Planner не ломает запуск приложения.
- **Тестирование:** `streamlit run Planner.py`, открыть приложение в браузере.
- **Фиксация:** Записать результат в REFACTORING_RESULTS.md.

---

## Этап 1.2 — utils/date_utils.py

- **Задача:** Создать `utils/date_utils.py` с функциями `parse_date_from_excel`, `date_range_list`; при необходимости подключить использование в импортах/парсинге.
- **Файлы:** `utils/date_utils.py`, при необходимости правки в Planner.py и excel_import.py.
- **Критерий завершения:** Парсинг дат идёт через date_utils; тесты импорта проходят.
- **Тестирование:** `pytest tests/ -v`, ручная проверка импорта из Excel.
- **Фиксация:** Записать результат в REFACTORING_RESULTS.md.

---

## Этап 2 — database.py

- **Задача:** Вынести схему БД и миграции в `database.py`; заменить bare `except:` в миграциях на конкретные исключения (sqlite3.OperationalError, ValueError, TypeError).
- **Файлы:** `database.py`, `Planner.py`.
- **Критерий завершения:** БД инициализируется и мигрирует без bare except; Planner использует database.get_connection, init_schema, run_migrations.
- **Тестирование:** Первый запуск (чистая БД), повторный запуск с существующей БД; `pytest tests/ -v`.
- **Фиксация:** Записать результат в REFACTORING_RESULTS.md.

---

## Этап 3 — repository.py и load_calculator / capacity

- **Задача:** Вынести в `repository.py` все load_*, CRUD, get_*, delete_* (с возвратом (success, message)); в `load_calculator.py` — department_load_summary, employee_load_by_day и связанные; в `capacity.py` или load_calculator — annual_project_capacity, overload_shortfall.
- **Файлы:** `repository.py`, `load_calculator.py`, при необходимости `capacity.py`, `Planner.py`.
- **Критерий завершения:** Все вызовы идут из repository / load_calculator / capacity; delete_* не вызывают st.error напрямую.
- **Тестирование:** `streamlit run Planner.py`, сценарии: роли, сотрудники, проекты, этапы, дашборд, аналитика (Прогноз, экспорт Excel).
- **Фиксация:** Записать результат в REFACTORING_RESULTS.md.

---

## Этап 4 — excel_import

- **Задача:** Подключить в excel_import использование `utils.date_utils` и конфига; оставить ядро без Streamlit.
- **Файлы:** `excel_import.py`.
- **Критерий завершения:** Тесты test_excel_import проходят; импорт из UI работает.
- **Тестирование:** `pytest tests/test_excel_import.py -v`, ручной импорт через приложение.
- **Фиксация:** Записать результат в REFACTORING_RESULTS.md.

---

## Этап 5 — components.py и pages/

- **Задача:** Вынести в `components.py` ru_date_picker, menu_button; вынести в `pages/` дашборд, аналитику, Гант (готовность, фильтры, мультиселект), календарь, проекты, роли, сотрудники, отпуска, импорт, очистку данных.
- **Файлы:** `components.py`, `pages/*.py`, `Planner.py`.
- **Критерий завершения:** Planner.py — только точка входа и диспетчер по menu; все сценарии работают.
- **Тестирование:** Полный прогон сценариев по test.md разд. 8.1 (дашборд, аналитика, Гант с заливкой и фильтрами, экспорт, Прогноз).
- **Фиксация:** Записать результат в REFACTORING_RESULTS.md.

---

## Этап 6 — типы и docstrings (по возможности)

- **Задача:** Добавить type hints и краткие docstrings в ключевые функции новых модулей.
- **Файлы:** config.py, database.py, repository.py, load_calculator.py, capacity.py, utils/date_utils.py, components.py, pages/*.py.
- **Критерий завершения:** Публичные функции имеют аннотации типов и описание.
- **Тестирование:** `pytest tests/ -v`, `streamlit run Planner.py`.
- **Фиксация:** Записать результат в REFACTORING_RESULTS.md.

---

## Этап 7 — замена оставшихся bare except

- **Задача:** Убедиться, что в коде нет bare `except:` (миграции и парсинг исправлены в этапах 2 и 1.2); при необходимости исправить оставшиеся места.
- **Файлы:** Все изменённые модули.
- **Критерий завершения:** Поиск по коду `except:` не находит неконкретных перехватов.
- **Тестирование:** `pytest tests/ -v`, `streamlit run Planner.py`.
- **Фиксация:** Записать результат в REFACTORING_RESULTS.md.

---

## Этап 8 — тесты под новую функциональность и структуру

- **Задача:** Сформировать и провести тесты согласно новой внедрённой функциональности (годовая ёмкость, overload_shortfall, готовность этапов; при необходимости — интеграционные тесты репозитория/страниц).
- **Файлы:** `tests/test_*.py`, при необходимости новый `tests/test_capacity.py` или расширение test_planner.py / test_dashboard.py.
- **Критерий завершения:** Тесты покрывают ключевые расчёты и импорт; все проходят.
- **Тестирование:** `pytest tests/ -v`; при необходимости обновить Makefile target `test`.
- **Фиксация:** Записать в REFACTORING_RESULTS.md список тестов и результат прогона.

---

## Этап 9 — Makefile и Planner.md

- **Задача:** Обновить Makefile при необходимости; в Planner.md добавить раздел «Структура проекта» с перечислением модулей.
- **Файлы:** Makefile, Planner.md.
- **Критерий завершения:** Документация соответствует фактической структуре проекта.
- **Тестирование:** Финальный прогон `make test`, `make run`.
- **Фиксация:** Записать результат в REFACTORING_RESULTS.md.
