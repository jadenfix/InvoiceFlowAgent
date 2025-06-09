"""
Logging configuration for the ingestion service
"""
import logging
import json
import sys
import traceback
from datetime import datetime
from typing import Dict, Any, Optional
import uuid

from .config import settings


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": settings.SERVICE_NAME,
        }
        
        # Add request ID if available
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id
        
        # Add extra fields
        if hasattr(record, "extra"):
            log_entry.update(record.extra)
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info)
            }
        
        return json.dumps(log_entry)


def setup_logging() -> None:
    """Setup application logging configuration"""
    # Clear existing handlers
    logging.getLogger().handlers.clear()
    
    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    
    # Set formatter based on configuration
    if settings.LOG_FORMAT.lower() == "json":
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    
    handler.setFormatter(formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))
    
    # Set specific log levels for third-party libraries
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("scrapy").setLevel(logging.INFO)
    logging.getLogger("selenium").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the specified name"""
    return logging.getLogger(name)


class LoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that adds request context"""
    
    def __init__(self, logger: logging.Logger, extra: Optional[Dict[str, Any]] = None):
        super().__init__(logger, extra or {})
    
    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        """Process the logging call to add extra context"""
        if "extra" in kwargs:
            kwargs["extra"].update(self.extra)
        else:
            kwargs["extra"] = self.extra.copy()
        
        return msg, kwargs


def set_request_id() -> str:
    """Generate and set a new request ID for logging context"""
    request_id = str(uuid.uuid4())
    # This would typically be set in middleware
    return request_id


def log_function_call(func_name: str, **kwargs) -> None:
    """Log function call with parameters"""
    logger = get_logger(__name__)
    logger.info(f"Calling {func_name}", extra={"function": func_name, "parameters": kwargs})


def log_function_result(func_name: str, result: Any, duration: float) -> None:
    """Log function result and execution time"""
    logger = get_logger(__name__)
    logger.info(
        f"Function {func_name} completed", 
        extra={
            "function": func_name, 
            "duration_ms": round(duration * 1000, 2),
            "result_type": type(result).__name__
        }
    )


def log_error(error: Exception, context: Optional[Dict[str, Any]] = None) -> None:
    """Log error with context"""
    logger = get_logger(__name__)
    extra = {"error_type": type(error).__name__}
    if context:
        extra.update(context)
    
    logger.error(f"Error occurred: {str(error)}", exc_info=error, extra=extra)


def log_performance_metrics(operation: str, duration: float, **metrics) -> None:
    """Log performance metrics"""
    logger = get_logger("performance")
    extra = {
        "operation": operation,
        "duration_ms": round(duration * 1000, 2),
        **metrics
    }
    logger.info(f"Performance metrics for {operation}", extra=extra) 