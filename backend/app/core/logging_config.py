"""One logging configuration for every process (R8 / U3).

The API, the ARQ worker, the outbox poller, the health checker and the seed
scripts used to call ``logging.basicConfig`` each in their own way — some at
module import, so whichever module loaded first decided the format of the
whole process. They now all call :func:`configure_logging` once, at start-up.

Outside ``local`` the lines are JSON (one object per line: ``time``, ``level``,
``logger``, ``message``, ``service``, plus the ``extra`` fields and the
exception), which Docker collects and any log platform indexes. In ``local``
they stay readable (``LOG_FORMAT=text``); ``LOG_LEVEL`` sets the root level.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

#: Attributes of a ``LogRecord`` that are not user-provided ``extra`` fields.
_STANDARD_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


class JsonFormatter(logging.Formatter):
    """One JSON object per line, UTC timestamps, ``extra`` fields included."""

    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service,
        }
        for key, value in record.__dict__.items():
            if key in _STANDARD_ATTRS or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(
    *,
    service: str,
    level: str | int | None = None,
    fmt: str | None = None,
    extra_handlers: list[logging.Handler] | None = None,
) -> None:
    """Configure the root logger of this process (idempotent, ``force``).

    ``level`` and ``fmt`` default to the settings (``LOG_LEVEL``,
    ``LOG_FORMAT``: ``json`` outside ``local``, ``text`` in ``local``).
    """
    from app.core.config import settings

    chosen_level = level if level is not None else settings.LOG_LEVEL
    if isinstance(chosen_level, str):
        chosen_level = getattr(logging, chosen_level.upper(), logging.INFO)
    chosen_fmt = (
        fmt
        or settings.LOG_FORMAT
        or ("text" if settings.ENVIRONMENT == "local" else "json")
    )

    stream = logging.StreamHandler(sys.stdout)
    if chosen_fmt == "json":
        stream.setFormatter(JsonFormatter(service))
    else:
        stream.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
    handlers: list[logging.Handler] = [stream, *(extra_handlers or [])]
    logging.basicConfig(level=chosen_level, handlers=handlers, force=True)
    # uvicorn ships its own handlers (coloured, text): route them through ours
    # so the API's access and error lines share the format of the app's.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True


__all__ = ["JsonFormatter", "configure_logging"]
