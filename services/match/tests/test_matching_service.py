"""Unit tests for the matching service."""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from app.services.matching_service import MatchingService
from app.models.invoice import InvoiceExtractedMessage, InvoiceMatchUpdate
from app.models.purchase_order import PurchaseOrder


class TestMatchingService:
    """Test cases for the matching service."""
    
    @pytest.mark.asyncio
    async def test_exact_match_auto_approved(
        self, 
        matching_service, 
        sample_purchase_order,
        invoice_extracted_message
    ):
        """Test exact amount match results in AUTO_APPROVED status."""
        # Modify message to have exact match
        invoice_extracted_message["fields"]["total_amount"] = 1000.00
        
        with patch.object(matching_service, '_update_invoice_match_status') as mock_update, \
             patch.object(matching_service, '_publish_matched_message') as mock_publish:
            
            await matching_service.process_invoice_extracted_message(invoice_extracted_message)
            
            # Verify update was called with AUTO_APPROVED
            mock_update.assert_called_once()
            update_call = mock_update.call_args[0][1]
            assert update_call.matched_status == "AUTO_APPROVED"
            assert update_call.matched_details.po_number == "PO123456"
            assert update_call.matched_details.variance_pct == Decimal("0.0")
            
            # Verify message was published
            mock_publish.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_within_tolerance_auto_approved(
        self, 
        matching_service,
        sample_purchase_order,
        invoice_extracted_message
    ):
        """Test amount within tolerance results in AUTO_APPROVED status."""
        # Invoice amount is 990.00, PO is 1000.00 -> 1% variance (within 2% tolerance)
        
        with patch.object(matching_service, '_update_invoice_match_status') as mock_update, \
             patch.object(matching_service, '_publish_matched_message') as mock_publish:
            
            await matching_service.process_invoice_extracted_message(invoice_extracted_message)
            
            # Verify update was called with AUTO_APPROVED
            mock_update.assert_called_once()
            update_call = mock_update.call_args[0][1]
            assert update_call.matched_status == "AUTO_APPROVED"
            assert update_call.matched_details.po_number == "PO123456"
            assert abs(update_call.matched_details.variance_pct) <= Decimal("0.02")
    
    @pytest.mark.asyncio
    async def test_high_variance_needs_review(
        self,
        matching_service,
        sample_purchase_order,
        invoice_extracted_message_high_variance
    ):
        """Test high variance results in NEEDS_REVIEW status."""
        
        with patch.object(matching_service, '_update_invoice_match_status') as mock_update, \
             patch.object(matching_service, '_publish_matched_message') as mock_publish:
            
            await matching_service.process_invoice_extracted_message(invoice_extracted_message_high_variance)
            
            # Verify update was called with NEEDS_REVIEW
            mock_update.assert_called_once()
            update_call = mock_update.call_args[0][1]
            assert update_call.matched_status == "NEEDS_REVIEW"
            assert update_call.matched_details.po_number == "PO123456"
            assert update_call.matched_details.variance_pct == Decimal("0.5")  # 50% higher
    
    @pytest.mark.asyncio
    async def test_no_po_number_needs_review(
        self,
        matching_service,
        invoice_extracted_message_no_po
    ):
        """Test missing PO number results in NEEDS_REVIEW status."""
        
        with patch.object(matching_service, '_update_invoice_match_status') as mock_update, \
             patch.object(matching_service, '_publish_matched_message') as mock_publish:
            
            await matching_service.process_invoice_extracted_message(invoice_extracted_message_no_po)
            
            # Verify update was called with NEEDS_REVIEW
            mock_update.assert_called_once()
            update_call = mock_update.call_args[0][1]
            assert update_call.matched_status == "NEEDS_REVIEW"
            assert update_call.matched_details.po_number is None
            assert update_call.matched_details.po_amount is None
    
    @pytest.mark.asyncio
    async def test_po_not_found_needs_review(
        self,
        matching_service,
        invoice_extracted_message
    ):
        """Test PO not found results in NEEDS_REVIEW status."""
        # Modify message to reference non-existent PO
        invoice_extracted_message["fields"]["po_numbers"] = ["NONEXISTENT"]
        
        with patch.object(matching_service, '_update_invoice_match_status') as mock_update, \
             patch.object(matching_service, '_publish_matched_message') as mock_publish:
            
            await matching_service.process_invoice_extracted_message(invoice_extracted_message)
            
            # Verify update was called with NEEDS_REVIEW
            mock_update.assert_called_once()
            update_call = mock_update.call_args[0][1]
            assert update_call.matched_status == "NEEDS_REVIEW"
            assert update_call.matched_details.po_number is None
    
    @pytest.mark.asyncio
    async def test_calculate_variance_percentage(self, matching_service):
        """Test variance percentage calculation."""
        # Test exact match
        variance = matching_service._calculate_variance_percentage(
            Decimal("1000.00"), Decimal("1000.00")
        )
        assert variance == Decimal("0.0")
        
        # Test 10% lower
        variance = matching_service._calculate_variance_percentage(
            Decimal("900.00"), Decimal("1000.00")
        )
        assert variance == Decimal("-0.1")
        
        # Test 10% higher
        variance = matching_service._calculate_variance_percentage(
            Decimal("1100.00"), Decimal("1000.00")
        )
        assert variance == Decimal("0.1")
        
        # Test zero PO amount
        variance = matching_service._calculate_variance_percentage(
            Decimal("100.00"), Decimal("0.00")
        )
        assert variance == Decimal("1.0")
    
    @pytest.mark.asyncio
    async def test_database_error_handling(
        self,
        matching_service,
        invoice_extracted_message
    ):
        """Test error handling when database operations fail."""
        
        with patch.object(matching_service, '_update_invoice_match_status') as mock_update, \
             patch.object(matching_service, '_handle_matching_error') as mock_error_handler:
            
            # Make update fail
            mock_update.side_effect = Exception("Database error")
            
            with pytest.raises(Exception):
                await matching_service.process_invoice_extracted_message(invoice_extracted_message)
            
            # Verify error handler was called
            mock_error_handler.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_message_queue_error_handling(
        self,
        matching_service,
        sample_purchase_order,
        invoice_extracted_message
    ):
        """Test error handling when message queue operations fail."""
        
        with patch.object(matching_service, '_update_invoice_match_status') as mock_update, \
             patch.object(matching_service, '_publish_matched_message') as mock_publish, \
             patch.object(matching_service, '_handle_matching_error') as mock_error_handler:
            
            # Make publish fail
            mock_publish.side_effect = Exception("Message queue error")
            
            with pytest.raises(Exception):
                await matching_service.process_invoice_extracted_message(invoice_extracted_message)
            
            # Verify error handler was called
            mock_error_handler.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_invalid_message_format(self, matching_service):
        """Test handling of invalid message format."""
        invalid_message = {
            "request_id": "test",
            "fields": {}  # Missing total_amount
        }
        
        with patch.object(matching_service, '_handle_matching_error') as mock_error_handler:
            with pytest.raises(Exception):
                await matching_service.process_invoice_extracted_message(invalid_message)
            
            mock_error_handler.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_multiple_po_numbers_first_match(
        self,
        matching_service,
        sample_purchase_order,
        invoice_extracted_message
    ):
        """Test behavior when multiple PO numbers are provided and first one matches."""
        # Modify message to have multiple PO numbers
        invoice_extracted_message["fields"]["po_numbers"] = ["PO123456", "NONEXISTENT"]
        
        with patch.object(matching_service, '_update_invoice_match_status') as mock_update, \
             patch.object(matching_service, '_publish_matched_message') as mock_publish:
            
            await matching_service.process_invoice_extracted_message(invoice_extracted_message)
            
            # Should match the first PO
            mock_update.assert_called_once()
            update_call = mock_update.call_args[0][1]
            assert update_call.matched_details.po_number == "PO123456"
    
    @pytest.mark.asyncio
    async def test_error_recovery_needs_review(
        self,
        matching_service
    ):
        """Test error recovery creates NEEDS_REVIEW status."""
        request_id = "test-error-recovery"
        error = Exception("Test error")
        
        with patch.object(matching_service, '_update_invoice_match_status') as mock_update, \
             patch.object(matching_service, '_publish_matched_message') as mock_publish:
            
            # Mock the database service
            import app.services.matching_service
            app.services.matching_service.db_service.update_invoice_match_status = AsyncMock()
            app.services.matching_service.mq_service.publish_invoice_matched = AsyncMock()
            
            await matching_service._handle_matching_error(request_id, error)
            
            # Verify fallback update was attempted
            app.services.matching_service.db_service.update_invoice_match_status.assert_called_once()
            app.services.matching_service.mq_service.publish_invoice_matched.assert_called_once()


