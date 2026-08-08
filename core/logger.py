from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs"
DEFAULT_LOG_FILE = DEFAULT_LOG_DIR / "exilingo.log"

LOG_FORMAT = (
    "%(asctime)s.%(msecs)03d "
    "[%(levelname)s] "
    "[%(name)s] "
    "%(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class FlushFileHandler(logging.FileHandler):
    """FileHandler, который сразу сбрасывает запись на диск."""

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()


def mask_secret(
    value: Any,
    *,
    visible_prefix: int = 6,
    visible_suffix: int = 5,
) -> str:
    """Маскирует секрет, оставляя начало и конец значения."""
    if value is None:
        return ""

    text = str(value)

    if not text:
        return ""

    if len(text) <= visible_prefix + visible_suffix:
        return "X" * len(text)

    masked_length = len(text) - visible_prefix - visible_suffix

    return (
        text[:visible_prefix]
        + ("X" * masked_length)
        + text[-visible_suffix:]
    )


def _is_secret_key(key: str) -> bool:
    """Определяет, является ли имя поля потенциальным секретом."""
    normalized = key.lower().replace("-", "_").replace(" ", "_")

    secret_names = {
        "api_key",
        "apikey",
        "api_token",
        "access_token",
        "refresh_token",
        "auth_token",
        "secret",
        "secret_key",
        "password",
        "passwd",
    }

    if normalized in secret_names:
        return True

    return (
        normalized.endswith("_api_key")
        or normalized.endswith("_token")
        or normalized.endswith("_password")
    )


def sanitize_settings(value: Any) -> Any:
    """
    Создаёт безопасную копию настроек для записи в лог.

    Исходный config не изменяется.
    """
    if isinstance(value, dict):
        result = {}

        for key, item in value.items():
            key_string = str(key)

            if _is_secret_key(key_string):
                result[key_string] = mask_secret(item)
            else:
                result[key_string] = sanitize_settings(item)

        return result

    if isinstance(value, list):
        return [sanitize_settings(item) for item in value]

    if isinstance(value, tuple):
        return [sanitize_settings(item) for item in value]

    return value


def _safe_json(value: Any) -> str:
    """Безопасно сериализует значение настроек."""
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    except Exception:
        return repr(value)


def _write_session_header(
    logger: logging.Logger,
    *,
    version: str | None = None,
) -> None:
    """Записывает начало новой сессии."""
    separator = "=" * 68

    logger.info(separator)
    logger.info("EXILINGO SESSION START")

    if version:
        logger.info("Version: %s", version)

    logger.info(
        "Started: %s",
        datetime.now().astimezone().isoformat(timespec="seconds"),
    )
    logger.info("Python: %s", sys.version.split()[0])
    logger.info("Platform: %s", sys.platform)
    logger.info("Project root: %s", PROJECT_ROOT)
    logger.info(separator)


_configured = False
_root_logger: logging.Logger | None = None


def setup_logging(
    *,
    log_file: str | Path | None = None,
    level: int = logging.DEBUG,
    version: str | None = None,
) -> logging.Logger:
    """
    Инициализирует файловое логирование Exilingo.

    Файл открывается в режиме w, поэтому каждая новая сессия
    начинает новый лог.

    Каждая запись сразу flush-ится на диск.
    """
    global _configured, _root_logger

    if _configured and _root_logger is not None:
        return _root_logger

    path = (
        Path(log_file)
        if log_file is not None
        else DEFAULT_LOG_FILE
    )

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("Exilingo")
    logger.setLevel(level)
    logger.propagate = False

    # Защита от дублирования handlers при повторной инициализации.
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    file_handler = FlushFileHandler(
        path,
        mode="w",
        encoding="utf-8",
        delay=False,
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(
        logging.Formatter(
            LOG_FORMAT,
            datefmt=DATE_FORMAT,
        )
    )

    logger.addHandler(file_handler)

    _configured = True
    _root_logger = logger

    _write_session_header(
        logger,
        version=version,
    )

    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Возвращает logger указанного компонента."""
    if not _configured:
        setup_logging()

    if not name:
        return _root_logger or logging.getLogger("Exilingo")

    return logging.getLogger(f"Exilingo.{name}")


def log_settings_snapshot(
    settings: dict[str, Any],
    *,
    logger: logging.Logger | None = None,
) -> None:
    """
    Записывает безопасный снимок текущих настроек.

    API keys, tokens, passwords и другие секреты маскируются.
    """
    target_logger = logger or get_logger("Settings")
    safe_settings = sanitize_settings(settings)

    target_logger.info("CURRENT SETTINGS SNAPSHOT BEGIN")
    target_logger.info("\n%s", _safe_json(safe_settings))
    target_logger.info("CURRENT SETTINGS SNAPSHOT END")


def log_exception(
    logger: logging.Logger,
    message: str,
    *args: Any,
    **kwargs: Any,
) -> None:
    """Записывает сообщение об ошибке вместе с traceback."""
    logger.error(
        message,
        *args,
        exc_info=True,
        **kwargs,
    )


def shutdown_logging() -> None:
    """Корректно завершает файловое логирование."""
    global _configured, _root_logger

    if not _configured:
        return

    if _root_logger is not None:
        _root_logger.info("EXILINGO SESSION END")

    logging.shutdown()

    _configured = False
    _root_logger = None


__all__ = [
    "DEFAULT_LOG_DIR",
    "DEFAULT_LOG_FILE",
    "get_logger",
    "log_exception",
    "log_settings_snapshot",
    "mask_secret",
    "sanitize_settings",
    "setup_logging",
    "shutdown_logging",
]
