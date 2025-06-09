"""
Middleware for InvoiceFlow Auth Service
Handles request logging, error handling, and CORS
"""
import time
from typing import Callable
from fastapi import Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.logging import (
    get_logger, set_request_id, log_request_start, log_request_end, log_error
)

logger = get_logger("auth.middleware")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging requests and responses."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and log details."""
        start_time = time.time()
        
        # Set request ID for logging context
        request_id = set_request_id(request)
        
        # Log request start
        log_request_start(request, request_id)
        
        try:
            # Process request
            response = await call_next(request)
            
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000
            
            # Log request completion
            log_request_end(request, response.status_code, duration_ms)
            
            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            
            return response
            
        except Exception as e:
            # Calculate duration for failed requests
            duration_ms = (time.time() - start_time) * 1000
            
            # Log error
            log_error(e, f"Request failed: {request.method} {request.url}")
            
            # Log request completion with error
            log_request_end(request, 500, duration_ms)
            
            # Return error response
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "message": "An unexpected error occurred",
                    "request_id": request_id,
                },
                headers={"X-Request-ID": request_id}
            )


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware for global error handling."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Handle errors globally."""
        try:
            response = await call_next(request)
            return response
            
        except HTTPException as e:
            # HTTPExceptions are handled by FastAPI
            raise e
            
        except Exception as e:
            # Log unexpected errors
            logger.error(f"Unhandled exception: {str(e)}", exc_info=True)
            
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "message": "An unexpected error occurred"
                }
            )


def setup_cors_middleware(app):
    """Setup CORS middleware with appropriate settings."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",  # React dev server
            "http://localhost:5173",  # Vite dev server
            "https://invoiceflow.com",  # Production frontend
            "https://*.invoiceflow.com",  # Subdomains
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Accept",
            "Accept-Language",
            "Content-Language",
            "Content-Type",
            "Authorization",
            "X-Request-ID",
        ],
        expose_headers=["X-Request-ID"],
    )


def setup_middleware(app):
    """Setup all middleware for the application."""
    # Add custom middleware
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(ErrorHandlingMiddleware)
    
    # Setup CORS
    setup_cors_middleware(app)
    
    logger.info("Middleware setup completed") 