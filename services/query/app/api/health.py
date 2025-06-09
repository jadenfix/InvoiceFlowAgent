"""
Health check endpoints
"""
from fastapi import APIRouter
from datetime import datetime
from typing import Dict, Any

from ..core.config import settings
from ..core.logging import get_logger
from ..services.cache import cache_service
from ..services.search import search_service

logger = get_logger(__name__)
router = APIRouter()


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Service health check
    
    Returns:
        Health status of the service and its dependencies
    """
    start_time = datetime.utcnow()
    
    # Check cache service health
    cache_health = cache_service.health_check()
    
    # Check search service health  
    search_health = search_service.health_check()
    
    # Determine overall service status
    service_healthy = True
    if cache_health.get("status") == "unhealthy":
        service_healthy = False
    if search_health.get("status") == "unhealthy":
        service_healthy = False
    
    response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
    
    health_status = {
        "service": "query-service",
        "status": "healthy" if service_healthy else "degraded",
        "version": settings.version,
        "timestamp": start_time.isoformat() + "Z",
        "response_time_ms": round(response_time, 1),
        "dependencies": {
            "cache": cache_health,
            "search": search_health
        },
        "configuration": {
            "redis_configured": bool(settings.redis_url),
            "opensearch_configured": bool(settings.opensearch_host),
            "spacy_model": settings.spacy_model,
            "cache_ttl": settings.cache_ttl
        }
    }
    
    logger.info(f"Health check completed: {health_status['status']}")
    return health_status


@router.get("/health/live")
async def liveness_probe() -> Dict[str, str]:
    """
    Kubernetes liveness probe
    
    Returns:
        Simple status for liveness check
    """
    return {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


@router.get("/health/ready")
async def readiness_probe() -> Dict[str, Any]:
    """
    Kubernetes readiness probe
    
    Returns:
        Readiness status based on critical dependencies
    """
    # Service is ready if basic functionality works
    # Cache and search can be degraded but service can still function
    
    try:
        # Test basic parsing functionality
        from ..services.parser import QueryParser
        parser = QueryParser()
        
        # Simple test parse
        test_result, confidence = parser.parse_query("test query")
        
        return {
            "status": "ready",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "parser_functional": True
        }
        
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return {
            "status": "not_ready",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "error": str(e),
            "parser_functional": False
        } 