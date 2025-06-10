"""
Logging configuration for the extraction service
"""
import logging
import json
import time
import traceback
from typing import Any, Dict, Optional
from datetime import datetime
from functools import wraps

from .config import settings


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": settings.SERVICE_NAME,
        }
        
        # Add extra fields
        if hasattr(record, 'request_id'):
            log_entry["request_id"] = record.request_id
        
        if hasattr(record, 'filename'):
            log_entry["filename"] = record.filename
            
        if hasattr(record, 'duration'):
            log_entry["duration"] = record.duration
            
        if hasattr(record, 'error_type'):
            log_entry["error_type"] = record.error_type
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info)
            }
        
        return json.dumps(log_entry)


def setup_logging():
    """Setup logging configuration"""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler
    handler = logging.StreamHandler()
    
    if settings.LOG_FORMAT.lower() == "json":
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    
    # Set specific logger levels
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("fastapi").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get logger instance"""
    return logging.getLogger(name)


def log_function_call(func_name: str, **kwargs):
    """Log function call with parameters"""
    logger = get_logger("app.core.logging")
    extra = {"function": func_name}
    extra.update(kwargs)
    logger.info(f"Calling {func_name}", extra=extra)


def log_function_result(func_name: str, result: Any, duration: float, **kwargs):
    """Log function result with duration"""
    logger = get_logger("app.core.logging")
    extra = {"function": func_name, "duration": duration}
    extra.update(kwargs)
    logger.info(f"Completed {func_name} in {duration:.3f}s", extra=extra)


def log_error(error: Exception, context: Optional[Dict[str, Any]] = None):
    """Log error with context"""
    logger = get_logger("app.core.logging")
    extra = {"error_type": type(error).__name__}
    if context:
        extra.update(context)
    logger.error(f"Error occurred: {error}", exc_info=True, extra=extra)


def log_processing_step(step: str, request_id: str, **kwargs):
    """Log processing step with request ID"""
    logger = get_logger("app.services.extraction")
    extra = {"step": step, "request_id": request_id}
    extra.update(kwargs)
    logger.info(f"Processing step: {step}", extra=extra)


def with_logging(func):
    """Decorator to add automatic logging to functions"""
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        start_time = time.time()
        func_name = f"{func.__module__}.{func.__name__}"
        
        try:
            log_function_call(func_name, **kwargs)
            result = await func(*args, **kwargs)
            duration = time.time() - start_time
            log_function_result(func_name, result, duration)
            return result
        except Exception as e:
            duration = time.time() - start_time
            log_error(e, {"function": func_name, "duration": duration})
            raise
    
    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        start_time = time.time()
        func_name = f"{func.__module__}.{func.__name__}"
        
        try:
            log_function_call(func_name, **kwargs)
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            log_function_result(func_name, result, duration)
            return result
        except Exception as e:
            duration = time.time() - start_time
            log_error(e, {"function": func_name, "duration": duration})
            raise
    
    if hasattr(func, '__code__') and 'await' in func.__code__.co_names:
        return async_wrapper
    else:
        return sync_wrapper


# Initialize logging on import
setup_logging() 