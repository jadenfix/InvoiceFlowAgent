"""Core matching service for invoice-PO matching logic."""

from decimal import Decimal
from typing import List, Optional, Dict, Any
import structlog

from ..core.config import settings
from ..core.logging import log_matching_event, log_error, set_request_id
from ..models.invoice import (
    InvoiceExtractedMessage, 
    InvoiceMatchedMessage, 
    InvoiceMatchUpdate,
    MatchedDetails
)
from ..models.purchase_order import PurchaseOrder
from .database_service import db_service
from .message_queue import mq_service

logger = structlog.get_logger(__name__)


class MatchingService:
    """Service for matching invoices with purchase orders."""
    
    def __init__(self):
        """Initialize matching service."""
        self.tolerance = settings.match_amount_tolerance
    
    async def process_invoice_extracted_message(
        self, 
        message_data: Dict[str, Any]
    ) -> None:
        """Process an invoice_extracted message and perform matching."""
        request_id = message_data.get("request_id", "unknown")
        set_request_id(request_id)
        
        try:
            # Validate message format
            extracted_message = InvoiceExtractedMessage(**message_data)
            
            log_matching_event(
                logger,
                "Starting invoice matching process",
                request_id,
                raw_key=extracted_message.raw_key
            )
            
            # Perform matching logic
            match_result = await self._match_invoice(extracted_message)
            
            # Update database with matching results
            await self._update_invoice_match_status(request_id, match_result)
            
            # Publish matched message
            await self._publish_matched_message(request_id, match_result)
            
            log_matching_event(
                logger,
                "Invoice matching process completed",
                request_id,
                status=match_result.matched_status
            )
            
        except Exception as e:
            log_error(
                logger,
                e,
                request_id,
                {"operation": "process_invoice_extracted"}
            )
            
            # For critical errors, mark as NEEDS_REVIEW
            await self._handle_matching_error(request_id, e)
            raise
    
    async def _match_invoice(
        self, 
        extracted_message: InvoiceExtractedMessage
    ) -> InvoiceMatchUpdate:
        """Perform the core matching logic."""
        request_id = extracted_message.request_id
        fields = extracted_message.fields
        
        # Extract required fields
        invoice_amount = Decimal(str(fields.get("total_amount", 0)))
        po_numbers = fields.get("po_numbers", [])
        
        log_matching_event(
            logger,
            "Extracted invoice data for matching",
            request_id,
            invoice_amount=invoice_amount,
            po_numbers=po_numbers
        )
        
        # Check if we have PO numbers to match against
        if not po_numbers or not any(po.strip() for po in po_numbers):
            # No PO numbers found
            return InvoiceMatchUpdate(
                matched_status="NEEDS_REVIEW",
                matched_details=MatchedDetails(
                    invoice_amount=invoice_amount,
                    po_number=None,
                    po_amount=None,
                    variance_pct=None
                )
            )
        
        # Try to match against each PO number
        for po_number in po_numbers:
            if not po_number or not po_number.strip():
                continue
                
            po_number = po_number.strip()
            
            try:
                # Look up purchase order
                purchase_order = await db_service.retry_with_backoff(
                    db_service.find_purchase_order_by_number,
                    po_number,
                    request_id
                )
                
                if not purchase_order:
                    log_matching_event(
                        logger,
                        "Purchase order not found",
                        request_id,
                        po_number=po_number
                    )
                    continue
                
                # Calculate variance
                variance_pct = self._calculate_variance_percentage(
                    invoice_amount, 
                    purchase_order.total_amount
                )
                
                log_matching_event(
                    logger,
                    "Purchase order found, calculating variance",
                    request_id,
                    po_number=po_number,
                    po_amount=purchase_order.total_amount,
                    invoice_amount=invoice_amount,
                    variance_pct=variance_pct,
                    tolerance=self.tolerance
                )
                
                # Check if within tolerance
                if abs(variance_pct) <= self.tolerance:
                    # Auto-approve if within tolerance
                    return InvoiceMatchUpdate(
                        matched_status="AUTO_APPROVED",
                        matched_details=MatchedDetails(
                            po_number=po_number,
                            po_amount=purchase_order.total_amount,
                            invoice_amount=invoice_amount,
                            variance_pct=variance_pct
                        )
                    )
                else:
                    # Variance too high, needs review
                    return InvoiceMatchUpdate(
                        matched_status="NEEDS_REVIEW",
                        matched_details=MatchedDetails(
                            po_number=po_number,
                            po_amount=purchase_order.total_amount,
                            invoice_amount=invoice_amount,
                            variance_pct=variance_pct
                        )
                    )
                    
            except Exception as e:
                log_error(
                    logger,
                    e,
                    request_id,
                    {"operation": "po_lookup", "po_number": po_number}
                )
                # Continue to next PO number if this one fails
                continue
        
        # No valid matches found
        return InvoiceMatchUpdate(
            matched_status="NEEDS_REVIEW",
            matched_details=MatchedDetails(
                invoice_amount=invoice_amount,
                po_number=None,
                po_amount=None,
                variance_pct=None
            )
        )
    
    def _calculate_variance_percentage(
        self, 
        invoice_amount: Decimal, 
        po_amount: Decimal
    ) -> Decimal:
        """Calculate percentage variance between invoice and PO amounts."""
        if po_amount == 0:
            return Decimal("1.0")  # 100% variance
        
        variance = (invoice_amount - po_amount) / po_amount
        return variance
    
    async def _update_invoice_match_status(
        self,
        request_id: str,
        match_result: InvoiceMatchUpdate
    ) -> None:
        """Update the invoice match status in the database."""
        try:
            await db_service.retry_with_backoff(
                db_service.update_invoice_match_status,
                request_id,
                match_result
            )
            
        except Exception as e:
            log_error(
                logger,
                e,
                request_id,
                {"operation": "update_invoice_status"}
            )
            raise
    
    async def _publish_matched_message(
        self,
        request_id: str,
        match_result: InvoiceMatchUpdate
    ) -> None:
        """Publish the invoice_matched message."""
        try:
            matched_message = InvoiceMatchedMessage(
                request_id=request_id,
                status=match_result.matched_status,
                details=match_result.matched_details
            )
            
            await mq_service.retry_with_backoff(
                mq_service.publish_invoice_matched,
                matched_message.dict(),
                request_id
            )
            
        except Exception as e:
            log_error(
                logger,
                e,
                request_id,
                {"operation": "publish_matched_message"}
            )
            raise
    
    async def _handle_matching_error(
        self,
        request_id: str,
        error: Exception
    ) -> None:
        """Handle errors during matching process."""
        try:
            # Create a NEEDS_REVIEW status for failed matches
            error_match_result = InvoiceMatchUpdate(
                matched_status="NEEDS_REVIEW",
                matched_details=MatchedDetails(
                    invoice_amount=Decimal("0.00"),
                    po_number=None,
                    po_amount=None,
                    variance_pct=None
                )
            )
            
            # Try to update database
            await db_service.update_invoice_match_status(
                request_id,
                error_match_result
            )
            
            # Try to publish error message
            await mq_service.publish_invoice_matched(
                {
                    "request_id": request_id,
                    "status": "NEEDS_REVIEW",
                    "details": error_match_result.matched_details.dict(),
                    "error": f"Matching failed: {str(error)}"
                },
                request_id
            )
            
        except Exception as e:
            log_error(
                logger,
                e,
                request_id,
                {"operation": "handle_matching_error", "original_error": str(error)}
            )
            # If we can't even handle the error, let it bubble up


# Global matching service instance
matching_service = MatchingService() 