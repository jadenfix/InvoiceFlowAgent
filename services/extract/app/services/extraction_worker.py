"""
Main extraction worker that orchestrates the entire extraction pipeline
"""
import time
import asyncio
from typing import Optional
from datetime import datetime

from ..core.config import settings
from ..core.logging import get_logger, log_processing_step, log_error
from ..models.invoice import (
    IngestMessage, ExtractedMessage, ExtractionStatus, 
    InvoiceFields, OCRResult
)
from .ocr_service import ocr_service
from .llm_service import llm_service
from .s3_service import s3_service
from .database_service import database_service
from .message_queue import message_queue_service


logger = get_logger(__name__)


class ExtractionWorker:
    """Main extraction worker service"""
    
    def __init__(self):
        self.is_running = False
    
    async def process_message(self, message: IngestMessage) -> bool:
        """
        Process a single message from the ingest queue
        
        Args:
            message: Ingest message to process
            
        Returns:
            True if successful, False otherwise
        """
        request_id = message.request_id
        start_time = time.time()
        
        log_processing_step("extraction_start", request_id, filename=message.filename)
        
        try:
            # Step 1: Update ingestion status to PROCESSING
            success = await database_service.update_ingestion_status(
                request_id, 
                "PROCESSING"
            )
            
            if not success:
                logger.error(f"Failed to update ingestion status for request {request_id}")
                return False
            
            # Step 2: Download PDF from S3
            pdf_content = await s3_service.download_file(message.s3_key, request_id)
            
            if not pdf_content:
                logger.error(f"Failed to download PDF for request {request_id}")
                await self._handle_failure(request_id, "Failed to download PDF from S3")
                return False
            
            # Step 3: Extract text using OCR
            ocr_result = await ocr_service.extract_text(pdf_content, request_id)
            
            if not ocr_result.text.strip():
                logger.warning(f"OCR returned empty text for request {request_id}")
                await self._handle_failure(request_id, "OCR extraction returned empty text")
                return False
            
            # Step 4: Upload raw OCR data to S3
            raw_ocr_key = s3_service.generate_raw_ocr_key(request_id)
            ocr_data = {
                "request_id": request_id,
                "text": ocr_result.text,
                "confidence": ocr_result.confidence,
                "method": ocr_result.method,
                "blocks": ocr_result.blocks,
                "timestamp": datetime.utcnow().isoformat(),
                "original_file": message.filename
            }
            
            success = await s3_service.upload_json(ocr_data, raw_ocr_key, request_id)
            
            if not success:
                logger.error(f"Failed to upload raw OCR data for request {request_id}")
                await self._handle_failure(request_id, "Failed to upload raw OCR data to S3")
                return False
            
            # Step 5: Extract structured fields using LLM
            try:
                extracted_fields = await llm_service.extract_fields(
                    ocr_result.text, 
                    request_id
                )
            except Exception as e:
                log_error(e, {"operation": "llm_extraction", "request_id": request_id})
                logger.error(f"LLM extraction failed for request {request_id}")
                await self._handle_failure(request_id, f"LLM extraction failed: {str(e)}")
                return False
            
            # Step 6: Create invoice raw record in database
            invoice_raw_id = await database_service.create_invoice_raw(
                request_id,
                raw_ocr_key,
                extracted_fields,
                ExtractionStatus.COMPLETED
            )
            
            if not invoice_raw_id:
                logger.error(f"Failed to create invoice raw record for request {request_id}")
                await self._handle_failure(request_id, "Failed to create database record")
                return False
            
            # Step 7: Publish extracted message to queue
            extracted_message = ExtractedMessage(
                request_id=request_id,
                raw_key=raw_ocr_key,
                fields=extracted_fields,
                timestamp=datetime.utcnow()
            )
            
            success = await message_queue_service.publish_extracted_message(
                extracted_message,
                request_id
            )
            
            if not success:
                logger.warning(f"Failed to publish extracted message for request {request_id}")
                # Don't fail the entire process for this
            
            # Success!
            duration = time.time() - start_time
            logger.info(
                f"Extraction completed successfully for request {request_id} "
                f"in {duration:.2f}s"
            )
            
            return True
            
        except Exception as e:
            log_error(e, {"operation": "extraction_process", "request_id": request_id})
            logger.error(f"Unexpected error during extraction for request {request_id}")
            await self._handle_failure(request_id, f"Unexpected error: {str(e)}")
            return False
    
    async def _handle_failure(self, request_id: str, error_message: str):
        """Handle extraction failure"""
        log_processing_step("extraction_failure", request_id, error=error_message)
        
        try:
            # Update ingestion status to FAILED
            await database_service.update_ingestion_status(request_id, "FAILED")
            
        except Exception as e:
            log_error(e, {"operation": "handle_failure", "request_id": request_id})
    
    async def health_check(self) -> dict:
        """Comprehensive health check for all services"""
        health_status = {
            "worker": "healthy" if self.is_running else "stopped",
            "database": "unknown",
            "s3": "unknown", 
            "rabbitmq": "unknown",
            "ocr": "unknown",
            "llm": "unknown"
        }
        
        # Check all services
        try:
            health_status["database"] = "healthy" if await database_service.health_check() else "unhealthy"
        except Exception:
            health_status["database"] = "unhealthy"
        
        try:
            health_status["s3"] = "healthy" if await s3_service.health_check() else "unhealthy"
        except Exception:
            health_status["s3"] = "unhealthy"
        
        try:
            health_status["rabbitmq"] = "healthy" if await message_queue_service.health_check() else "unhealthy"
        except Exception:
            health_status["rabbitmq"] = "unhealthy"
        
        try:
            health_status["ocr"] = "healthy" if await ocr_service.health_check() else "unhealthy"
        except Exception:
            health_status["ocr"] = "unhealthy"
        
        try:
            health_status["llm"] = "healthy" if await llm_service.health_check() else "unhealthy"
        except Exception:
            health_status["llm"] = "unhealthy"
        
        return health_status


# Create worker instance
extraction_worker = ExtractionWorker()
