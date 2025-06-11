from fastapi import APIRouter, status
from datetime import datetime

router = APIRouter()


@router.get("/live", status_code=status.HTTP_200_OK)
async def liveness():
    return {"status": "healthy", "timestamp": datetime.utcnow()}


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness():
    # In production we'd check DB & RabbitMQ; dev-mode always healthy
    return {"status": "ready", "timestamp": datetime.utcnow()} 