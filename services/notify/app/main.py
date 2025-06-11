"""
FastAPI main application for notification service
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import create_tables
from app.api.health import router as health_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting notification service")
    
    try:
        # Create database tables
        create_tables()
        logger.info("Database tables initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down notification service")


# Create FastAPI app
app = FastAPI(
    title="Invoice Notification Service",
    description="Notification service for invoice review alerts",
    version="1.0.0",
    lifespan=lifespan
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
app.include_router(health_router, tags=["Health"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "notification-service",
        "version": "1.0.0",
        "status": "running",
        "description": "Invoice notification service for review alerts"
    }


@app.get("/info")
async def service_info():
    """Service information endpoint"""
    return {
        "name": "notification-service",
        "version": "1.0.0",
        "description": "Handles email and SMS notifications for invoices requiring review",
        "features": [
            "Email notifications via SendGrid",
            "SMS notifications via Twilio", 
            "Scheduled scanning for invoices needing review",
            "Duplicate notification prevention",
            "Retry logic with exponential backoff",
            "Health monitoring and status checks"
        ],
        "endpoints": {
            "health": {
                "GET /health/live": "Liveness probe",
                "GET /health/ready": "Readiness probe", 
                "GET /health/status": "Detailed status"
            }
        },
        "configuration": {
            "notification_interval_minutes": settings.review_notification_interval,
            "recipients_configured": len(settings.recipients_list),
            "email_service": "sendgrid" if settings.sendgrid_api_key else "not configured",
            "sms_service": "twilio" if settings.twilio_account_sid else "not configured"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True
    ) 