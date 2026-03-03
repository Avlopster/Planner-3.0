# -*- coding: utf-8 -*-
"""Тесты системы логирования приложения: init_app_logging, логгеры, log_user_facing_error, record_error, config."""
import logging
import os
import sys
import tempfile

import pytest

# Корень проекта в path для импорта config и utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as app_config


@pytest.fixture
def temp_logs_dir():
    """Временный каталог для логов в тестах; подмена config перед инициализацией логгеров."""
    tmp = tempfile.mkdtemp(prefix="planner_logs_test_")
    yield tmp
    try:
        for f in ("planner_db.log", "planner_actions.log", "planner_errors.log"):
            p = os.path.join(tmp, f)
            if os.path.isfile(p):
                os.remove(p)
        os.rmdir(tmp)
    except OSError:
        pass


def _read_last_line(path: str) -> str:
    """Читает последнюю непустую строку файла."""
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        lines = [line.rstrip() for line in f.readlines() if line.strip()]
    return lines[-1] if lines else ""


class TestConfigLogsDir:
    """Проверка конфигурации путей логов."""

    def test_get_logs_dir_returns_string(self):
        from config import get_logs_dir
        path = get_logs_dir()
        assert isinstance(path, str)
        assert len(path) > 0

    def test_logs_dir_and_paths_defined(self):
        assert hasattr(app_config, "LOGS_DIR")
        assert hasattr(app_config, "DB_LOG_PATH")
        assert hasattr(app_config, "ACTIONS_LOG_PATH")
        assert hasattr(app_config, "ERRORS_LOG_PATH")
        assert "planner_db.log" in app_config.DB_LOG_PATH
        assert "planner_actions.log" in app_config.ACTIONS_LOG_PATH
        assert "planner_errors.log" in app_config.ERRORS_LOG_PATH


class TestInitAppLogging:
    """Проверка инициализации логирования и создания файлов."""

    def test_init_creates_log_dir_and_files(self, temp_logs_dir):
        app_logging = __import__("utils.app_logging", fromlist=["utils"])
        app_config.LOGS_DIR = temp_logs_dir
        app_config.DB_LOG_PATH = os.path.join(temp_logs_dir, "planner_db.log")
        app_config.ACTIONS_LOG_PATH = os.path.join(temp_logs_dir, "planner_actions.log")
        app_config.ERRORS_LOG_PATH = os.path.join(temp_logs_dir, "planner_errors.log")
        app_logging._DB_LOGGER = None
        app_logging._ACTIONS_LOGGER = None
        app_logging._ERRORS_LOGGER = None
        app_logging.init_app_logging()
        assert os.path.isdir(temp_logs_dir)
        assert os.path.isfile(app_config.DB_LOG_PATH) or os.path.isfile(app_config.ACTIONS_LOG_PATH) or os.path.isfile(app_config.ERRORS_LOG_PATH)

    def test_get_loggers_create_files_when_logging(self, temp_logs_dir):
        app_logging = __import__("utils.app_logging", fromlist=["utils"])
        app_config.LOGS_DIR = temp_logs_dir
        app_config.DB_LOG_PATH = os.path.join(temp_logs_dir, "planner_db.log")
        app_config.ACTIONS_LOG_PATH = os.path.join(temp_logs_dir, "planner_actions.log")
        app_config.ERRORS_LOG_PATH = os.path.join(temp_logs_dir, "planner_errors.log")
        app_logging._DB_LOGGER = None
        app_logging._ACTIONS_LOGGER = None
        app_logging._ERRORS_LOGGER = None
        app_logging.init_app_logging()
        app_logging.get_db_logger().info("Test DB message")
        app_logging.get_actions_logger().info("Test action message")
        app_logging.get_errors_logger().warning("Test error message")
        assert os.path.isfile(app_config.DB_LOG_PATH)
        assert os.path.isfile(app_config.ACTIONS_LOG_PATH)
        assert os.path.isfile(app_config.ERRORS_LOG_PATH)
        assert "Test DB message" in open(app_config.DB_LOG_PATH, encoding="utf-8").read()
        assert "Test action message" in open(app_config.ACTIONS_LOG_PATH, encoding="utf-8").read()
        assert "Test error message" in open(app_config.ERRORS_LOG_PATH, encoding="utf-8").read()


class TestLoggersIdentity:
    """Проверка имён и типа логгеров."""

    def test_logger_names(self, temp_logs_dir):
        app_logging = __import__("utils.app_logging", fromlist=["utils"])
        app_config.LOGS_DIR = temp_logs_dir
        app_config.DB_LOG_PATH = os.path.join(temp_logs_dir, "planner_db.log")
        app_config.ACTIONS_LOG_PATH = os.path.join(temp_logs_dir, "planner_actions.log")
        app_config.ERRORS_LOG_PATH = os.path.join(temp_logs_dir, "planner_errors.log")
        app_logging._DB_LOGGER = None
        app_logging._ACTIONS_LOGGER = None
        app_logging._ERRORS_LOGGER = None
        app_logging.init_app_logging()
        assert app_logging.get_db_logger().name == "planner.db"
        assert app_logging.get_actions_logger().name == "planner.actions"
        assert app_logging.get_errors_logger().name == "planner.errors"

    def test_get_loggers_return_logger_instances(self, temp_logs_dir):
        app_logging = __import__("utils.app_logging", fromlist=["utils"])
        app_config.LOGS_DIR = temp_logs_dir
        app_config.DB_LOG_PATH = os.path.join(temp_logs_dir, "planner_db.log")
        app_config.ACTIONS_LOG_PATH = os.path.join(temp_logs_dir, "planner_actions.log")
        app_config.ERRORS_LOG_PATH = os.path.join(temp_logs_dir, "planner_errors.log")
        app_logging._DB_LOGGER = None
        app_logging._ACTIONS_LOGGER = None
        app_logging._ERRORS_LOGGER = None
        app_logging.init_app_logging()
        assert isinstance(app_logging.get_db_logger(), logging.Logger)
        assert isinstance(app_logging.get_actions_logger(), logging.Logger)
        assert isinstance(app_logging.get_errors_logger(), logging.Logger)


