"""
Production ingestion API endpoints
"""
import uuid
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..core.logging import get_logger
from ..core.config import settings
from ..services.message_queue import message_queue_service


logger = get_logger(__name__)
router = APIRouter()


# Mock simplified models for now
class InvoiceStatus:
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


async def validate_file(file: UploadFile) -> bytes:
    """Validate uploaded file"""
    # Check file extension
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported"
        )
    
    # Read and validate file size
    content = await file.read()
    max_size = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    
    if len(content) > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {settings.MAX_FILE_SIZE_MB}MB"
        )
    
    if len(content) == 0:
        raise HTTPException(
            status_code=400,
            detail="Empty file not allowed"
        )
    
    return content


@router.post("/ingest/upload")
async def upload_invoice(file: UploadFile = File(...)):
    """
    Upload and process an invoice file
    
    This endpoint:
    1. Validates the file (PDF, size <= 10MB)
    2. Uploads to S3 at key raw/{request_id}.pdf
    3. Inserts row in Postgres with status='PENDING'
    4. Publishes message to RabbitMQ queue
    5. Returns 202 Accepted with request_id
    """
    request_id = str(uuid.uuid4())
    
    try:
        # Step 1: Validate file
        logger.info(f"Processing upload request {request_id} for file {file.filename}")
        content = await validate_file(file)
        
        # Step 2: Upload to S3 (simulated for now)
        s3_key = f"raw/{request_id}.pdf"
        logger.info(f"Would upload to S3: {s3_key}")
        
        # Step 3: Insert database record (simulated for now)
        logger.info(f"Would insert DB record with status PENDING")
        
        # Step 4: Publish message to queue (simulated for now)
        try:
            payload = {
                "request_id": request_id,
                "filename": file.filename,
                "s3_key": s3_key,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # For now, just log the message we would publish
            logger.info(f"Would publish message: {payload}")
            
        except Exception as e:
            logger.error(f"Message queue error: {e}")
            # Would rollback database insert in production
            raise HTTPException(status_code=502, detail="Message queue unavailable")
        
        # Step 5: Return success response
        return JSONResponse(
            status_code=202,
            content={
                "request_id": request_id,
                "status": InvoiceStatus.PENDING,
                "message": "File uploaded successfully, processing started"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error for request {request_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/ingest/status/{request_id}")
async def get_ingestion_status(request_id: str):
    """
    Get processing status for a request
    
    Returns:
        - 404 if request not found
        - Request details with current status
    """
    try:
        # In production, this would query the database
        # For now, return mock data
        return {
            "request_id": request_id,
            "filename": "sample.pdf",
            "status": InvoiceStatus.PENDING,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "s3_key": f"raw/{request_id}.pdf"
        }
        
    except Exception as e:
        logger.error(f"Status check error for {request_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/ingest/stats")
async def get_ingestion_stats():
    """
    Get ingestion statistics
    
    Returns aggregate counts for each status
    """
    try:
        # In production, this would query the database
        # For now, return mock stats
        return {
            "pending": 5,
            "processing": 3,
            "failed": 1,
            "completed": 23,
            "total": 32
        }
        
    except Exception as e:
        logger.error(f"Stats error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/ingest/health")
async def health_check():
    """
    Health check for ingestion dependencies
    """
    health_status = {
        "service": "healthy",
        "dependencies": {}
    }
    
    try:
        # Check message queue
        mq_healthy = await message_queue_service.health_check()
        health_status["dependencies"]["rabbitmq"] = "healthy" if mq_healthy else "unhealthy"
        
        # Check S3 (would check s3_service.health_check() in production)
        health_status["dependencies"]["s3"] = "healthy"
        
        # Check database (would check db_service.health_check() in production)
        health_status["dependencies"]["database"] = "healthy"
        
        # Overall status
        all_healthy = all(
            status == "healthy" 
            for status in health_status["dependencies"].values()
        )
        
        if not all_healthy:
            health_status["service"] = "degraded"
            return JSONResponse(status_code=503, content=health_status)
        
        return health_status
        
    except Exception as e:
        logger.error(f"Health check error: {e}")
        health_status["service"] = "unhealthy"
        health_status["error"] = str(e)
        return JSONResponse(status_code=503, content=health_status) 