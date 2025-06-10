"""Invoice database models for matching."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import Column, DateTime, Index, JSON, Numeric, String, Text, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from pydantic import BaseModel, validator

Base = declarative_base()


class Invoice(Base):
    """Invoice database model with matching fields."""
    
    __tablename__ = "invoices"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True)
    request_id = Column(String(255), unique=True, nullable=False, index=True)
    
    # Original invoice fields
    vendor_name = Column(Text)
    invoice_number = Column(String(255))
    invoice_date = Column(DateTime(timezone=True))
    due_date = Column(DateTime(timezone=True))
    total_amount = Column(Numeric(12, 2))
    tax_amount = Column(Numeric(12, 2))
    line_items = Column(JSON)
    po_numbers = Column(JSON)  # List of PO numbers from extraction
    
    # Matching fields
    matched_status = Column(
        String(20),
        CheckConstraint("matched_status IN ('AUTO_APPROVED', 'NEEDS_REVIEW')"),
        nullable=False,
        default='NEEDS_REVIEW',
        index=True
    )
    matched_at = Column(DateTime(timezone=True))
    matched_details = Column(JSON)  # PO#, matched_amount, variance_pct
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Indexes
    __table_args__ = (
        Index("idx_request_id", "request_id"),
        Index("idx_matched_status", "matched_status"),
        Index("idx_invoice_number", "invoice_number"),
        Index("idx_vendor_name", "vendor_name"),
    )


class MatchedDetails(BaseModel):
    """Schema for matching details."""
    
    po_number: Optional[str] = None
    po_amount: Optional[Decimal] = None
    invoice_amount: Decimal
    variance_pct: Optional[Decimal] = None


class InvoiceMatchUpdate(BaseModel):
    """Schema for updating invoice match status."""
    
    matched_status: str
    matched_details: MatchedDetails
    
    @validator("matched_status")
    def validate_status(cls, v):
        """Validate match status values."""
        if v not in ["AUTO_APPROVED", "NEEDS_REVIEW"]:
            raise ValueError("Status must be AUTO_APPROVED or NEEDS_REVIEW")
        return v


class InvoiceExtractedMessage(BaseModel):
    """Schema for incoming invoice_extracted messages."""
    
    request_id: str
    raw_key: str
    fields: Dict[str, Any]
    
    @validator("fields")
    def validate_fields(cls, v):
        """Validate required fields are present."""
        if "total_amount" not in v:
            raise ValueError("total_amount is required in fields")
        return v


class InvoiceMatchedMessage(BaseModel):
    """Schema for outgoing invoice_matched messages."""
    
    request_id: str
    status: str
    details: MatchedDetails
    timestamp: datetime = None
    
    def __init__(self, **data):
        if "timestamp" not in data:
            data["timestamp"] = datetime.utcnow()
        super().__init__(**data) 