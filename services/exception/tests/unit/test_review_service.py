"""Unit tests for review service."""

import uuid
from datetime import datetime
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from app.services.review_service import (
    ReviewService,
    InvoiceNotFoundError,
    AlreadyReviewedError,
)
from app.models.schemas import ApproveRequest, RejectRequest


class TestReviewService:
    """Test cases for ReviewService."""
    
    @pytest_asyncio.fixture
    async def mock_message_service(self):
        """Mock message service."""
        mock_service = AsyncMock()
        mock_service.publish_review_message = AsyncMock()
        return mock_service
    
    @pytest_asyncio.fixture
    async def review_service(self, mock_message_service):
        """Create review service with mocked dependencies."""
        return ReviewService(mock_message_service)
    
    @pytest_asyncio.fixture
    async def mock_session(self):
        """Mock database session."""
        mock = AsyncMock()
        mock.commit = AsyncMock()
        mock.rollback = AsyncMock()
        return mock
    
    @pytest.mark.asyncio
    async def test_get_review_queue_empty(self, review_service, mock_session):
        """Test getting empty review queue."""
        # Mock query execution
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_result.scalars.return_value.all.return_value = []
        
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        result = await review_service.get_review_queue(mock_session)
        
        assert result.total == 0
        assert len(result.items) == 0
        assert result.page == 1
        assert result.page_size == 20
        assert not result.has_next
        assert not result.has_prev
    
    @pytest.mark.asyncio
    async def test_get_review_queue_with_items(self, review_service, mock_session, sample_invoice):
        """Test getting review queue with items."""
        # Mock query execution for count
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1
        
        # Mock query execution for items
        mock_items_result = MagicMock()
        mock_items_result.scalars.return_value.all.return_value = [sample_invoice]
        
        # Set up session to return different results for different queries
        mock_session.execute = AsyncMock(side_effect=[mock_count_result, mock_items_result])
        
        result = await review_service.get_review_queue(mock_session)
        
        assert result.total == 1
        assert len(result.items) == 1
        assert result.items[0].id == sample_invoice.id
        assert result.items[0].vendor_name == sample_invoice.vendor_name
    
    @pytest.mark.asyncio
    async def test_get_invoice_detail_success(self, review_service, mock_session, sample_invoice):
        """Test getting invoice detail successfully."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_invoice
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        result = await review_service.get_invoice_detail(mock_session, sample_invoice.id)
        
        assert result.id == sample_invoice.id
        assert result.vendor_name == sample_invoice.vendor_name
        assert result.matched_status == sample_invoice.matched_status
    
    @pytest.mark.asyncio
    async def test_get_invoice_detail_not_found(self, review_service, mock_session):
        """Test getting invoice detail when invoice not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        invoice_id = uuid.uuid4()
        
        with pytest.raises(InvoiceNotFoundError):
            await review_service.get_invoice_detail(mock_session, invoice_id)
    
    @pytest.mark.asyncio
    async def test_approve_invoice_success(
        self, 
        review_service, 
        mock_session, 
        sample_invoice, 
        approve_request_data,
        mock_message_service
    ):
        """Test approving invoice successfully."""
        # Setup invoice mock
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_invoice
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        request = ApproveRequest(**approve_request_data)
        
        result = await review_service.approve_invoice(mock_session, sample_invoice.id, request)
        
        # Verify invoice was updated
        assert sample_invoice.matched_status == "AUTO_APPROVED"
        assert sample_invoice.reviewed_by == request.reviewed_by
        assert sample_invoice.review_notes == request.review_notes
        
        # Verify response
        assert result.invoice_id == sample_invoice.id
        assert result.action == "approve"
        assert result.reviewed_by == request.reviewed_by
        
        # Verify database commit
        mock_session.commit.assert_called_once()
        
        # Verify message published
        mock_message_service.publish_review_message.assert_called_once_with(
            invoice_id=sample_invoice.id,
            action="approve",
            reviewed_by=request.reviewed_by,
            review_notes=request.review_notes
        )
    
    @pytest.mark.asyncio
    async def test_approve_invoice_not_found(
        self, 
        review_service, 
        mock_session, 
        approve_request_data
    ):
        """Test approving invoice when invoice not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        invoice_id = uuid.uuid4()
        request = ApproveRequest(**approve_request_data)
        
        with pytest.raises(InvoiceNotFoundError):
            await review_service.approve_invoice(mock_session, invoice_id, request)
    
    @pytest.mark.asyncio
    async def test_approve_invoice_already_reviewed(
        self, 
        review_service, 
        mock_session, 
        reviewed_invoice, 
        approve_request_data
    ):
        """Test approving invoice that's already reviewed."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = reviewed_invoice
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        request = ApproveRequest(**approve_request_data)
        
        with pytest.raises(AlreadyReviewedError):
            await review_service.approve_invoice(mock_session, reviewed_invoice.id, request)
    
    @pytest.mark.asyncio
    async def test_reject_invoice_success(
        self, 
        review_service, 
        mock_session, 
        sample_invoice, 
        reject_request_data,
        mock_message_service
    ):
        """Test rejecting invoice successfully."""
        # Setup invoice mock
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_invoice
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        request = RejectRequest(**reject_request_data)
        
        result = await review_service.reject_invoice(mock_session, sample_invoice.id, request)
        
        # Verify invoice was updated
        assert sample_invoice.matched_status == "REJECTED"
        assert sample_invoice.reviewed_by == request.reviewed_by
        assert sample_invoice.review_notes == request.review_notes
        
        # Verify response
        assert result.invoice_id == sample_invoice.id
        assert result.action == "reject"
        assert result.reviewed_by == request.reviewed_by
        
        # Verify database commit
        mock_session.commit.assert_called_once()
        
        # Verify message published
        mock_message_service.publish_review_message.assert_called_once_with(
            invoice_id=sample_invoice.id,
            action="reject",
            reviewed_by=request.reviewed_by,
            review_notes=request.review_notes
        )
    
    @pytest.mark.asyncio
    async def test_reject_invoice_not_found(
        self, 
        review_service, 
        mock_session, 
        reject_request_data
    ):
        """Test rejecting invoice when invoice not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        invoice_id = uuid.uuid4()
        request = RejectRequest(**reject_request_data)
        
        with pytest.raises(InvoiceNotFoundError):
            await review_service.reject_invoice(mock_session, invoice_id, request)
    
    @pytest.mark.asyncio
    async def test_reject_invoice_already_reviewed(
        self, 
        review_service, 
        mock_session, 
        reviewed_invoice, 
        reject_request_data
    ):
        """Test rejecting invoice that's already reviewed."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = reviewed_invoice
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        request = RejectRequest(**reject_request_data)
        
        with pytest.raises(AlreadyReviewedError):
            await review_service.reject_invoice(mock_session, reviewed_invoice.id, request) 