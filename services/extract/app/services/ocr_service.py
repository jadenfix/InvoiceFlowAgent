"""
OCR service with AWS Textract and Tesseract fallback
"""
import asyncio
import json
import time
import tempfile
import os
from typing import Dict, Any, Optional, List, Tuple
from PIL import Image
import pytesseract
import pdf2image
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from tenacity import retry, stop_after_attempt, wait_exponential

from ..core.config import settings, get_textract_config
from ..core.logging import get_logger, log_processing_step, log_error
from ..models.invoice import OCRResult


logger = get_logger(__name__)


class OCRService:
    """OCR service for text extraction from PDFs"""
    
    def __init__(self):
        self.textract_config = get_textract_config()
        self.textract_client = None
    
    def _get_textract_client(self):
        """Get or create Textract client"""
        if self.textract_client is None:
            self.textract_client = boto3.client('textract', **self.textract_config)
        return self.textract_client
    
    @retry(
        stop=stop_after_attempt(settings.TEXTRACT_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, max=10)
    )
    async def extract_with_textract(self, pdf_bytes: bytes, request_id: str) -> Optional[OCRResult]:
        """Extract text using AWS Textract"""
        log_processing_step("textract_extraction", request_id)
        
        try:
            # Run Textract in a thread pool since it's not async
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, 
                self._run_textract_sync, 
                pdf_bytes, 
                request_id
            )
            return result
            
        except NoCredentialsError as e:
            log_error(e, {"operation": "textract", "request_id": request_id})
            logger.warning(f"AWS credentials not found for request {request_id}")
            return None
            
        except ClientError as e:
            log_error(e, {"operation": "textract", "request_id": request_id})
            error_code = e.response['Error']['Code']
            
            if error_code in ['InvalidParameterException', 'UnsupportedDocumentException']:
                logger.warning(f"Textract cannot process document for request {request_id}: {error_code}")
                return None
            
            # Re-raise for retry
            raise
            
        except Exception as e:
            log_error(e, {"operation": "textract", "request_id": request_id})
            raise
    
    def _run_textract_sync(self, pdf_bytes: bytes, request_id: str) -> OCRResult:
        """Run Textract synchronously"""
        client = self._get_textract_client()
        
        response = client.detect_document_text(
            Document={'Bytes': pdf_bytes}
        )
        
        # Extract text from blocks
        text_lines = []
        blocks = response.get('Blocks', [])
        
        for block in blocks:
            if block['BlockType'] == 'LINE':
                text_lines.append(block['Text'])
        
        full_text = '\n'.join(text_lines)
        
        # Calculate average confidence
        confidences = [
            block.get('Confidence', 0) 
            for block in blocks 
            if 'Confidence' in block
        ]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0
        
        return OCRResult(
            text=full_text,
            confidence=avg_confidence / 100.0,  # Convert to 0-1 scale
            method="textract",
            blocks=blocks
        )
    
    async def extract_with_tesseract(self, pdf_bytes: bytes, request_id: str) -> OCRResult:
        """Extract text using Tesseract OCR as fallback"""
        log_processing_step("tesseract_extraction", request_id)
        
        try:
            # Run Tesseract in a thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, 
                self._run_tesseract_sync, 
                pdf_bytes, 
                request_id
            )
            return result
            
        except Exception as e:
            log_error(e, {"operation": "tesseract", "request_id": request_id})
            raise
    
    def _run_tesseract_sync(self, pdf_bytes: bytes, request_id: str) -> OCRResult:
        """Run Tesseract synchronously"""
        text_lines = []
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Save PDF to temporary file
            pdf_path = os.path.join(temp_dir, f"{request_id}.pdf")
            with open(pdf_path, 'wb') as f:
                f.write(pdf_bytes)
            
            # Convert PDF to images
            try:
                images = pdf2image.convert_from_path(
                    pdf_path,
                    dpi=settings.PDF_DPI,
                    fmt='PNG'
                )
                
                # Process each page
                for i, image in enumerate(images):
                    logger.info(f"Processing page {i+1}/{len(images)} for request {request_id}")
                    
                    # Extract text from image
                    custom_config = f'--oem 3 --psm {settings.OCR_PSM} -l {settings.OCR_LANGUAGE}'
                    text = pytesseract.image_to_string(image, config=custom_config)
                    
                    if text.strip():
                        text_lines.append(text.strip())
                
            except Exception as e:
                log_error(e, {"operation": "pdf_to_image", "request_id": request_id})
                raise
        
        full_text = '\n\n'.join(text_lines)
        
        return OCRResult(
            text=full_text,
            confidence=None,  # Tesseract confidence not easily available
            method="tesseract",
            blocks=None
        )
    
    async def extract_text(self, pdf_bytes: bytes, request_id: str) -> OCRResult:
        """
        Extract text from PDF using Textract with Tesseract fallback
        
        Args:
            pdf_bytes: PDF file content as bytes
            request_id: Request ID for logging
            
        Returns:
            OCRResult with extracted text and metadata
        """
        start_time = time.time()
        
        try:
            # Try Textract first
            textract_result = await self.extract_with_textract(pdf_bytes, request_id)
            
            if textract_result and textract_result.text.strip():
                logger.info(f"Textract extraction successful for request {request_id}")
                return textract_result
            
            # Fallback to Tesseract if enabled
            if settings.OCR_FALLBACK_ENABLED:
                logger.info(f"Falling back to Tesseract for request {request_id}")
                tesseract_result = await self.extract_with_tesseract(pdf_bytes, request_id)
                return tesseract_result
            else:
                logger.warning(f"Textract failed and fallback disabled for request {request_id}")
                return OCRResult(
                    text="",
                    confidence=0.0,
                    method="textract_failed",
                    blocks=None
                )
                
        except Exception as e:
            log_error(e, {"operation": "ocr_extraction", "request_id": request_id})
            
            # Last resort: try Tesseract if not already tried
            if settings.OCR_FALLBACK_ENABLED:
                try:
                    logger.info(f"Emergency fallback to Tesseract for request {request_id}")
                    tesseract_result = await self.extract_with_tesseract(pdf_bytes, request_id)
                    return tesseract_result
                except Exception as fallback_error:
                    log_error(fallback_error, {"operation": "tesseract_fallback", "request_id": request_id})
            
            # If all methods fail, return empty result
            return OCRResult(
                text="",
                confidence=0.0,
                method="failed",
                blocks=None
            )
        
        finally:
            duration = time.time() - start_time
            logger.info(f"OCR extraction completed in {duration:.2f}s for request {request_id}")
    
    async def health_check(self) -> bool:
        """Health check for OCR services"""
        try:
            # Test Textract connection
            if self.textract_config.get('aws_access_key_id'):
                client = self._get_textract_client()
                # Simple operation to test connectivity
                await asyncio.get_event_loop().run_in_executor(
                    None, 
                    lambda: client.meta.client.describe_regions()
                )
            
            # Test Tesseract availability
            if settings.OCR_FALLBACK_ENABLED:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: pytesseract.get_tesseract_version()
                )
            
            return True
            
        except Exception as e:
            log_error(e, {"operation": "ocr_health_check"})
            return False


# Create service instance
ocr_service = OCRService() 