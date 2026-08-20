"""JSON logging with request-scoped correlation fields and trace identifiers."""

from __future__ import annotations

import contextvars
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from opentelemetry import trace

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
room_code_var: contextvars.ContextVar[str] = contextvars.ContextVar("room_code", default="")
operation_var: contextvars.ContextVar[str] = contextvars.ContextVar("operation", default="")


@dataclass(slots=True)
class ContextBinding:
    tokens: tuple[contextvars.Token[str], contextvars.Token[str], contextvars.Token[str]]

    def reset(self) -> None:
        request_id_var.reset(self.tokens[0])
        room_code_var.reset(self.tokens[1])
        operation_var.reset(self.tokens[2])


def bind_context(request_id: str, room_code: str = "", operation: str = "") -> ContextBinding:
    return ContextBinding(
        (
            request_id_var.set(request_id),
            room_code_var.set(room_code),
            operation_var.set(operation),
        )
    )


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.room_code = room_code_var.get()
        record.operation = operation_var.get()
        span = trace.get_current_span().get_span_context()
        record.trace_id = format(span.trace_id, "032x") if span.is_valid else ""
        record.span_id = format(span.span_id, "016x") if span.is_valid else ""
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        value: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()),
            "message": record.getMessage(),
        }
        for key in (
            "request_id",
            "room_code",
            "operation",
            "trace_id",
            "span_id",
            "http_method",
            "http_path",
            "http_status",
            "duration_ms",
            "player_ref",
        ):
            field = getattr(record, key, None)
            if field not in (None, ""):
                value[key] = field
        if record.exc_info:
            value["exception"] = self.formatException(record.exc_info)
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def configure_logging(level: str, json_output: bool) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(ContextFilter())
    if json_output:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s request_id=%(request_id)s")
        )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    # These access loggers include query strings, which can contain player credentials.
    for logger_name in ("httpx", "httpx2", "uvicorn.access"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)
