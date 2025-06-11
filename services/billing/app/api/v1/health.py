from datetime import datetime
from fastapi import APIRouter, status

router = APIRouter()

@router.get("/live", status_code=status.HTTP_200_OK)
async def live():
    return {"status":"healthy","timestamp":datetime.utcnow()}

@router.get("/ready", status_code=status.HTTP_200_OK)
async def ready():
    return {"status":"ready","timestamp":datetime.utcnow()} 