class TestMatchingEdgeCases:
    """Test edge cases for matching logic."""
    
    @pytest.mark.asyncio
    async def test_zero_invoice_amount(self, matching_service, sample_purchase_order):
        """Test handling of zero invoice amount."""
        message = {
            "request_id": "test-zero",
            "raw_key": "test.pdf",
            "fields": {
                "total_amount": 0.00,
                "po_numbers": ["PO123456"]
            }
        }
        
        extracted = InvoiceExtractedMessage(**message)
        result = await matching_service._match_invoice(extracted)
        
        assert result.matched_status == "NEEDS_REVIEW"  # Zero amount should need review
    
    @pytest.mark.asyncio
    async def test_negative_invoice_amount(self, matching_service, sample_purchase_order):
        """Test handling of negative invoice amount."""
        message = {
            "request_id": "test-negative",
            "raw_key": "test.pdf", 
            "fields": {
                "total_amount": -100.00,
                "po_numbers": ["PO123456"]
            }
        }
        
        extracted = InvoiceExtractedMessage(**message)
        result = await matching_service._match_invoice(extracted)
        
        assert result.matched_status == "NEEDS_REVIEW"
    
    @pytest.mark.asyncio
    async def test_empty_po_numbers_list(self, matching_service):
        """Test handling of empty PO numbers list."""
        message = {
            "request_id": "test-empty-po",
            "raw_key": "test.pdf",
            "fields": {
                "total_amount": 100.00,
                "po_numbers": []
            }
        }
        
        extracted = InvoiceExtractedMessage(**message)
        result = await matching_service._match_invoice(extracted)
        
        assert result.matched_status == "NEEDS_REVIEW"
        assert result.matched_details.po_number is None
    
    @pytest.mark.asyncio
    async def test_whitespace_only_po_numbers(self, matching_service):
        """Test handling of whitespace-only PO numbers."""
        message = {
            "request_id": "test-whitespace-po",
            "raw_key": "test.pdf",
            "fields": {
                "total_amount": 100.00,
                "po_numbers": ["   ", "\t", "\n"]
            }
        }
        
        extracted = InvoiceExtractedMessage(**message)
        result = await matching_service._match_invoice(extracted)
        
        assert result.matched_status == "NEEDS_REVIEW"
        assert result.matched_details.po_number is None 