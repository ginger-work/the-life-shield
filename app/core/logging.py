"""
Structured logging configuration using structlog.
Outputs JSON in production, human-readable in development.
"""
import logging
import sys
from typing import Any

import structlog

from app.core.config import settings


def configure_logging() -> None:
    """
    Configure structlog and standard library logging.
    Call once at application startup.
    """
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Suppress noisy libraries
    for noisy_lib in ["uvicorn.access", "sqlalchemy.engine"]:
        logging.getLogger(noisy_lib).setLevel(logging.WARNING)

    # Processors common to all environments
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.LOG_FORMAT == "json" or settings.is_production:
        # JSON output for production / log aggregation
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Human-readable output for development
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Return a bound structlog logger for the given module name.

    Usage:
        logger = get_logger(__name__)
        logger.info("User created", user_id=user.id, email=user.email)
    """
    return structlog.get_logger(name)


def bind_request_context(**kwargs: Any) -> None:
    """
    Bind values to the current request's log context.
    All subsequent log calls in this request will include these values.
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_request_context() -> None:
    """Clear the per-request log context (call at end of request)."""
    structlog.contextvars.clear_contextvars()
