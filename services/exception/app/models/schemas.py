"""Pydantic schemas for API models."""

from datetime import datetime
from typing import Optional, List
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class InvoiceBase(BaseModel):
    """Base invoice schema."""
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    total_amount: Optional[Decimal] = None
    invoice_date: Optional[datetime] = None
    due_date: Optional[datetime] = None


class InvoiceDetail(InvoiceBase):
    """Detailed invoice schema for review."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    status: str
    matched_status: str
    file_path: Optional[str] = None
    file_type: Optional[str] = None
    
    # Extraction data
    extracted_vendor: Optional[str] = None
    extracted_amount: Optional[Decimal] = None
    extracted_invoice_number: Optional[str] = None
    extracted_date: Optional[datetime] = None
    
    # Matching data
    confidence_score: Optional[Decimal] = None
    match_details: Optional[str] = None
    
    # Review data
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None
    
    # Timestamps
    created_at: datetime
    updated_at: datetime


class InvoiceQueueItem(BaseModel):
    """Invoice queue item for list view."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    total_amount: Optional[Decimal] = None
    invoice_date: Optional[datetime] = None
    matched_status: str
    confidence_score: Optional[Decimal] = None
    created_at: datetime


class ReviewQueueResponse(BaseModel):
    """Response for review queue endpoint."""
    items: List[InvoiceQueueItem]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_prev: bool


class ReviewRequest(BaseModel):
    """Request schema for review actions."""
    reviewed_by: str = Field(..., min_length=1, max_length=255)
    review_notes: Optional[str] = Field(None, max_length=2000)


class ApproveRequest(ReviewRequest):
    """Request schema for approval."""
    pass


class RejectRequest(ReviewRequest):
    """Request schema for rejection."""
    review_notes: str = Field(..., min_length=1, max_length=2000)


class ReviewResponse(BaseModel):
    """Response schema for review actions."""
    invoice_id: UUID
    action: str
    reviewed_by: str
    reviewed_at: datetime
    review_notes: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str
    version: str
    timestamp: datetime


class ReadinessResponse(BaseModel):
    """Readiness check response."""
    status: str
    service: str
    version: str
    timestamp: datetime
    checks: dict


class ErrorResponse(BaseModel):
    """Error response schema."""
    error: str
    message: str
    request_id: Optional[str] = None
    timestamp: datetime


class ValidationErrorResponse(BaseModel):
    """Validation error response schema."""
    error: str
    message: str
    details: List[dict]
    request_id: Optional[str] = None
    timestamp: datetime 