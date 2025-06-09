"""
Health check endpoints
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any

from ..core.logging import get_logger


logger = get_logger(__name__)
router = APIRouter()


@router.get("/")
async def health_check() -> Dict[str, Any]:
    """Basic health check endpoint"""
    return {
        "status": "healthy",
        "service": "ingest-service"
    }


@router.get("/ready")
async def readiness_check() -> Dict[str, Any]:
    """Readiness check - simplified version"""
    return {
        "status": "ready",
        "service": "ingest-service",
        "message": "Service is ready (simplified check)"
    }


@router.get("/live")
async def liveness_check() -> Dict[str, Any]:
    """Liveness check - service is running"""
    return {
        "status": "alive",
        "service": "ingest-service"
    } 