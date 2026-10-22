"""Structured JSON logging with correlation-ID propagation.

Every log line is a single JSON object so CloudWatch Logs Insights (or any
log aggregator) can filter on fields like ``correlation_id`` and ``event_id``
instead of regex-ing free text. The correlation ID lives in a ``ContextVar``:
the ingest handler sets it from the inbound request, embeds it in the SQS
message, and the processor restores it on the other side — so one ID ties
together every log line a single event produces across both functions.
"""

import contextvars
import json
import logging
import os
from datetime import datetime, timezone

_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default="-"
)


def set_correlation_id(value: str) -> None:
    _correlation_id.set(value or "-")


def get_correlation_id() -> str:
    return _correlation_id.get()


class JsonFormatter(logging.Formatter):
    """Render each record as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": get_correlation_id(),
        }
        # Handlers attach structured fields via ``extra={"fields": {...}}``.
        fields = getattr(record, "fields", None)
        if fields:
            entry.update(fields)
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logger(name: str) -> logging.Logger:
    """Return a logger that writes JSON lines to stdout (Lambda captures it)."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
    logger.propagate = False
    return logger


def log(logger: logging.Logger, level: int, message: str, **fields) -> None:
    """Emit a log line with arbitrary structured fields attached."""
    logger.log(level, message, extra={"fields": fields})
