"""
Main FastAPI application for the extraction service
"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import settings
from .core.logging import get_logger, setup_logging
from .api.health import router as health_router
from .services.extraction_worker import extraction_worker
from .services.message_queue import message_queue_service


# Setup logging
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info(f"Starting {settings.SERVICE_NAME} v{settings.VERSION}")
    
    try:
        # Connect to RabbitMQ and start consuming
        await message_queue_service.connect()
        
        # Start the extraction worker in the background
        extraction_task = asyncio.create_task(
            _start_extraction_worker()
        )
        
        logger.info("Application startup completed")
        
        yield
        
    finally:
        # Shutdown
        logger.info("Shutting down application")
        
        # Stop the extraction worker
        extraction_worker.is_running = False
        
        # Disconnect from RabbitMQ
        await message_queue_service.disconnect()
        
        # Cancel the extraction task
        if 'extraction_task' in locals():
            extraction_task.cancel()
            try:
                await extraction_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Application shutdown completed")


async def _start_extraction_worker():
    """Start the extraction worker"""
    try:
        extraction_worker.is_running = True
        
        # Start consuming messages
        await message_queue_service.start_consuming(
            extraction_worker.process_message
        )
        
        # Keep running
        while extraction_worker.is_running:
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"Extraction worker error: {e}")
        raise


# Create FastAPI app
app = FastAPI(
    title="Invoice Extraction Service",
    description="Microservice for extracting structured data from invoice PDFs using OCR and LLM",
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health_router, tags=["health"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": settings.SERVICE_NAME,
        "version": settings.VERSION,
        "status": "running",
        "docs": "/docs" if settings.DEBUG else "disabled"
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        workers=settings.WORKERS if not settings.DEBUG else 1,
        log_level=settings.LOG_LEVEL.lower(),
    ) 