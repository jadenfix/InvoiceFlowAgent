"""
Comprehensive tests for the extraction pipeline
"""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.models.invoice import IngestMessage, InvoiceFields, OCRResult, ExtractionStatus
from app.services.extraction_worker import ExtractionWorker
from app.services.ocr_service import OCRService
from app.services.llm_service import LLMService
from app.services.s3_service import S3Service
from app.services.database_service import DatabaseService
from app.services.message_queue import MessageQueueService


@pytest.fixture
def sample_ingest_message():
    """Sample ingest message for testing"""
    return IngestMessage(
        request_id="12345678-1234-1234-1234-123456789012",
        filename="test_invoice.pdf",
        s3_key="raw/12345678-1234-1234-1234-123456789012.pdf",
        timestamp=datetime.utcnow()
    )


@pytest.fixture
def sample_ocr_result():
    """Sample OCR result for testing"""
    return OCRResult(
        text="INVOICE\nVendor: ACME Corp\nInvoice #: INV-001\nTotal: $100.00",
        confidence=0.95,
        method="textract",
        blocks=[]
    )


@pytest.fixture
def sample_invoice_fields():
    """Sample extracted invoice fields for testing"""
    return InvoiceFields(
        vendor_name="ACME Corp",
        invoice_number="INV-001",
        invoice_date="2024-01-09",
        total_amount=100.00,
        currency="USD",
        line_items=[]
    )


@pytest.fixture
def mock_services():
    """Mock all external services"""
    return {
        'ocr_service': AsyncMock(spec=OCRService),
        'llm_service': AsyncMock(spec=LLMService),
        's3_service': AsyncMock(spec=S3Service),
        'database_service': AsyncMock(spec=DatabaseService),
        'message_queue_service': AsyncMock(spec=MessageQueueService)
    }


