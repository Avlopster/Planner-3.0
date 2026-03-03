# -*- coding: utf-8 -*-
"""Логирование приложения Planner: три файла (БД, действия пользователя, ошибки), обработчик ошибок с понятными сообщениями."""
import logging
import os
import sys
import traceback
from logging.handlers import RotatingFileHandler
from typing import Any, Optional

import config as app_config

_LOG_DIR_INITIALIZED = False
_DB_LOGGER: Optional[logging.Logger] = None
_ACTIONS_LOGGER: Optional[logging.Logger] = None
_ERRORS_LOGGER: Optional[logging.Logger] = None

# Ротация: 2 МБ, 5 резервных файлов
_ROTATE_MAX_BYTES = 2 * 1024 * 1024
_ROTATE_BACKUP_COUNT = 5

# Маппинг исключений на сообщения для пользователя
_EXCEPTION_USER_MESSAGES = {
    "sqlite3.OperationalError": "Ошибка доступа к базе данных. Проверьте путь к БД и права записи.",
    "sqlite3.IntegrityError": "Ошибка целостности данных в базе.",
    "ValueError": "Некорректное значение данных.",
    "TypeError": "Некорректный тип данных.",
    "OSError": "Ошибка доступа к файлу или каталогу.",
    "PermissionError": "Недостаточно прав для выполнения операции.",
}


def _make_handler(
    path: str,
    fmt: str,
    level: int = logging.INFO,
) -> RotatingFileHandler:
    """Создаёт RotatingFileHandler с UTF-8 и ротацией."""
    try:
        handler = RotatingFileHandler(
            path,
            maxBytes=_ROTATE_MAX_BYTES,
            backupCount=_ROTATE_BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError:
        # Fallback: запись в stderr не ломает старт приложения
        return logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(fmt))
    return handler


def init_app_logging() -> None:
    """Инициализирует каталог логов и три логгера. Вызывать один раз при старте приложения (из Planner.py)."""
    global _LOG_DIR_INITIALIZED, _DB_LOGGER, _ACTIONS_LOGGER, _ERRORS_LOGGER
    if _DB_LOGGER is not None:
        return
    log_dir = app_config.LOGS_DIR
    try:
        os.makedirs(log_dir, exist_ok=True)
        _LOG_DIR_INITIALIZED = True
    except OSError:
        pass
    level_db = logging.DEBUG if os.environ.get("PLANNER_LOG_DEBUG") else logging.INFO
    fmt_db = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    fmt_short = "%(asctime)s - %(message)s"
    fmt_err = "%(asctime)s - %(levelname)s - %(message)s"

    _DB_LOGGER = logging.getLogger("planner.db")
    _DB_LOGGER.setLevel(level_db)
    _DB_LOGGER.handlers.clear()
    _DB_LOGGER.addHandler(_make_handler(app_config.DB_LOG_PATH, fmt_db, level_db))

    _ACTIONS_LOGGER = logging.getLogger("planner.actions")
    _ACTIONS_LOGGER.setLevel(logging.INFO)
    _ACTIONS_LOGGER.handlers.clear()
    _ACTIONS_LOGGER.addHandler(_make_handler(app_config.ACTIONS_LOG_PATH, fmt_short, logging.INFO))

    _ERRORS_LOGGER = logging.getLogger("planner.errors")
    _ERRORS_LOGGER.setLevel(logging.INFO)
    _ERRORS_LOGGER.handlers.clear()
    _ERRORS_LOGGER.addHandler(_make_handler(app_config.ERRORS_LOG_PATH, fmt_err, logging.INFO))


def get_db_logger() -> logging.Logger:
    """Логгер для операций БД (planner_db.log)."""
    if _DB_LOGGER is None:
        init_app_logging()
    return _DB_LOGGER


def get_actions_logger() -> logging.Logger:
    """Логгер для действий пользователя (planner_actions.log)."""
    if _ACTIONS_LOGGER is None:
        init_app_logging()
    return _ACTIONS_LOGGER


def get_errors_logger() -> logging.Logger:
    """Логгер для ошибок приложения (planner_errors.log)."""
    if _ERRORS_LOGGER is None:
        init_app_logging()
    return _ERRORS_LOGGER


def log_user_facing_error(
    level: int,
    user_message: str,
    exc: Optional[BaseException] = None,
    context: Optional[str] = None,
) -> None:
    """Пишет в planner_errors.log сообщение, понятное пользователю. При exc опционально дописывает traceback в лог (отдельная запись)."""
    log = get_errors_logger()
    msg = user_message
    if context:
        msg = f"{msg} [{context}]"
    log.log(level, msg)
    if exc is not None:
        tb = traceback.format_exc()
        log.debug("Traceback: %s", tb)


def _user_message_for_exception(exc: BaseException) -> str:
    """Возвращает пользовательское сообщение для известного типа исключения или общее."""
    exc_type_name = type(exc).__name__
    if exc_type_name in _EXCEPTION_USER_MESSAGES:
        return _EXCEPTION_USER_MESSAGES[exc_type_name]
    return "Внутренняя ошибка приложения. Обратитесь в поддержку с файлом planner_errors.log."


def record_error(
    exc: BaseException,
    user_message: Optional[str] = None,
    level: int = logging.ERROR,
) -> None:
    """Записывает ошибку в planner_errors.log. Если user_message не задано — подставляется из маппинга исключений."""
    msg = user_message if user_message else _user_message_for_exception(exc)
    log_user_facing_error(level, msg, exc=exc)
