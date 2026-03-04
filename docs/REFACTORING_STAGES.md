# Этапы рефакторинга Planner 3.0

Рефакторинг выполняется в каталоге **Planner 3.0** по плану из `.cursor/plans/`. Исходная стабильная версия — **Planner-2.0** (не изменяется).

## Таблица этапов

| № | Этап | Описание | Статус |
|---|------|----------|--------|
| 0 | Синхронизация | Проверка соответствия Planner 3.0 и Planner-2.0; при необходимости обновление 3.0 | [x] |
| 1 | Безопасность sql_runner | Ограничение выполнения только чтением по умолчанию; явное подтверждение для INSERT/UPDATE/DELETE; не логировать тело запроса | [x] |
| 2 | Слой данных: этапы и назначения | Вынести все прямые SQL из app_pages/projects.py в repository (phase/assignment CRUD) | [x] |
| 3 | Мутация конфига | Убрать присвоение app_config.DB_PATH в database.get_connection; возвращать фактический путь явно | [x] |
| 4 | Точка входа и кеш | Унифицировать кеш загрузок или убрать неиспользуемый; упростить Planner.py до инициализации, меню и роутинга | [x] |
| 5 | DRY в load_calculator | Выделить общие функции для employee_load_by_day и employee_load_by_day_batch | [x] |
| 6 | Поддерживаемость projects.py | Разбить длинные функции в app_pages/projects.py на подфункции | [x] |
| 7 | Тесты | Заменить дубликат check_vacation_overlap в test_planner на вызов repository; добавить тесты для phase CRUD и load_calculator | [x] |
| 8 | Качество кода | black/isort/flake8 или ruff; docstring для render(conn) | [x] |
| 9 | Документация | Обновить README/docs под новую структуру и ключевые решения | [x] |

## Проверки после этапов

- Запуск: `streamlit run Planner.py`
- Тесты: `pytest tests/ -v`
- Результаты фиксировать в [REFACTORING_RESULTS.md](REFACTORING_RESULTS.md).
