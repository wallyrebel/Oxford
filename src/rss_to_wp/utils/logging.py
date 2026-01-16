"""Logging utilities with structured output."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import structlog


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    json_output: bool = False,
) -> structlog.BoundLogger:
    """Configure structured logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR).
        log_file: Optional path to log file.
        json_output: If True, output JSON logs (useful for production).

    Returns:
        Configured structlog logger.
    """
    # Set up standard library logging
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Configure handlers
    handlers: list[logging.Handler] = []

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    handlers.append(console_handler)

    # File handler (optional)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(log_level)
        handlers.append(file_handler)

    # Configure root logger
    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        handlers=handlers,
        force=True,
    )

    # Configure structlog
    if json_output:
        # JSON output for production/parsing
        processors = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Pretty console output for development
        processors = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    return structlog.get_logger()


def get_logger(name: Optional[str] = None) -> structlog.BoundLogger:
    """Get a logger instance.

    Args:
        name: Optional logger name for context.

    Returns:
        Structlog bound logger.
    """
    logger = structlog.get_logger()
    if name:
        logger = logger.bind(component=name)
    return logger
