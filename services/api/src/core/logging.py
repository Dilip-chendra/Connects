"""Structured logging with secret redaction."""

import logging
import re
import sys

SENSITIVE_PATTERNS = [
    re.compile(r"(bearer\s+)[a-zA-Z0-9_\-\.]+", re.IGNORECASE),
    re.compile(r"(password['\"]?\s*[:=]\s*['\"])[^'\"]+(['\"])", re.IGNORECASE),
    re.compile(r"(secret['\"]?\s*[:=]\s*['\"])[^'\"]+(['\"])", re.IGNORECASE),
    re.compile(r"(token['\"]?\s*[:=]\s*['\"])[^'\"]+(['\"])", re.IGNORECASE),
    re.compile(r"(api[_-]?key['\"]?\s*[:=]\s*['\"])[^'\"]+(['\"])", re.IGNORECASE),
]


class RedactingFormatter(logging.Formatter):
    """Custom formatter that redacts sensitive secrets from log records."""

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        for pattern in SENSITIVE_PATTERNS:
            msg = pattern.sub(
                r"\1[REDACTED]\2" if r"\2" in pattern.pattern else r"\1[REDACTED]", msg
            )
        return msg


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configures structured, redacted logging to stdout."""
    logger = logging.getLogger("connects")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Avoid duplicate handlers
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = RedactingFormatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] [tenant=%(tenant_id)s] %(message)s",
            defaults={"tenant_id": "none"},
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


logger = setup_logging()
