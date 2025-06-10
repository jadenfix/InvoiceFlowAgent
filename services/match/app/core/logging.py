"""Logging configuration for the matching service."""

import logging
import structlog
import sys
from typing import Any, Dict
from contextvars import ContextVar

from .config import settings

# Context variable for request ID tracking
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


def configure_logging() -> None:
    """Configure structured logging for the application."""
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.JSONRenderer() if settings.log_level == "DEBUG" 
            else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper()),
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a configured logger for the given name."""
    return structlog.get_logger(name)


def set_request_id(request_id: str) -> None:
    """Set the current request ID in context."""
    request_id_ctx.set(request_id)


def get_request_id() -> str:
    """Get the current request ID from context."""
    return request_id_ctx.get()


def log_matching_event(
    logger: structlog.BoundLogger,
    event: str,
    request_id: str,
    **kwargs: Any
) -> None:
    """Log a matching-related event with context."""
    logger.info(
        event,
        request_id=request_id,
        service="match-service",
        **kwargs
    )


def log_error(
    logger: structlog.BoundLogger,
    error: Exception,
    request_id: str,
    context: Dict[str, Any] = None
) -> None:
    """Log an error with full context."""
    logger.error(
        "Error occurred",
        request_id=request_id,
        service="match-service",
        error_type=type(error).__name__,
        error_message=str(error),
        **(context or {})
    ) 