"""Logging configuration for the Exception Review Service."""

import sys
import structlog
from typing import Any, Dict
from .config import settings


def configure_logging() -> None:
    """Configure structured logging."""
    
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer() if settings.log_format == "json" 
            else structlog.dev.ConsoleRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a configured logger instance."""
    return structlog.get_logger(name)


def log_request(request_id: str, method: str, path: str, **kwargs: Any) -> None:
    """Log incoming request."""
    logger = get_logger("request")
    logger.info(
        "Request received",
        request_id=request_id,
        method=method,
        path=path,
        **kwargs
    )


def log_response(request_id: str, status_code: int, duration_ms: float, **kwargs: Any) -> None:
    """Log outgoing response."""
    logger = get_logger("response")
    logger.info(
        "Response sent",
        request_id=request_id,
        status_code=status_code,
        duration_ms=duration_ms,
        **kwargs
    )


def log_error(request_id: str, error: Exception, **kwargs: Any) -> None:
    """Log error."""
    logger = get_logger("error")
    logger.error(
        "Error occurred",
        request_id=request_id,
        error_type=type(error).__name__,
        error_message=str(error),
        **kwargs
    ) 