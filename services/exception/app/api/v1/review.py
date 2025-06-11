"""Review endpoints for exception handling."""

import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query

from ...models.schemas import (
    ReviewQueueResponse,
    InvoiceDetail,
    ApproveRequest,
    RejectRequest,
    ReviewResponse,
    ErrorResponse,
    ValidationErrorResponse,
    InvoiceQueueItem
)
from ...core.config import settings
from ...core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


def get_mock_queue_data():
    """Get mock queue data for development mode."""
    return ReviewQueueResponse(
        items=[
            InvoiceQueueItem(
                id="123e4567-e89b-12d3-a456-426614174000",
                vendor_name="Acme Corp",
                invoice_number="INV-2024-001",
                total_amount=1500.00,
                invoice_date="2024-01-15T00:00:00Z",
                matched_status="NEEDS_REVIEW",
                confidence_score=0.85,
                created_at="2024-01-15T10:30:00Z"
            ),
            InvoiceQueueItem(
                id="456e7890-e89b-12d3-a456-426614174001",
                vendor_name="Tech Solutions Inc",
                invoice_number="INV-2024-002",
                total_amount=2500.00,
                invoice_date="2024-01-14T00:00:00Z",
                matched_status="NEEDS_REVIEW",
                confidence_score=0.65,
                created_at="2024-01-14T14:20:00Z"
            )
        ],
        total=2,
        page=1,
        page_size=20,
        has_next=False,
        has_prev=False
    )


def get_mock_invoice_detail(invoice_id: str):
    """Get mock invoice detail for development mode."""
    return InvoiceDetail(
        id=invoice_id,
        vendor_name="Acme Corp",
        invoice_number="INV-2024-001",
        total_amount=1500.00,
        invoice_date="2024-01-15T00:00:00Z",
        due_date="2024-02-14T00:00:00Z",
        status="PROCESSED",
        matched_status="NEEDS_REVIEW",
        file_path="/invoices/acme/INV-2024-001.pdf",
        file_type="PDF",
        extracted_vendor="Acme Corp",
        extracted_amount=1500.00,
        extracted_invoice_number="INV-2024-001",
        extracted_date="2024-01-15T00:00:00Z",
        confidence_score=0.85,
        match_details="High confidence match based on vendor name and amount",
        created_at="2024-01-15T10:30:00Z",
        updated_at="2024-01-15T10:30:00Z"
    )


@router.get("/queue", response_model=ReviewQueueResponse)
async def get_review_queue(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    vendor_filter: Optional[str] = Query(None, description="Filter by vendor name"),
    date_from: Optional[datetime] = Query(None, description="Filter from date"),
    date_to: Optional[datetime] = Query(None, description="Filter to date"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", regex="^(asc|desc)$", description="Sort order")
):
    """Get paginated list of invoices needing review."""
    
    if settings.environment == "development":
        logger.info("Returning mock queue data in development mode")
        return get_mock_queue_data()
    
    try:
        from ...models.database import get_db_session
        from ...services.review_service import ReviewService
        from ...services.message_service import message_service
        
        review_service = ReviewService(message_service)
        
        async with get_db_session() as session:
            result = await review_service.get_review_queue(
                session=session,
                page=page,
                page_size=page_size,
                vendor_filter=vendor_filter,
                date_from=date_from,
                date_to=date_to,
                sort_by=sort_by,
                sort_order=sort_order
            )
            
            logger.info(
                "Review queue retrieved",
                page=page,
                page_size=page_size,
                total=result.total
            )
            
            return result
        
    except Exception as e:
        logger.error("Failed to get review queue", error=str(e))
        if settings.environment == "development":
            logger.info("Falling back to mock data")
            return get_mock_queue_data()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve review queue"
        )


@router.get("/{invoice_id}", response_model=InvoiceDetail)
async def get_invoice_detail(invoice_id: uuid.UUID):
    """Get detailed invoice information for review."""
    
    if settings.environment == "development":
        logger.info("Returning mock invoice detail in development mode")
        return get_mock_invoice_detail(str(invoice_id))
    
    try:
        from ...models.database import get_db_session
        from ...services.review_service import (
            ReviewService, 
            InvoiceNotFoundError
        )
        from ...services.message_service import message_service
        
        review_service = ReviewService(message_service)
        
        async with get_db_session() as session:
            result = await review_service.get_invoice_detail(
                session=session,
                invoice_id=invoice_id
            )
            
            logger.info("Invoice detail retrieved", invoice_id=str(invoice_id))
            return result
        
    except ImportError as e:
        logger.warning(f"Service dependencies not available: {e}")
        if settings.environment == "development":
            return get_mock_invoice_detail(str(invoice_id))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service dependencies not available"
        )
    except Exception as e:
        logger.error(
            "Failed to get invoice detail",
            invoice_id=str(invoice_id),
            error=str(e)
        )
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Invoice {invoice_id} not found"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve invoice detail"
        )


