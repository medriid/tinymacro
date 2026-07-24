from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "tinymacro"


def default_log_path() -> Path:
    return Path.home() / ".config" / "tiny-macro" / "tiny-macro.log"


@dataclass(slots=True)
class LogRecord:
    time: str
    level: str
    message: str

    def format(self) -> str:
        return f"{self.time}  {self.level:<7} {self.message}"


class RingBufferHandler(logging.Handler):
    """Keeps the most recent records in memory for the in-app log viewer."""

    def __init__(self, capacity: int = 500) -> None:
        super().__init__()
        self.records: deque[LogRecord] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(
            LogRecord(
                time=datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
                level=record.levelname,
                message=record.getMessage(),
            )
        )

    def snapshot(self) -> list[LogRecord]:
        return list(self.records)

    def clear(self) -> None:
        self.records.clear()


_ring: RingBufferHandler | None = None


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def ring_buffer() -> RingBufferHandler:
    global _ring
    if _ring is None:
        _ring = RingBufferHandler()
    return _ring


def configure_logging(
    level: int = logging.INFO,
    log_path: Path | None = None,
    to_file: bool = True,
    capacity: int = 500,
) -> logging.Logger:
    """Attach a rotating file handler and an in-memory ring buffer once."""
    logger = get_logger()
    logger.setLevel(level)
    logger.propagate = False

    ring = ring_buffer()
    ring.records = type(ring.records)(ring.records, maxlen=capacity)
    if ring not in logger.handlers:
        logger.addHandler(ring)

    if to_file and not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
        path = log_path or default_log_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(path, maxBytes=512_000, backupCount=3, encoding="utf-8")
            file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            logger.addHandler(file_handler)
        except OSError:
            # A read-only home or missing permissions should never crash the app;
            # the in-memory ring buffer still works for diagnostics.
            pass
    return logger
