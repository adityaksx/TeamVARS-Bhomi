import contextvars
import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# Context variables for log correlation
current_request_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("current_request_id", default=None)
current_document_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("current_document_id", default=None)
current_stage: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("current_stage", default=None)

# Patterns to sanitize in logs
_SECRET_PATTERNS = [
    re.compile(r"(api[_-]?key[\"']?\s*[:=]\s*[\"']?)([a-zA-Z0-9_\-\.]{8,})([\"']?)", re.IGNORECASE),
    re.compile(r"(Bearer\s+)([a-zA-Z0-9_\-\.]{8,})", re.IGNORECASE),
    re.compile(r"(x-goog-api-key[\"']?\s*[:=]\s*[\"']?)([a-zA-Z0-9_\-\.]{8,})([\"']?)", re.IGNORECASE),
    re.compile(r"(api-subscription-key[\"']?\s*[:=]\s*[\"']?)([a-zA-Z0-9_\-\.]{8,})([\"']?)", re.IGNORECASE),
    re.compile(r"(AIzaSy[a-zA-Z0-9_\-]{33})"),
]


def sanitize_secret(text: str) -> str:
    """Sanitize API keys, bearer tokens, and sensitive headers from log messages."""
    if not isinstance(text, str):
        text = str(text)
    sanitized = text
    for pattern in _SECRET_PATTERNS:
        if pattern.groups == 3:
            sanitized = pattern.sub(r"\1[REDACTED]\3", sanitized)
        elif pattern.groups == 2:
            sanitized = pattern.sub(r"\1[REDACTED]", sanitized)
        elif pattern.groups == 1:
            sanitized = pattern.sub(r"[REDACTED_API_KEY]", sanitized)
    return sanitized


class BhoomiLensFormatter(logging.Formatter):
    """Structured formatter with correlation IDs and secret redaction."""

    def format(self, record: logging.LogRecord) -> str:
        # Check contextvars if not explicitly set on record
        req_id = getattr(record, "request_id", None) or current_request_id.get() or "—"
        doc_id = getattr(record, "document_id", None) or current_document_id.get() or "—"
        stage = getattr(record, "stage", None) or current_stage.get() or "—"

        asctime = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        levelname = record.levelname
        msg = sanitize_secret(record.getMessage())

        formatted = f"{asctime} | {levelname:<7} | request={req_id} | document={doc_id} | stage={stage} | {msg}"
        if record.exc_info:
            formatted += "\n" + self.formatException(record.exc_info)
        return formatted


_configured = False


def configure_logging(
    log_level: Optional[str] = None,
    enable_file_logging: Optional[bool] = None,
    log_file: str = "logs/bhoomilens.log",
) -> logging.Logger:
    global _configured
    logger = logging.getLogger("bhoomilens")

    level_name = (log_level or os.getenv("LOG_LEVEL", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)

    if _configured:
        return logger

    # Clear existing handlers to prevent duplicates
    logger.handlers.clear()

    formatter = BhoomiLensFormatter()

    # Console Handler (StreamHandler)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Optional Rotating File Handler
    file_logging_enabled = (
        enable_file_logging
        if enable_file_logging is not None
        else os.getenv("ENABLE_FILE_LOGGING", "true").lower() in ("true", "1", "yes")
    )

    if file_logging_enabled:
        try:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                log_path,
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as exc:
            logger.warning(f"Failed to initialize rotating file logger at {log_file}: {exc}")

    logger.propagate = False
    _configured = True
    return logger


def get_logger() -> logging.Logger:
    if not _configured:
        return configure_logging()
    return logging.getLogger("bhoomilens")
