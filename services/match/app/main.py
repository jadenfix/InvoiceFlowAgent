"""Main FastAPI application for the matching service."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
import structlog

from .core.config import settings
from .core.logging import configure_logging, get_logger
from .api.health import router as health_router
from .services.database_service import db_service
from .services.message_queue import mq_service
from .services.matching_service import matching_service

# Configure logging
configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown."""
    
    # Startup
    logger.info("Starting matching service", service=settings.service_name)
    
    try:
        # Initialize database service
        await db_service.initialize()
        
        # Initialize message queue service
        await mq_service.initialize()
        
        # Start consuming messages
        asyncio.create_task(
            mq_service.consume_invoice_extracted(
                matching_service.process_invoice_extracted_message
            )
        )
        
        logger.info(
            "Matching service started successfully",
            service=settings.service_name,
            version=settings.version,
            port=settings.port
        )
        
        yield
        
    except Exception as e:
        logger.error(
            "Failed to start matching service",
            service=settings.service_name,
            error=str(e)
        )
        raise
    
    # Shutdown
    logger.info("Shutting down matching service", service=settings.service_name)
    
    try:
        # Close message queue connections
        await mq_service.close()
        
        # Close database connections
        await db_service.close()
        
        logger.info("Matching service shut down successfully", service=settings.service_name)
        
    except Exception as e:
        logger.error(
            "Error during shutdown",
            service=settings.service_name,
            error=str(e)
        )


# Create FastAPI application
app = FastAPI(
    title="InvoiceFlow Matching Service",
    description="Service for matching invoices with purchase orders",
    version=settings.version,
    lifespan=lifespan
)

# Include routers
app.include_router(health_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": settings.service_name,
        "version": settings.version,
        "description": "InvoiceFlow Matching Service",
        "status": "running"
    }


@app.get("/info")
async def service_info():
    """Service information endpoint."""
    return {
        "service": settings.service_name,
        "version": settings.version,
        "description": "Service for matching invoices with purchase orders",
        "configuration": {
            "match_tolerance": str(settings.match_amount_tolerance),
            "log_level": settings.log_level,
            "port": settings.port
        },
        "endpoints": {
            "health": {
                "liveness": "/health/live",
                "readiness": "/health/ready",
                "status": "/health/status"
            }
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=False
    ) 