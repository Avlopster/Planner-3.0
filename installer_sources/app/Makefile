# Makefile — Планировщик ресурсов отдела (Planner)
# Точка входа: Planner.py (Streamlit). Модули: config, database, repository,
# load_calculator, capacity, excel_import, excel_import_ui, utils, components, pages/

.PHONY: all run run-browser install test test-quick check clean help

# Цель по умолчанию: показать справку
all: help

# Запуск приложения (Streamlit)
run:
	python -m streamlit run Planner.py

# Запуск с открытием браузера по умолчанию
run-browser:
	python -m streamlit run Planner.py --server.headless false

# Установка зависимостей
install:
	pip install -r requirements.txt

# Полный прогон тестов
test:
	python -m pytest tests/ -v

# Быстрый прогон тестов (без подробного вывода)
test-quick:
	python -m pytest tests/ -q

# Проверка: импорт приложения и всех страниц (без запуска UI)
check:
	python -c "import database, repository, load_calculator, capacity, config, excel_import, excel_import_ui; from utils import date_utils; import components; from app_pages import dashboard, roles, employees, vacations, projects, import_excel, analytics, gantt, calendar as calendar_page, config_page, clear_data; print('OK')"

# Удаление кэшей Python и pytest
clean:
	python -c "import pathlib, shutil; [p.unlink() for p in pathlib.Path('.').rglob('*.py[co]') if p.is_file()]; [p.rmdir() for p in sorted(pathlib.Path('.').rglob('__pycache__'), key=lambda x: -len(x.parts)) if p.is_dir()]; shutil.rmtree('.pytest_cache', ignore_errors=True)"

# Справка по целям (цель по умолчанию)
help:
	@echo Цели:
	@echo   make run         — запуск приложения (Streamlit)
	@echo   make run-browser — запуск с открытием браузера
	@echo   make install     — установка зависимостей
	@echo   make test        — полный прогон тестов (pytest -v)
	@echo   make test-quick  — быстрый прогон тестов
	@echo   make check       — проверка импорта модулей и страниц
	@echo   make clean       — удаление __pycache__ и .pytest_cache
	@echo   make help        — эта справка
