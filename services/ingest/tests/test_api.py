"""
Tests for ingestion API endpoints
"""
import pytest
import io
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from fastapi import UploadFile, HTTPException

from app.main import app
from app.api.ingest import validate_file


client = TestClient(app)


class TestValidateFile:
    """Tests for file validation"""
    
    @pytest.mark.asyncio
    async def test_valid_pdf_file(self):
        """Test valid PDF file validation"""
        content = b"fake pdf content"
        file = Mock(spec=UploadFile)
        file.filename = "test.pdf"
        file.read = AsyncMock(return_value=content)
        
        result = await validate_file(file)
        assert result == content
    
    @pytest.mark.asyncio
    async def test_invalid_file_extension(self):
        """Test rejection of non-PDF files"""
        file = Mock(spec=UploadFile)
        file.filename = "test.txt"
        
        with pytest.raises(HTTPException) as excinfo:
            await validate_file(file)
        assert excinfo.value.status_code == 400
        assert "Only PDF files are supported" in excinfo.value.detail
    
    @pytest.mark.asyncio
    async def test_file_too_large(self):
        """Test rejection of files that are too large"""
        content = b"x" * (11 * 1024 * 1024)  # 11MB
        file = Mock(spec=UploadFile)
        file.filename = "test.pdf"
        file.read = AsyncMock(return_value=content)
        
        with pytest.raises(HTTPException) as excinfo:
            await validate_file(file)
        assert excinfo.value.status_code == 413
        assert "File too large" in excinfo.value.detail
    
    @pytest.mark.asyncio
    async def test_empty_file(self):
        """Test rejection of empty files"""
        file = Mock(spec=UploadFile)
        file.filename = "test.pdf"
        file.read = AsyncMock(return_value=b"")
        
        with pytest.raises(HTTPException) as excinfo:
            await validate_file(file)
        assert excinfo.value.status_code == 400
        assert "Empty file not allowed" in excinfo.value.detail


class TestUploadEndpoint:
    """Tests for the upload endpoint"""
    
    def test_successful_upload(self):
        """Test successful file upload"""
        # Create test file
        test_content = b"fake pdf content"
        test_file = io.BytesIO(test_content)
        
        response = client.post(
            "/api/v1/ingest/upload",
            files={"file": ("test.pdf", test_file, "application/pdf")}
        )
        
        assert response.status_code == 202
        data = response.json()
        assert "request_id" in data
        assert data["status"] == "PENDING"
        assert "processing started" in data["message"]
    
    def test_upload_invalid_file_type(self):
        """Test upload with invalid file type"""
        test_content = b"fake content"
        test_file = io.BytesIO(test_content)
        
        response = client.post(
            "/api/v1/ingest/upload",
            files={"file": ("test.txt", test_file, "text/plain")}
        )
        
        assert response.status_code == 400
        # For FastAPI error responses, the error message is in the response content
        error_text = response.text
        assert "Only PDF files are supported" in error_text
    
    def test_upload_file_too_large(self):
        """Test upload with file that's too large"""
        # Create 11MB file
        test_content = b"x" * (11 * 1024 * 1024)
        test_file = io.BytesIO(test_content)
        
        response = client.post(
            "/api/v1/ingest/upload",
            files={"file": ("large.pdf", test_file, "application/pdf")}
        )
        
        assert response.status_code == 413
        error_text = response.text
        assert "File too large" in error_text
    
    def test_upload_empty_file(self):
        """Test upload with empty file"""
        test_file = io.BytesIO(b"")
        
        response = client.post(
            "/api/v1/ingest/upload",
            files={"file": ("empty.pdf", test_file, "application/pdf")}
        )
        
        assert response.status_code == 400
        error_text = response.text
        assert "Empty file not allowed" in error_text


class TestStatusEndpoint:
    """Tests for the status endpoint"""
    
    def test_get_status(self):
        """Test getting status for a request"""
        request_id = "test-request-id-123"
        
        response = client.get(f"/api/v1/ingest/status/{request_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["request_id"] == request_id
        assert "status" in data
        assert "created_at" in data
        assert "updated_at" in data
        assert "s3_key" in data


class TestStatsEndpoint:
    """Tests for the stats endpoint"""
    
    def test_get_stats(self):
        """Test getting ingestion statistics"""
        response = client.get("/api/v1/ingest/stats")
        
        assert response.status_code == 200
        data = response.json()
        assert "pending" in data
        assert "processing" in data
        assert "failed" in data
        assert "completed" in data
        assert "total" in data
        
        # Verify all values are integers
        for key, value in data.items():
            assert isinstance(value, int)


class TestHealthEndpoint:
    """Tests for the health endpoint"""
    
    def test_health_check_healthy(self):
        """Test health check when all services are healthy"""
        with patch('app.api.ingest.message_queue_service.health_check', return_value=True):
            response = client.get("/api/v1/ingest/health")
            
            assert response.status_code == 200
            data = response.json()
            assert data["service"] == "healthy"
            assert "dependencies" in data
    
    def test_health_check_degraded(self):
        """Test health check when some services are unhealthy"""
        with patch('app.api.ingest.message_queue_service.health_check', return_value=False):
            response = client.get("/api/v1/ingest/health")
            
            assert response.status_code == 503
            data = response.json()
            assert data["service"] == "degraded"
            assert data["dependencies"]["rabbitmq"] == "unhealthy"


class TestIntegrationScenarios:
    """Integration test scenarios"""
    
    def test_full_upload_workflow(self):
        """Test complete upload workflow"""
        # Step 1: Upload file
        test_content = b"fake pdf content"
        test_file = io.BytesIO(test_content)
        
        upload_response = client.post(
            "/api/v1/ingest/upload",
            files={"file": ("test.pdf", test_file, "application/pdf")}
        )
        
        assert upload_response.status_code == 202
        request_id = upload_response.json()["request_id"]
        
        # Step 2: Check status
        status_response = client.get(f"/api/v1/ingest/status/{request_id}")
        assert status_response.status_code == 200
        
        # Step 3: Check stats
        stats_response = client.get("/api/v1/ingest/stats")
        assert stats_response.status_code == 200
        
        # Step 4: Check health
        health_response = client.get("/api/v1/ingest/health")
        assert health_response.status_code in [200, 503]  # Depends on RabbitMQ availability 