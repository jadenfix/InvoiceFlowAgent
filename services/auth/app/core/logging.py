"""
Structured logging configuration for InvoiceFlow Auth Service
Provides structured logging with request IDs and error tracking
"""
import sys
import uuid
import structlog
from typing import Any, Dict
from contextvars import ContextVar
from fastapi import Request
from app.core.config import settings

# Context variable for request ID
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


def add_request_id(logger: Any, name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add request ID to log entries."""
    request_id = request_id_ctx.get("")
    if request_id:
        event_dict["request_id"] = request_id
    return event_dict


def add_severity_level(logger: Any, name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add severity level for cloud logging."""
    level = event_dict.get("level", "").upper()
    severity_map = {
        "DEBUG": "DEBUG",
        "INFO": "INFO", 
        "WARNING": "WARNING",
        "ERROR": "ERROR",
        "CRITICAL": "CRITICAL"
    }
    event_dict["severity"] = severity_map.get(level, "INFO")
    return event_dict


def configure_logging():
    """Configure structured logging."""
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            add_request_id,
            add_severity_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer() if settings.environment == "production"
            else structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    import logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level),
    )


def get_logger(name: str = None):
    """Get a structured logger instance."""
    return structlog.get_logger(name)


def set_request_id(request: Request) -> str:
    """Set request ID for the current request context."""
    # Try to get request ID from headers first
    request_id = request.headers.get("X-Request-ID")
    if not request_id:
        request_id = str(uuid.uuid4())
    
    request_id_ctx.set(request_id)
    return request_id


def log_request_start(request: Request, request_id: str):
    """Log the start of a request."""
    logger = get_logger("auth.request")
    logger.info(
        "Request started",
        method=request.method,
        url=str(request.url),
        user_agent=request.headers.get("User-Agent", ""),
        remote_addr=request.client.host if request.client else "",
        request_id=request_id,
    )


def log_request_end(request: Request, response_status: int, duration_ms: float):
    """Log the end of a request."""
    logger = get_logger("auth.request")
    logger.info(
        "Request completed",
        method=request.method,
        url=str(request.url),
        status_code=response_status,
        duration_ms=round(duration_ms, 2),
        request_id=request_id_ctx.get(""),
    )


def log_auth_event(event_type: str, user_email: str = None, success: bool = True, **kwargs):
    """Log authentication-related events."""
    logger = get_logger("auth.security")
    
    log_data = {
        "event_type": event_type,
        "success": success,
        "request_id": request_id_ctx.get(""),
        **kwargs
    }
    
    if user_email:
        log_data["user_email"] = user_email
    
    if success:
        logger.info("Auth event", **log_data)
    else:
        logger.warning("Auth event failed", **log_data)


def log_error(error: Exception, context: str = ""):
    """Log errors with full context."""
    logger = get_logger("auth.error")
    logger.error(
        "Error occurred",
        error_type=type(error).__name__,
        error_message=str(error),
        context=context,
        request_id=request_id_ctx.get(""),
        exc_info=True,
    )


# Initialize logging on import
configure_logging() 