@router.post("/{invoice_id}/approve", response_model=ReviewResponse)
async def approve_invoice(
    invoice_id: uuid.UUID,
    request: ApproveRequest
):
    """Approve an invoice."""
    
    if settings.environment == "development":
        logger.info(f"Mock approving invoice {invoice_id} by {request.reviewed_by}")
        return ReviewResponse(
            invoice_id=str(invoice_id),
            action="approve",
            reviewed_by=request.reviewed_by,
            reviewed_at=datetime.utcnow(),
            review_notes=request.review_notes
        )
    
    try:
        from ...models.database import get_db_session
        from ...services.review_service import (
            ReviewService,
            InvoiceNotFoundError,
            AlreadyReviewedError
        )
        from ...services.message_service import message_service, PublishError
        
        review_service = ReviewService(message_service)
        
        async with get_db_session() as session:
            result = await review_service.approve_invoice(
                session=session,
                invoice_id=invoice_id,
                request=request
            )
            
            logger.info(
                "Invoice approved",
                invoice_id=str(invoice_id),
                reviewed_by=request.reviewed_by
            )
            
            return result
        
    except ImportError as e:
        logger.warning(f"Service dependencies not available: {e}")
        if settings.environment == "development":
            return ReviewResponse(
                invoice_id=str(invoice_id),
                action="approve",
                reviewed_by=request.reviewed_by,
                reviewed_at=datetime.utcnow(),
                review_notes=request.review_notes
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service dependencies not available"
        )
    except Exception as e:
        logger.error(
            "Failed to approve invoice",
            invoice_id=str(invoice_id),
            error=str(e)
        )
        
        error_msg = str(e).lower()
        if "not found" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Invoice {invoice_id} not found"
            )
        elif "already reviewed" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Invoice {invoice_id} has already been reviewed"
            )
        elif "publish" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to publish approval notification"
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to approve invoice"
        )


@router.post("/{invoice_id}/reject", response_model=ReviewResponse)
async def reject_invoice(
    invoice_id: uuid.UUID,
    request: RejectRequest
):
    """Reject an invoice."""
    
    if settings.environment == "development":
        logger.info(f"Mock rejecting invoice {invoice_id} by {request.reviewed_by}")
        return ReviewResponse(
            invoice_id=str(invoice_id),
            action="reject",
            reviewed_by=request.reviewed_by,
            reviewed_at=datetime.utcnow(),
            review_notes=request.review_notes
        )
    
    try:
        from ...models.database import get_db_session
        from ...services.review_service import (
            ReviewService,
            InvoiceNotFoundError,
            AlreadyReviewedError
        )
        from ...services.message_service import message_service, PublishError
        
        review_service = ReviewService(message_service)
        
        async with get_db_session() as session:
            result = await review_service.reject_invoice(
                session=session,
                invoice_id=invoice_id,
                request=request
            )
            
            logger.info(
                "Invoice rejected",
                invoice_id=str(invoice_id),
                reviewed_by=request.reviewed_by
            )
            
            return result
        
    except ImportError as e:
        logger.warning(f"Service dependencies not available: {e}")
        if settings.environment == "development":
            return ReviewResponse(
                invoice_id=str(invoice_id),
                action="reject",
                reviewed_by=request.reviewed_by,
                reviewed_at=datetime.utcnow(),
                review_notes=request.review_notes
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service dependencies not available"
        )
    except Exception as e:
        logger.error(
            "Failed to reject invoice",
            invoice_id=str(invoice_id),
            error=str(e)
        )
        
        error_msg = str(e).lower()
        if "not found" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Invoice {invoice_id} not found"
            )
        elif "already reviewed" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Invoice {invoice_id} has already been reviewed"
            )
        elif "publish" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to publish rejection notification"
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reject invoice"
        ) 