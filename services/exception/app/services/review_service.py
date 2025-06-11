"""Review service for managing invoice exception reviews."""

import uuid
from datetime import datetime
from typing import List, Optional, Tuple
from decimal import Decimal
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import NoResultFound

from ..models.database import Invoice
from ..models.schemas import (
    InvoiceQueueItem, 
    InvoiceDetail, 
    ReviewQueueResponse,
    ApproveRequest,
    RejectRequest,
    ReviewResponse
)
from ..core.logging import get_logger
from .message_service import MessageService

logger = get_logger(__name__)


class ReviewServiceError(Exception):
    """Base exception for review service."""
    pass


class InvoiceNotFoundError(ReviewServiceError):
    """Invoice not found."""
    pass


class AlreadyReviewedError(ReviewServiceError):
    """Invoice already reviewed."""
    pass


class ReviewService:
    """Service for managing invoice reviews."""
    
    def __init__(self, message_service: MessageService):
        self.message_service = message_service
    
    async def get_review_queue(
        self,
        session: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        vendor_filter: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc"
    ) -> ReviewQueueResponse:
        """Get paginated list of invoices needing review."""
        
        # Base query for invoices needing review
        query = select(Invoice).where(
            and_(
                Invoice.matched_status == "NEEDS_REVIEW",
                Invoice.reviewed_by.is_(None)
            )
        )
        
        # Apply filters
        if vendor_filter:
            query = query.where(
                or_(
                    Invoice.vendor_name.ilike(f"%{vendor_filter}%"),
                    Invoice.extracted_vendor.ilike(f"%{vendor_filter}%")
                )
            )
        
        if date_from:
            query = query.where(Invoice.created_at >= date_from)
            
        if date_to:
            query = query.where(Invoice.created_at <= date_to)
        
        # Count total items
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0
        
        # Apply sorting
        if sort_order.lower() == "desc":
            query = query.order_by(getattr(Invoice, sort_by).desc())
        else:
            query = query.order_by(getattr(Invoice, sort_by).asc())
        
        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)
        
        # Execute query
        result = await session.execute(query)
        invoices = result.scalars().all()
        
        # Convert to queue items
        items = [
            InvoiceQueueItem(
                id=invoice.id,
                vendor_name=invoice.vendor_name or invoice.extracted_vendor,
                invoice_number=invoice.invoice_number or invoice.extracted_invoice_number,
                total_amount=invoice.total_amount or invoice.extracted_amount,
                invoice_date=invoice.invoice_date or invoice.extracted_date,
                matched_status=invoice.matched_status,
                confidence_score=invoice.confidence_score,
                created_at=invoice.created_at
            )
            for invoice in invoices
        ]
        
        # Calculate pagination info
        has_next = offset + len(items) < total
        has_prev = page > 1
        
        logger.info(
            "Retrieved review queue",
            total=total,
            page=page,
            page_size=page_size,
            items_count=len(items)
        )
        
        return ReviewQueueResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            has_next=has_next,
            has_prev=has_prev
        )
    
    async def get_invoice_detail(
        self,
        session: AsyncSession,
        invoice_id: uuid.UUID
    ) -> InvoiceDetail:
        """Get detailed invoice information for review."""
        
        query = select(Invoice).where(Invoice.id == invoice_id)
        result = await session.execute(query)
        invoice = result.scalar_one_or_none()
        
        if not invoice:
            logger.warning("Invoice not found", invoice_id=str(invoice_id))
            raise InvoiceNotFoundError(f"Invoice {invoice_id} not found")
        
        logger.info("Retrieved invoice detail", invoice_id=str(invoice_id))
        
        return InvoiceDetail.model_validate(invoice)
    
    async def approve_invoice(
        self,
        session: AsyncSession,
        invoice_id: uuid.UUID,
        request: ApproveRequest
    ) -> ReviewResponse:
        """Approve an invoice."""
        
        # Get invoice
        query = select(Invoice).where(Invoice.id == invoice_id)
        result = await session.execute(query)
        invoice = result.scalar_one_or_none()
        
        if not invoice:
            logger.warning("Invoice not found for approval", invoice_id=str(invoice_id))
            raise InvoiceNotFoundError(f"Invoice {invoice_id} not found")
        
        # Check if already reviewed
        if invoice.reviewed_by is not None:
            logger.warning(
                "Invoice already reviewed",
                invoice_id=str(invoice_id),
                reviewed_by=invoice.reviewed_by
            )
            raise AlreadyReviewedError(f"Invoice {invoice_id} already reviewed")
        
        # Update invoice
        reviewed_at = datetime.utcnow()
        invoice.matched_status = "AUTO_APPROVED"
        invoice.reviewed_by = request.reviewed_by
        invoice.reviewed_at = reviewed_at
        invoice.review_notes = request.review_notes
        invoice.updated_at = reviewed_at
        
        try:
            # Commit to database
            await session.commit()
            
            # Publish message
            await self.message_service.publish_review_message(
                invoice_id=invoice_id,
                action="approve",
                reviewed_by=request.reviewed_by,
                review_notes=request.review_notes
            )
            
            logger.info(
                "Invoice approved",
                invoice_id=str(invoice_id),
                reviewed_by=request.reviewed_by
            )
            
            return ReviewResponse(
                invoice_id=invoice_id,
                action="approve",
                reviewed_by=request.reviewed_by,
                reviewed_at=reviewed_at,
                review_notes=request.review_notes
            )
            
        except Exception as e:
            logger.error(
                "Failed to approve invoice",
                invoice_id=str(invoice_id),
                error=str(e)
            )
            await session.rollback()
            raise
    
    async def reject_invoice(
        self,
        session: AsyncSession,
        invoice_id: uuid.UUID,
        request: RejectRequest
    ) -> ReviewResponse:
        """Reject an invoice."""
        
        # Get invoice
        query = select(Invoice).where(Invoice.id == invoice_id)
        result = await session.execute(query)
        invoice = result.scalar_one_or_none()
        
        if not invoice:
            logger.warning("Invoice not found for rejection", invoice_id=str(invoice_id))
            raise InvoiceNotFoundError(f"Invoice {invoice_id} not found")
        
        # Check if already reviewed
        if invoice.reviewed_by is not None:
            logger.warning(
                "Invoice already reviewed",
                invoice_id=str(invoice_id),
                reviewed_by=invoice.reviewed_by
            )
            raise AlreadyReviewedError(f"Invoice {invoice_id} already reviewed")
        
        # Update invoice
        reviewed_at = datetime.utcnow()
        invoice.matched_status = "REJECTED"
        invoice.reviewed_by = request.reviewed_by
        invoice.reviewed_at = reviewed_at
        invoice.review_notes = request.review_notes
        invoice.updated_at = reviewed_at
        
        try:
            # Commit to database
            await session.commit()
            
            # Publish message
            await self.message_service.publish_review_message(
                invoice_id=invoice_id,
                action="reject",
                reviewed_by=request.reviewed_by,
                review_notes=request.review_notes
            )
            
            logger.info(
                "Invoice rejected",
                invoice_id=str(invoice_id),
                reviewed_by=request.reviewed_by
            )
            
            return ReviewResponse(
                invoice_id=invoice_id,
                action="reject",
                reviewed_by=request.reviewed_by,
                reviewed_at=reviewed_at,
                review_notes=request.review_notes
            )
            
        except Exception as e:
            logger.error(
                "Failed to reject invoice",
                invoice_id=str(invoice_id),
                error=str(e)
            )
            await session.rollback()
            raise 