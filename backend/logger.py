"""
ScreenerClaw — Singleton JSON Logger

Usage in any module:
    from backend.logger import get_logger
    logger = get_logger(__name__)

    logger.info("Scraping company", extra={"ticker": "TCS", "url": url})
    logger.error("Pipeline failed", extra={"error": str(e), "query": query})
    logger.exception("Unexpected crash", extra={"step": "valuation"})

Output: pretty-printed JSON to both stdout and logs/app.log
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from threading import Lock
from typing import Any

# Fields that are internal to Python's LogRecord — skip from extra output
_SKIP_FIELDS: frozenset[str] = frozenset({
    "args", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "module",
    "msecs", "message", "msg", "name", "pathname", "process",
    "processName", "relativeCreated", "stack_info", "thread",
    "threadName", "taskName",
})

_SEPARATOR = "─" * 64


class JsonFormatter(logging.Formatter):
    """Formats log records as pretty-printed JSON with a separator line."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "logged_at":     datetime.now().isoformat(),
            "level":         record.levelname,
            "logger":        record.name,
            "file":          os.path.basename(record.pathname),
            "file_path":     record.pathname,
            "function_name": record.funcName,
            "line_number":   record.lineno,
            "message":       record.getMessage(),
        }

        # Exception traceback
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        elif record.exc_text:
            log_data["exception"] = record.exc_text

        # Any extra= fields passed by the caller
        extra = {
            k: v for k, v in vars(record).items()
            if k not in _SKIP_FIELDS
        }
        if extra:
            log_data["extra"] = extra

        def _serialize(obj: Any) -> Any:
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, Exception):
                return {"type": type(obj).__name__, "message": str(obj)}
            if isinstance(obj, bytes):
                return obj.decode("utf-8", errors="replace")
            if hasattr(obj, "__dict__"):
                return str(obj)
            return f"<Unserializable: {type(obj).__name__}>"

        return json.dumps(log_data, indent=2, default=_serialize) + f"\n{_SEPARATOR}"


class _SingletonLogger:
    """Thread-safe singleton that configures the root ScreenerClaw logger once."""

    _instance: "_SingletonLogger | None" = None
    _lock = Lock()

    def __new__(cls) -> "_SingletonLogger":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._setup()
        return cls._instance

    def _setup(self) -> None:
        log_dir = "logs"
        log_file = os.path.join(log_dir, "app.log")
        os.makedirs(log_dir, exist_ok=True)

        root = logging.getLogger("ScreenerClaw")
        root.setLevel(logging.DEBUG)

        if root.handlers:
            return  # already configured (e.g. re-imported)

        formatter = JsonFormatter()

        # Console handler
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.DEBUG)
        stream_handler.setFormatter(formatter)

        # File handler
        file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)

        root.addHandler(stream_handler)
        root.addHandler(file_handler)

        # Suppress noisy third-party loggers
        for noisy in ("httpx", "httpcore", "urllib3", "asyncio"):
            logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Return a child of the ScreenerClaw singleton logger.

    Usage:
        from backend.logger import get_logger
        logger = get_logger(__name__)
    """
    _SingletonLogger()  # ensure singleton is initialised
    # Map module path to ScreenerClaw.* hierarchy
    if name.startswith("backend."):
        child_name = f"ScreenerClaw.{name}"
    elif name == "__main__":
        child_name = "ScreenerClaw.main"
    else:
        child_name = f"ScreenerClaw.{name}"
    return logging.getLogger(child_name)