class TestExtractionPipeline:
    """Test the complete extraction pipeline"""
    
    @pytest.mark.asyncio
    async def test_successful_extraction_flow(
        self, 
        sample_ingest_message, 
        sample_ocr_result, 
        sample_invoice_fields,
        mock_services
    ):
        """Test successful end-to-end extraction"""
        # Setup mocks
        mock_services['database_service'].update_ingestion_status.return_value = True
        mock_services['s3_service'].download_file.return_value = b"fake_pdf_content"
        mock_services['ocr_service'].extract_text.return_value = sample_ocr_result
        mock_services['s3_service'].generate_raw_ocr_key.return_value = "extracted/raw/test.json"
        mock_services['s3_service'].upload_json.return_value = True
        mock_services['llm_service'].extract_fields.return_value = sample_invoice_fields
        mock_services['database_service'].create_invoice_raw.return_value = "invoice_raw_id"
        mock_services['message_queue_service'].publish_extracted_message.return_value = True
        
        # Create worker with mocked services
        worker = ExtractionWorker()
        
        # Patch the services
        with patch.multiple(
            'app.services.extraction_worker',
            database_service=mock_services['database_service'],
            s3_service=mock_services['s3_service'],
            ocr_service=mock_services['ocr_service'],
            llm_service=mock_services['llm_service'],
            message_queue_service=mock_services['message_queue_service']
        ):
            # Process the message
            result = await worker.process_message(sample_ingest_message)
        
        # Verify success
        assert result is True
        
        # Verify all services were called correctly
        mock_services['database_service'].update_ingestion_status.assert_called_with(
            sample_ingest_message.request_id, "PROCESSING"
        )
        mock_services['s3_service'].download_file.assert_called_with(
            sample_ingest_message.s3_key, sample_ingest_message.request_id
        )
        mock_services['ocr_service'].extract_text.assert_called_once()
        mock_services['llm_service'].extract_fields.assert_called_once()
        mock_services['database_service'].create_invoice_raw.assert_called_once()
        mock_services['message_queue_service'].publish_extracted_message.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_s3_download_failure(self, sample_ingest_message, mock_services):
        """Test handling of S3 download failure"""
        # Setup mocks - S3 download fails
        mock_services['database_service'].update_ingestion_status.return_value = True
        mock_services['s3_service'].download_file.return_value = None
        
        worker = ExtractionWorker()
        
        with patch.multiple(
            'app.services.extraction_worker',
            database_service=mock_services['database_service'],
            s3_service=mock_services['s3_service']
        ):
            result = await worker.process_message(sample_ingest_message)
        
        # Verify failure
        assert result is False
        
        # Verify error handling
        mock_services['database_service'].update_ingestion_status.assert_any_call(
            sample_ingest_message.request_id, "FAILED"
        )
    
    @pytest.mark.asyncio
    async def test_ocr_empty_text(
        self, 
        sample_ingest_message, 
        mock_services
    ):
        """Test handling when OCR returns empty text"""
        # Setup mocks - OCR returns empty result
        mock_services['database_service'].update_ingestion_status.return_value = True
        mock_services['s3_service'].download_file.return_value = b"fake_pdf_content"
        
        empty_ocr_result = OCRResult(
            text="",  # Empty text
            confidence=0.0,
            method="textract",
            blocks=[]
        )
        mock_services['ocr_service'].extract_text.return_value = empty_ocr_result
        
        worker = ExtractionWorker()
        
        with patch.multiple(
            'app.services.extraction_worker',
            database_service=mock_services['database_service'],
            s3_service=mock_services['s3_service'],
            ocr_service=mock_services['ocr_service']
        ):
            result = await worker.process_message(sample_ingest_message)
        
        # Verify failure
        assert result is False
        
        # Verify error handling
        mock_services['database_service'].update_ingestion_status.assert_any_call(
            sample_ingest_message.request_id, "FAILED"
        )
    
    @pytest.mark.asyncio
    async def test_llm_extraction_failure(
        self, 
        sample_ingest_message, 
        sample_ocr_result,
        mock_services
    ):
        """Test handling of LLM extraction failure"""
        # Setup mocks - LLM extraction fails
        mock_services['database_service'].update_ingestion_status.return_value = True
        mock_services['s3_service'].download_file.return_value = b"fake_pdf_content"
        mock_services['ocr_service'].extract_text.return_value = sample_ocr_result
        mock_services['s3_service'].generate_raw_ocr_key.return_value = "extracted/raw/test.json"
        mock_services['s3_service'].upload_json.return_value = True
        mock_services['llm_service'].extract_fields.side_effect = Exception("LLM API error")
        
        worker = ExtractionWorker()
        
        with patch.multiple(
            'app.services.extraction_worker',
            database_service=mock_services['database_service'],
            s3_service=mock_services['s3_service'],
            ocr_service=mock_services['ocr_service'],
            llm_service=mock_services['llm_service']
        ):
            result = await worker.process_message(sample_ingest_message)
        
        # Verify failure
        assert result is False
        
        # Verify error handling
        mock_services['database_service'].update_ingestion_status.assert_any_call(
            sample_ingest_message.request_id, "FAILED"
        )


class TestOCRService:
    """Test OCR service functionality"""
    
    @pytest.mark.asyncio
    async def test_textract_success(self):
        """Test successful Textract extraction"""
        ocr_service = OCRService()
        
        # Mock Textract response
        mock_response = {
            'Blocks': [
                {
                    'BlockType': 'LINE',
                    'Text': 'INVOICE',
                    'Confidence': 99.5
                },
                {
                    'BlockType': 'LINE', 
                    'Text': 'Total: $100.00',
                    'Confidence': 98.2
                }
            ]
        }
        
        with patch.object(ocr_service, '_run_textract_sync') as mock_textract:
            mock_textract.return_value = OCRResult(
                text="INVOICE\nTotal: $100.00",
                confidence=0.988,
                method="textract",
                blocks=mock_response['Blocks']
            )
            
            result = await ocr_service.extract_with_textract(b"fake_pdf", "test_id")
        
        assert result is not None
        assert result.text == "INVOICE\nTotal: $100.00"
        assert result.method == "textract"
        assert result.confidence > 0.9
    
    @pytest.mark.asyncio
    async def test_tesseract_fallback(self):
        """Test Tesseract fallback when Textract fails"""
        ocr_service = OCRService()
        
        with patch.object(ocr_service, 'extract_with_textract') as mock_textract, \
             patch.object(ocr_service, 'extract_with_tesseract') as mock_tesseract:
            
            # Textract returns None (failure)
            mock_textract.return_value = None
            
            # Tesseract returns result
            mock_tesseract.return_value = OCRResult(
                text="INVOICE\nTotal: $100.00",
                confidence=None,
                method="tesseract",
                blocks=None
            )
            
            result = await ocr_service.extract_text(b"fake_pdf", "test_id")
        
        assert result.method == "tesseract"
        assert result.text == "INVOICE\nTotal: $100.00"


