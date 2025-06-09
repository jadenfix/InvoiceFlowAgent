"""
Main FastAPI application for InvoiceFlow Auth Service
Entry point with all components integrated
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.core.database import init_db, close_db
from app.core.logging import get_logger
from app.middleware import setup_middleware
from app.api import auth, health

logger = get_logger("auth.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting InvoiceFlow Auth Service...")
    
    # Initialize database
    if not init_db():
        logger.error("Failed to initialize database connection")
        raise RuntimeError("Database initialization failed")
    
    logger.info("Database initialized successfully")
    logger.info(f"Auth service started in {settings.environment} environment")
    
    yield
    
    # Shutdown
    logger.info("Shutting down InvoiceFlow Auth Service...")
    close_db()
    logger.info("Auth service shut down complete")


# Create FastAPI application
app = FastAPI(
    title="InvoiceFlow Auth Service",
    description="Authentication and authorization service for InvoiceFlow platform",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
    openapi_url="/openapi.json" if settings.environment != "production" else None,
)

# Setup middleware
setup_middleware(app)

# Include routers
app.include_router(health.router)
app.include_router(auth.router)


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "InvoiceFlow Auth Service",
        "version": "1.0.0",
        "status": "operational",
        "environment": settings.environment,
        "docs_url": "/docs" if settings.environment != "production" else "disabled",
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """Global HTTP exception handler."""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail,
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception):
    """Global exception handler for unexpected errors."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred"
        }
    )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level=settings.log_level.lower(),
    ) 