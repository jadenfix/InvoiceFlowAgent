"""
Health check endpoints for InvoiceFlow Auth Service
Provides liveness and readiness probes for Kubernetes
"""
import time
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from app.core.database import check_db_health
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("auth.health")
router = APIRouter(tags=["health"])

# Track service start time
service_start_time = time.time()


@router.get("/healthz")
async def liveness_probe():
    """
    Kubernetes liveness probe endpoint.
    
    Checks if the service is alive and responding.
    Should return 200 if the service is running, even if dependencies are down.
    
    Returns:
    - HTTP 200 if service is alive
    - HTTP 503 if service is critically failed
    """
    try:
        uptime_seconds = int(time.time() - service_start_time)
        
        return {
            "status": "alive",
            "service": "invoiceflow-auth",
            "uptime_seconds": uptime_seconds,
            "timestamp": int(time.time()),
        }
        
    except Exception as e:
        logger.error(f"Liveness probe failed: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "service": "invoiceflow-auth",
                "error": "Service is not responding properly"
            }
        )


@router.get("/readyz")
async def readiness_probe():
    """
    Kubernetes readiness probe endpoint.
    
    Checks if the service is ready to handle requests.
    Should return 200 only when all dependencies are healthy.
    
    Returns:
    - HTTP 200 if service is ready
    - HTTP 503 if service is not ready (dependencies unhealthy)
    """
    try:
        # Check database health
        db_health = await check_db_health()
        
        # Calculate uptime
        uptime_seconds = int(time.time() - service_start_time)
        
        # Service is ready if database is healthy
        is_ready = db_health["status"] == "healthy"
        
        response_data = {
            "status": "ready" if is_ready else "not_ready",
            "service": "invoiceflow-auth",
            "uptime_seconds": uptime_seconds,
            "timestamp": int(time.time()),
            "checks": {
                "database": db_health,
                "configuration": {
                    "status": "healthy",
                    "environment": settings.environment,
                }
            }
        }
        
        if is_ready:
            return response_data
        else:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=response_data
            )
            
    except Exception as e:
        logger.error(f"Readiness probe failed: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "service": "invoiceflow-auth",
                "error": str(e),
                "timestamp": int(time.time()),
            }
        )


@router.get("/health")
async def detailed_health_check():
    """
    Detailed health check endpoint for monitoring and debugging.
    
    Provides comprehensive health information about the service and its dependencies.
    
    Returns:
    - Detailed health status
    - Database connection info
    - Configuration status
    - Performance metrics
    """
    try:
        start_time = time.time()
        
        # Check database health
        db_health = await check_db_health()
        
        # Calculate uptime
        uptime_seconds = int(time.time() - service_start_time)
        check_duration_ms = round((time.time() - start_time) * 1000, 2)
        
        # Determine overall status
        overall_status = "healthy" if db_health["status"] == "healthy" else "unhealthy"
        
        health_data = {
            "status": overall_status,
            "service": "invoiceflow-auth",
            "version": "1.0.0",
            "environment": settings.environment,
            "uptime_seconds": uptime_seconds,
            "check_duration_ms": check_duration_ms,
            "timestamp": int(time.time()),
            "checks": {
                "database": db_health,
                "configuration": {
                    "status": "healthy",
                    "jwt_configured": bool(settings.jwt_secret),
                    "database_configured": bool(settings.database_url),
                },
                "features": {
                    "authentication": True,
                    "rate_limiting": True,
                    "logging": True,
                    "metrics": settings.enable_metrics,
                }
            },
            "metrics": {
                "uptime_seconds": uptime_seconds,
                "check_duration_ms": check_duration_ms,
            }
        }
        
        # Return appropriate status code
        if overall_status == "healthy":
            return health_data
        else:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=health_data
            )
            
    except Exception as e:
        logger.error(f"Detailed health check failed: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "service": "invoiceflow-auth",
                "error": str(e),
                "timestamp": int(time.time()),
            }
        ) 