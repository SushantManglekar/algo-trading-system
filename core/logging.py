"""Structured JSON logging and request correlation for the ASGI application."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class JsonLogFormatter(logging.Formatter):
    """Render standard log records as compact, machine-readable JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for attribute in ("request_id", "correlation_id", "method", "path", "status_code"):
            value = getattr(record, attribute, None)
            if value is not None:
                payload[attribute] = value
        return json.dumps(payload, default=str, separators=(",", ":"))


def configure_json_logging(level: str = "INFO") -> None:
    """Install one tagged stdout handler, making repeated app factories safe in tests."""
    root_logger = logging.getLogger()
    if any(getattr(handler, "_intraday_json_handler", False) for handler in root_logger.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler._intraday_json_handler = True  # type: ignore[attr-defined]
    handler.setFormatter(JsonLogFormatter())
    root_logger.addHandler(handler)
    root_logger.setLevel(level.upper())
