"""
Health check API endpoints
"""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db, check_async_database_connection
from app.services.notification_service import NotificationService
from app.models.notification import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health/live", status_code=200)
async def liveness_probe():
    """
    Liveness probe - checks if the service is running
    """
    return {"status": "alive", "timestamp": datetime.utcnow()}


@router.get("/health/ready", response_model=HealthResponse)
async def readiness_probe(db: AsyncSession = Depends(get_async_db)):
    """
    Readiness probe - checks if the service is ready to handle requests
    Checks database and broker connectivity
    """
    try:
        # Check database connectivity
        db_healthy = await check_async_database_connection()
        
        # Check broker connectivity (Redis)
        broker_healthy = await check_broker_connection()
        
        # Check notification services
        notification_service = NotificationService()
        service_health = notification_service.check_health()
        
        overall_status = "ready" if (
            db_healthy and broker_healthy
        ) else "not_ready"
        
        response = HealthResponse(
            status=overall_status,
            database="healthy" if db_healthy else "unhealthy",
            broker="healthy" if broker_healthy else "unhealthy",
            timestamp=datetime.utcnow()
        )
        
        # Return 503 if not ready
        if overall_status != "ready":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=response.dict()
            )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "error",
                "database": "unknown",
                "broker": "unknown",
                "error": str(e),
                "timestamp": datetime.utcnow()
            }
        )


async def check_broker_connection() -> bool:
    """Check if Redis/Celery broker is accessible"""
    try:
        import redis
        from app.core.config import settings
        
        # Parse Redis URL
        if settings.celery_broker_url.startswith('redis://'):
            redis_url = settings.celery_broker_url
        else:
            redis_url = 'redis://localhost:6379/0'
        
        # Create Redis client
        r = redis.from_url(redis_url)
        
        # Simple ping test
        response = r.ping()
        return response is True
        
    except Exception as e:
        logger.error(f"Broker connection check failed: {e}")
        return False


@router.get("/health/status")
async def detailed_status():
    """
    Detailed health status including all components
    """
    try:
        # Check database
        db_healthy = await check_async_database_connection()
        
        # Check broker
        broker_healthy = await check_broker_connection()
        
        # Check notification services
        notification_service = NotificationService()
        service_health = notification_service.check_health()
        
        return {
            "service": "notification-service",
            "status": "healthy" if (db_healthy and broker_healthy) else "degraded",
            "components": {
                "database": {
                    "status": "healthy" if db_healthy else "unhealthy",
                    "type": "postgresql"
                },
                "broker": {
                    "status": "healthy" if broker_healthy else "unhealthy",
                    "type": "redis"
                },
                "email_service": {
                    "status": "healthy" if service_health.get('email_service') else "unhealthy",
                    "type": "sendgrid"
                },
                "sms_service": {
                    "status": "healthy" if service_health.get('sms_service') else "unhealthy",
                    "type": "twilio"
                }
            },
            "timestamp": datetime.utcnow(),
            "version": "1.0.0"
        }
        
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        return {
            "service": "notification-service",
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow()
        } 