class TestLLMService:
    """Test LLM service functionality"""
    
    @pytest.mark.asyncio
    async def test_field_extraction_success(self):
        """Test successful field extraction"""
        llm_service = LLMService()
        
        # Mock LangChain response
        mock_llm_response = {
            "vendor_name": "ACME Corp",
            "invoice_number": "INV-001",
            "invoice_date": "2024-01-09",
            "total_amount": 100.00,
            "currency": "USD",
            "line_items": []
        }
        
        with patch.object(llm_service, 'llm') as mock_llm, \
             patch.object(llm_service, 'parser') as mock_parser:
            
            # Setup mock chain
            mock_chain = AsyncMock()
            mock_chain.ainvoke.return_value = mock_llm_response
            
            # Mock the chain creation
            with patch('app.services.llm_service.PromptTemplate') as mock_prompt:
                mock_prompt.return_value.__or__ = lambda self, other: mock_chain
                
                result = await llm_service.extract_fields(
                    "INVOICE\nVendor: ACME Corp\nTotal: $100.00",
                    "test_id"
                )
        
        assert result.vendor_name == "ACME Corp"
        assert result.invoice_number == "INV-001"
        assert result.total_amount == 100.00
    
    @pytest.mark.asyncio
    async def test_empty_text_handling(self):
        """Test handling of empty input text"""
        llm_service = LLMService()
        
        result = await llm_service.extract_fields("", "test_id")
        
        # Should return empty InvoiceFields
        assert result.vendor_name is None
        assert result.total_amount is None


class TestHealthChecks:
    """Test health check functionality"""
    
    @pytest.mark.asyncio
    async def test_all_services_healthy(self, mock_services):
        """Test when all services are healthy"""
        # Setup all services as healthy
        for service in mock_services.values():
            service.health_check.return_value = True
        
        worker = ExtractionWorker()
        
        with patch.multiple(
            'app.services.extraction_worker',
            **mock_services
        ):
            health_status = await worker.health_check()
        
        # All dependencies should be healthy
        assert health_status["database"] == "healthy"
        assert health_status["s3"] == "healthy"
        assert health_status["rabbitmq"] == "healthy"
        assert health_status["ocr"] == "healthy"
        assert health_status["llm"] == "healthy"
    
    @pytest.mark.asyncio
    async def test_some_services_unhealthy(self, mock_services):
        """Test when some services are unhealthy"""
        # Setup mixed health status
        mock_services['database_service'].health_check.return_value = True
        mock_services['s3_service'].health_check.return_value = False
        mock_services['message_queue_service'].health_check.return_value = True
        mock_services['ocr_service'].health_check.return_value = False
        mock_services['llm_service'].health_check.return_value = True
        
        worker = ExtractionWorker()
        
        with patch.multiple(
            'app.services.extraction_worker',
            **mock_services
        ):
            health_status = await worker.health_check()
        
        # Check mixed status
        assert health_status["database"] == "healthy"
        assert health_status["s3"] == "unhealthy"
        assert health_status["rabbitmq"] == "healthy"
        assert health_status["ocr"] == "unhealthy"
        assert health_status["llm"] == "healthy"


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 