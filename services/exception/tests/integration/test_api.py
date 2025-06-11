"""Integration tests for Exception Review API."""

import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient


class TestHealthEndpoints:
    """Test health check endpoints."""
    
    @pytest.mark.asyncio
    async def test_liveness_probe(self, test_client: AsyncClient):
        """Test liveness probe endpoint."""
        response = await test_client.get("/health/live")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "exception-review"
        assert "timestamp" in data
    
    @pytest.mark.asyncio
    async def test_readiness_probe(self, test_client: AsyncClient):
        """Test readiness probe endpoint."""
        response = await test_client.get("/health/ready")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "exception-review"
        assert "checks" in data
        assert "database" in data["checks"]
        assert "rabbitmq" in data["checks"]


class TestReviewQueueEndpoints:
    """Test review queue endpoints."""
    
    @pytest.mark.asyncio
    async def test_get_empty_queue(self, test_client: AsyncClient):
        """Test getting empty review queue."""
        response = await test_client.get("/api/v1/review/queue")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert not data["has_next"]
        assert not data["has_prev"]
    
    @pytest.mark.asyncio
    async def test_get_queue_with_items(self, test_client: AsyncClient, sample_invoice):
        """Test getting review queue with items."""
        response = await test_client.get("/api/v1/review/queue")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        
        item = data["items"][0]
        assert item["id"] == str(sample_invoice.id)
        assert item["vendor_name"] == sample_invoice.vendor_name
        assert item["matched_status"] == sample_invoice.matched_status
    
    @pytest.mark.asyncio
    async def test_get_queue_pagination(self, test_client: AsyncClient, multiple_invoices):
        """Test review queue pagination."""
        # Test first page
        response = await test_client.get("/api/v1/review/queue?page=1&page_size=10")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 25
        assert len(data["items"]) == 10
        assert data["page"] == 1
        assert data["page_size"] == 10
        assert data["has_next"]
        assert not data["has_prev"]
        
        # Test second page
        response = await test_client.get("/api/v1/review/queue?page=2&page_size=10")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 25
        assert len(data["items"]) == 10
        assert data["page"] == 2
        assert data["has_next"]
        assert data["has_prev"]
    
    @pytest.mark.asyncio
    async def test_get_queue_filtering(self, test_client: AsyncClient, multiple_invoices):
        """Test review queue filtering."""
        response = await test_client.get("/api/v1/review/queue?vendor_filter=Vendor 1")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should match "Vendor 1", "Vendor 10", "Vendor 11", etc.
        assert data["total"] > 0
        for item in data["items"]:
            assert "Vendor 1" in item["vendor_name"]
    
    @pytest.mark.asyncio
    async def test_get_queue_sorting(self, test_client: AsyncClient, multiple_invoices):
        """Test review queue sorting."""
        # Test ascending sort by amount
        response = await test_client.get("/api/v1/review/queue?sort_by=total_amount&sort_order=asc")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify sorting (amounts should be in ascending order)
        amounts = [item["total_amount"] for item in data["items"] if item["total_amount"]]
        assert amounts == sorted(amounts)


class TestInvoiceDetailEndpoints:
    """Test invoice detail endpoints."""
    
    @pytest.mark.asyncio
    async def test_get_invoice_detail_success(self, test_client: AsyncClient, sample_invoice):
        """Test getting invoice detail successfully."""
        response = await test_client.get(f"/api/v1/review/{sample_invoice.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_invoice.id)
        assert data["vendor_name"] == sample_invoice.vendor_name
        assert data["matched_status"] == sample_invoice.matched_status
        assert data["confidence_score"] == float(sample_invoice.confidence_score)
    
    @pytest.mark.asyncio
    async def test_get_invoice_detail_not_found(self, test_client: AsyncClient):
        """Test getting invoice detail when not found."""
        invoice_id = str(uuid.uuid4())
        response = await test_client.get(f"/api/v1/review/{invoice_id}")
        
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["message"].lower()


class TestReviewActionEndpoints:
    """Test review action endpoints."""
    
    @pytest.mark.asyncio
    async def test_approve_invoice_success(
        self, 
        test_client: AsyncClient, 
        sample_invoice, 
        approve_request_data
    ):
        """Test approving invoice successfully."""
        response = await test_client.post(
            f"/api/v1/review/{sample_invoice.id}/approve",
            json=approve_request_data
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["invoice_id"] == str(sample_invoice.id)
        assert data["action"] == "approve"
        assert data["reviewed_by"] == approve_request_data["reviewed_by"]
        assert "reviewed_at" in data
    
    @pytest.mark.asyncio
    async def test_approve_invoice_not_found(self, test_client: AsyncClient, approve_request_data):
        """Test approving invoice when not found."""
        invoice_id = str(uuid.uuid4())
        response = await test_client.post(
            f"/api/v1/review/{invoice_id}/approve",
            json=approve_request_data
        )
        
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["message"].lower()
    
    @pytest.mark.asyncio
    async def test_approve_invoice_already_reviewed(
        self, 
        test_client: AsyncClient, 
        reviewed_invoice, 
        approve_request_data
    ):
        """Test approving invoice that's already reviewed."""
        response = await test_client.post(
            f"/api/v1/review/{reviewed_invoice.id}/approve",
            json=approve_request_data
        )
        
        assert response.status_code == 409
        data = response.json()
        assert "already been reviewed" in data["message"].lower()
    
    @pytest.mark.asyncio
    async def test_reject_invoice_success(
        self, 
        test_client: AsyncClient, 
        sample_invoice, 
        reject_request_data
    ):
        """Test rejecting invoice successfully."""
        response = await test_client.post(
            f"/api/v1/review/{sample_invoice.id}/reject",
            json=reject_request_data
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["invoice_id"] == str(sample_invoice.id)
        assert data["action"] == "reject"
        assert data["reviewed_by"] == reject_request_data["reviewed_by"]
        assert data["review_notes"] == reject_request_data["review_notes"]
    
    @pytest.mark.asyncio
    async def test_reject_invoice_without_notes(
        self, 
        test_client: AsyncClient, 
        sample_invoice
    ):
        """Test rejecting invoice without required notes."""
        request_data = {
            "reviewed_by": "test_reviewer"
            # Missing review_notes
        }
        
        response = await test_client.post(
            f"/api/v1/review/{sample_invoice.id}/reject",
            json=request_data
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "validation" in data["error"].lower()
        
        # Check that review_notes field is in error details
        found_notes_error = False
        for detail in data["details"]:
            if "review_notes" in detail["field"]:
                found_notes_error = True
                break
        assert found_notes_error
    
    @pytest.mark.asyncio
    async def test_approve_invoice_invalid_data(self, test_client: AsyncClient, sample_invoice):
        """Test approving invoice with invalid data."""
        request_data = {
            # Missing reviewed_by
            "review_notes": "Some notes"
        }
        
        response = await test_client.post(
            f"/api/v1/review/{sample_invoice.id}/approve",
            json=request_data
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "validation" in data["error"].lower()


class TestRootEndpoint:
    """Test root endpoint."""
    
    @pytest.mark.asyncio
    async def test_root_endpoint(self, test_client: AsyncClient):
        """Test root endpoint returns service information."""
        response = await test_client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "exception-review"
        assert "version" in data
        assert "description" in data
        assert "docs_url" in data 