"""Health check endpoints."""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.schemas import HealthResponse, ReadinessResponse
from ...core.config import settings
from ...core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/live", response_model=HealthResponse)
async def liveness_probe():
    """Liveness probe endpoint."""
    return HealthResponse(
        status="healthy",
        service=settings.service_name,
        version=settings.service_version,
        timestamp=datetime.utcnow()
    )


@router.get("/ready", response_model=ReadinessResponse)
async def readiness_probe():
    """Readiness probe endpoint."""
    
    checks = {}
    overall_status = "healthy"
    
    # Only check dependencies if not in development mode
    if settings.environment != "development":
        # Check database connection
        try:
            from ...models.database import get_db_session
            # Try to get a session and execute a simple query
            async with get_db_session() as session:
                await session.execute("SELECT 1")
            checks["database"] = "healthy"
            logger.debug("Database check passed")
        except Exception as e:
            checks["database"] = f"unhealthy: {str(e)}"
            overall_status = "unhealthy"
            logger.error("Database check failed", error=str(e))
        
        # Check RabbitMQ connection
        try:
            from ...services.message_service import message_service
            if await message_service.health_check():
                checks["rabbitmq"] = "healthy"
                logger.debug("RabbitMQ check passed")
            else:
                checks["rabbitmq"] = "unhealthy: connection closed"
                overall_status = "unhealthy"
                logger.error("RabbitMQ check failed: connection closed")
        except Exception as e:
            checks["rabbitmq"] = f"unhealthy: {str(e)}"
            overall_status = "unhealthy"
            logger.error("RabbitMQ check failed", error=str(e))
    else:
        # In development mode, report as healthy
        checks["database"] = "skipped (development mode)"
        checks["rabbitmq"] = "skipped (development mode)"
        logger.debug("Health checks skipped in development mode")
    
    if overall_status == "unhealthy" and settings.environment == "production":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not ready"
        )
    
    return ReadinessResponse(
        status=overall_status,
        service=settings.service_name,
        version=settings.service_version,
        timestamp=datetime.utcnow(),
        checks=checks
    ) 