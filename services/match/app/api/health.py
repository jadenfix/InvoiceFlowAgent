"""Health check endpoints for the matching service."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
import structlog

from ..services.database_service import db_service
from ..services.message_queue import mq_service
from ..core.config import settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    service: str
    version: str
    details: dict = {}


@router.get("/live", response_model=HealthResponse)
async def liveness_check():
    """
    Liveness probe endpoint.
    Returns 200 if the service is running.
    """
    return HealthResponse(
        status="healthy",
        service=settings.service_name,
        version=settings.version,
        details={
            "check": "liveness",
            "description": "Service is running"
        }
    )


@router.get("/ready", response_model=HealthResponse)
async def readiness_check():
    """
    Readiness probe endpoint.
    Returns 200 if service can handle requests (DB and RabbitMQ are available).
    Returns 503 if service is not ready.
    """
    details = {}
    is_ready = True
    
    # Check database connectivity
    try:
        db_healthy = await db_service.health_check()
        details["database"] = "healthy" if db_healthy else "unhealthy"
        if not db_healthy:
            is_ready = False
    except Exception as e:
        details["database"] = f"error: {str(e)}"
        is_ready = False
    
    # Check message queue connectivity
    try:
        mq_healthy = await mq_service.health_check()
        details["message_queue"] = "healthy" if mq_healthy else "unhealthy"
        if not mq_healthy:
            is_ready = False
    except Exception as e:
        details["message_queue"] = f"error: {str(e)}"
        is_ready = False
    
    # Add service configuration
    details.update({
        "check": "readiness",
        "match_tolerance": str(settings.match_amount_tolerance),
        "database_url_set": bool(settings.database_url),
        "rabbitmq_url_set": bool(settings.rabbitmq_url)
    })
    
    if not is_ready:
        logger.warning(
            "Readiness check failed",
            service=settings.service_name,
            details=details
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not_ready",
                "service": settings.service_name,
                "version": settings.version,
                "details": details
            }
        )
    
    return HealthResponse(
        status="ready",
        service=settings.service_name,
        version=settings.version,
        details=details
    )


@router.get("/status", response_model=HealthResponse)
async def status_check():
    """
    Detailed status endpoint with component health information.
    """
    details = {}
    
    # Database status
    try:
        db_healthy = await db_service.health_check()
        details["database"] = {
            "status": "healthy" if db_healthy else "unhealthy",
            "url_configured": bool(settings.database_url)
        }
    except Exception as e:
        details["database"] = {
            "status": "error",
            "error": str(e),
            "url_configured": bool(settings.database_url)
        }
    
    # Message queue status
    try:
        mq_healthy = await mq_service.health_check()
        details["message_queue"] = {
            "status": "healthy" if mq_healthy else "unhealthy",
            "url_configured": bool(settings.rabbitmq_url)
        }
    except Exception as e:
        details["message_queue"] = {
            "status": "error",
            "error": str(e),
            "url_configured": bool(settings.rabbitmq_url)
        }
    
    # Configuration status
    details["configuration"] = {
        "match_tolerance": str(settings.match_amount_tolerance),
        "log_level": settings.log_level,
        "port": settings.port
    }
    
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        version=settings.version,
        details=details
    ) 