class TestLogUserFacingError:
    """Проверка log_user_facing_error."""

    def test_log_user_facing_error_writes_to_errors_file(self, temp_logs_dir):
        app_logging = __import__("utils.app_logging", fromlist=["utils"])
        app_config.LOGS_DIR = temp_logs_dir
        app_config.ERRORS_LOG_PATH = os.path.join(temp_logs_dir, "planner_errors.log")
        app_config.DB_LOG_PATH = os.path.join(temp_logs_dir, "planner_db.log")
        app_config.ACTIONS_LOG_PATH = os.path.join(temp_logs_dir, "planner_actions.log")
        app_logging._DB_LOGGER = None
        app_logging._ACTIONS_LOGGER = None
        app_logging._ERRORS_LOGGER = None
        app_logging.init_app_logging()
        app_logging.log_user_facing_error(logging.ERROR, "Понятное сообщение пользователю")
        content = open(app_config.ERRORS_LOG_PATH, encoding="utf-8").read()
        assert "Понятное сообщение пользователю" in content

    def test_log_user_facing_error_with_context(self, temp_logs_dir):
        app_logging = __import__("utils.app_logging", fromlist=["utils"])
        app_config.LOGS_DIR = temp_logs_dir
        app_config.ERRORS_LOG_PATH = os.path.join(temp_logs_dir, "planner_errors.log")
        app_config.DB_LOG_PATH = os.path.join(temp_logs_dir, "planner_db.log")
        app_config.ACTIONS_LOG_PATH = os.path.join(temp_logs_dir, "planner_actions.log")
        app_logging._DB_LOGGER = None
        app_logging._ACTIONS_LOGGER = None
        app_logging._ERRORS_LOGGER = None
        app_logging.init_app_logging()
        app_logging.log_user_facing_error(logging.WARNING, "Предупреждение", context="project_id=1")
        content = open(app_config.ERRORS_LOG_PATH, encoding="utf-8").read()
        assert "Предупреждение" in content
        assert "project_id=1" in content


class TestRecordError:
    """Проверка record_error и маппинга исключений."""

    def test_record_error_with_user_message(self, temp_logs_dir):
        app_logging = __import__("utils.app_logging", fromlist=["utils"])
        app_config.LOGS_DIR = temp_logs_dir
        app_config.ERRORS_LOG_PATH = os.path.join(temp_logs_dir, "planner_errors.log")
        app_config.DB_LOG_PATH = os.path.join(temp_logs_dir, "planner_db.log")
        app_config.ACTIONS_LOG_PATH = os.path.join(temp_logs_dir, "planner_actions.log")
        app_logging._DB_LOGGER = None
        app_logging._ACTIONS_LOGGER = None
        app_logging._ERRORS_LOGGER = None
        app_logging.init_app_logging()
        try:
            raise ValueError("test")
        except ValueError as e:
            app_logging.record_error(e, user_message="Своё сообщение для пользователя")
        content = open(app_config.ERRORS_LOG_PATH, encoding="utf-8").read()
        assert "Своё сообщение для пользователя" in content

    def test_record_error_without_user_message_uses_mapping(self, temp_logs_dir):
        app_logging = __import__("utils.app_logging", fromlist=["utils"])
        app_config.LOGS_DIR = temp_logs_dir
        app_config.ERRORS_LOG_PATH = os.path.join(temp_logs_dir, "planner_errors.log")
        app_config.DB_LOG_PATH = os.path.join(temp_logs_dir, "planner_db.log")
        app_config.ACTIONS_LOG_PATH = os.path.join(temp_logs_dir, "planner_actions.log")
        app_logging._DB_LOGGER = None
        app_logging._ACTIONS_LOGGER = None
        app_logging._ERRORS_LOGGER = None
        app_logging.init_app_logging()
        try:
            raise ValueError("internal")
        except ValueError as e:
            app_logging.record_error(e)
        content = open(app_config.ERRORS_LOG_PATH, encoding="utf-8").read()
        assert "Некорректное значение данных" in content

    def test_record_error_unknown_exception_gets_generic_message(self, temp_logs_dir):
        app_logging = __import__("utils.app_logging", fromlist=["utils"])
        app_config.LOGS_DIR = temp_logs_dir
        app_config.ERRORS_LOG_PATH = os.path.join(temp_logs_dir, "planner_errors.log")
        app_config.DB_LOG_PATH = os.path.join(temp_logs_dir, "planner_db.log")
        app_config.ACTIONS_LOG_PATH = os.path.join(temp_logs_dir, "planner_actions.log")
        app_logging._DB_LOGGER = None
        app_logging._ACTIONS_LOGGER = None
        app_logging._ERRORS_LOGGER = None
        app_logging.init_app_logging()
        try:
            raise RuntimeError("unknown")
        except RuntimeError as e:
            app_logging.record_error(e)
        content = open(app_config.ERRORS_LOG_PATH, encoding="utf-8").read()
        assert "Внутренняя ошибка приложения" in content or "planner_errors.log" in content
