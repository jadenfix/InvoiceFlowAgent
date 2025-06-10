"""
Health check endpoints for the extraction service
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime
from typing import Dict, Any

from ..core.logging import get_logger
from ..models.invoice import HealthStatus
from ..services.database_service import database_service
from ..services.s3_service import s3_service
from ..services.message_queue import message_queue_service
from ..services.ocr_service import ocr_service
from ..services.llm_service import llm_service


router = APIRouter()
logger = get_logger(__name__)


@router.get("/health/live", response_model=Dict[str, str])
async def liveness_check():
    """
    Liveness probe - returns 200 if the service is running
    """
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@router.get("/health/ready", response_model=Dict[str, Any])
async def readiness_check():
    """
    Readiness probe - checks all dependencies
    Returns 200 if all dependencies are healthy, 503 if any are unhealthy
    """
    health_status = {
        "service": "extract-service",
        "dependencies": {},
        "timestamp": datetime.utcnow().isoformat()
    }
    
    all_healthy = True
    
    # Check database
    try:
        db_healthy = await database_service.health_check()
        health_status["dependencies"]["database"] = "healthy" if db_healthy else "unhealthy"
        if not db_healthy:
            all_healthy = False
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        health_status["dependencies"]["database"] = "unhealthy"
        all_healthy = False
    
    # Check S3
    try:
        s3_healthy = await s3_service.health_check()
        health_status["dependencies"]["s3"] = "healthy" if s3_healthy else "unhealthy"
        if not s3_healthy:
            all_healthy = False
    except Exception as e:
        logger.error(f"S3 health check failed: {e}")
        health_status["dependencies"]["s3"] = "unhealthy"
        all_healthy = False
    
    # Check RabbitMQ
    try:
        mq_healthy = await message_queue_service.health_check()
        health_status["dependencies"]["rabbitmq"] = "healthy" if mq_healthy else "unhealthy"
        if not mq_healthy:
            all_healthy = False
    except Exception as e:
        logger.error(f"RabbitMQ health check failed: {e}")
        health_status["dependencies"]["rabbitmq"] = "unhealthy"
        all_healthy = False
    
    # Check OCR service (non-critical)
    try:
        ocr_healthy = await ocr_service.health_check()
        health_status["dependencies"]["ocr"] = "healthy" if ocr_healthy else "degraded"
    except Exception as e:
        logger.error(f"OCR health check failed: {e}")
        health_status["dependencies"]["ocr"] = "degraded"
    
    # Check LLM service (non-critical)
    try:
        llm_healthy = await llm_service.health_check()
        health_status["dependencies"]["llm"] = "healthy" if llm_healthy else "degraded"
    except Exception as e:
        logger.error(f"LLM health check failed: {e}")
        health_status["dependencies"]["llm"] = "degraded"
    
    # Return appropriate status code
    if all_healthy:
        return health_status
    else:
        raise HTTPException(status_code=503, detail=health_status)


@router.get("/health/detailed", response_model=Dict[str, Any])
async def detailed_health_check():
    """
    Detailed health check with additional metrics and information
    """
    health_info = {
        "service": "extract-service",
        "timestamp": datetime.utcnow().isoformat(),
        "dependencies": {},
        "metrics": {
            "uptime": "unknown",  # Could add actual uptime tracking
            "processed_messages": "unknown",  # Could add message counter
            "success_rate": "unknown"  # Could add success rate tracking
        }
    }
    
    # Detailed dependency checks
    dependencies = [
        ("database", database_service.health_check),
        ("s3", s3_service.health_check),
        ("rabbitmq", message_queue_service.health_check),
        ("ocr", ocr_service.health_check),
        ("llm", llm_service.health_check)
    ]
    
    for dep_name, health_func in dependencies:
        try:
            start_time = datetime.utcnow()
            is_healthy = await health_func()
            end_time = datetime.utcnow()
            response_time = (end_time - start_time).total_seconds() * 1000  # ms
            
            health_info["dependencies"][dep_name] = {
                "status": "healthy" if is_healthy else "unhealthy",
                "response_time_ms": round(response_time, 2),
                "last_checked": end_time.isoformat()
            }
            
        except Exception as e:
            health_info["dependencies"][dep_name] = {
                "status": "error",
                "error": str(e),
                "last_checked": datetime.utcnow().isoformat()
            }
    
    return health_info 