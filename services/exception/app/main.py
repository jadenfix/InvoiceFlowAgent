"""Main FastAPI application for Exception Review Service."""

import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from .core.config import settings
from .core.logging import configure_logging, get_logger, log_request, log_response, log_error
from .models.schemas import ErrorResponse, ValidationErrorResponse

# Configure logging
configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    
    # Startup
    logger.info("Starting Exception Review Service")
    
    try:
        # Only initialize database and message service in non-development mode
        # or when explicitly configured
        if settings.environment != "development" or settings.database_url != "sqlite:///:memory:":
            from .models.database import init_db
            from .services.message_service import message_service
            
            # Initialize database
            try:
                await init_db()
                logger.info("Database initialized")
            except Exception as e:
                logger.warning(f"Database initialization failed: {e}")
                if settings.environment == "production":
                    raise
                logger.info("Continuing without database in development mode")
            
            # Connect to RabbitMQ
            try:
                await message_service.connect()
                logger.info("Message service connected")
            except Exception as e:
                logger.warning(f"Message service connection failed: {e}")
                if settings.environment == "production":
                    raise
                logger.info("Continuing without message service in development mode")
        else:
            logger.info("Running in development mode without external dependencies")
        
        yield
        
    except Exception as e:
        logger.error("Failed to start service", error=str(e))
        if settings.environment == "production":
            raise
        logger.warning("Starting in limited mode due to errors")
        yield
    finally:
        # Shutdown
        logger.info("Shutting down Exception Review Service")
        
        try:
            if settings.environment != "development":
                from .models.database import close_db
                from .services.message_service import message_service
                
                await message_service.disconnect()
                await close_db()
                logger.info("Service shutdown complete")
        except Exception as e:
            logger.error("Error during shutdown", error=str(e))


# Create FastAPI application
app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
    docs_url=settings.docs_url,
    redoc_url=settings.redoc_url,
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allow_origins,
    allow_credentials=settings.allow_credentials,
    allow_methods=settings.allow_methods,
    allow_headers=settings.allow_headers,
)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Logging middleware for requests and responses."""
    
    request_id = str(uuid.uuid4())
    start_time = datetime.utcnow()
    
    # Log request
    log_request(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        query_params=str(request.query_params),
        client_ip=request.client.host
    )
    
    # Add request ID to state
    request.state.request_id = request_id
    
    try:
        # Process request
        response = await call_next(request)
        
        # Calculate duration
        duration = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        # Log response
        log_response(
            request_id=request_id,
            status_code=response.status_code,
            duration_ms=duration
        )
        
        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id
        
        return response
        
    except Exception as e:
        # Calculate duration
        duration = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        # Log error
        log_error(
            request_id=request_id,
            error=e,
            duration_ms=duration
        )
        
        raise


# Exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors."""
    
    request_id = getattr(request.state, "request_id", None)
    
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=ValidationErrorResponse(
            error="Validation Error",
            message="Invalid request data",
            details=[
                {
                    "field": ".".join(str(x) for x in error["loc"]),
                    "message": error["msg"],
                    "type": error["type"]
                }
                for error in exc.errors()
            ],
            request_id=request_id,
            timestamp=datetime.utcnow()
        ).model_dump(mode="json")
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions."""
    
    request_id = getattr(request.state, "request_id", None)
    
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=f"HTTP {exc.status_code}",
            message=exc.detail,
            request_id=request_id,
            timestamp=datetime.utcnow()
        ).model_dump(mode="json")
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions."""
    
    request_id = getattr(request.state, "request_id", None)
    
    logger.error(
        "Unhandled exception",
        request_id=request_id,
        error_type=type(exc).__name__,
        error_message=str(exc)
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="Internal Server Error",
            message="An unexpected error occurred",
            request_id=request_id,
            timestamp=datetime.utcnow()
        ).model_dump(mode="json")
    )


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "description": "Exception Review Service for Invoice Processing",
        "docs_url": settings.docs_url,
        "health_check": "/health/live",
        "readiness_check": "/health/ready",
        "environment": settings.environment
    }


# Include routers
from .api.v1 import health, review

app.include_router(
    health.router,
    prefix="/health",
    tags=["Health"]
)

app.include_router(
    review.router,
    prefix="/api/v1/review",
    tags=["Review"]
)


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.service_host,
        port=settings.service_port,
        reload=settings.debug,
        log_config=None  # Use our custom logging
    ) 