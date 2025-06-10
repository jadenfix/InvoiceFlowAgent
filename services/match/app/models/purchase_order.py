"""Purchase order database models."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from pydantic import BaseModel, validator

Base = declarative_base()


class PurchaseOrder(Base):
    """Purchase order database model."""
    
    __tablename__ = "purchase_orders"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)
    po_number = Column(Text, unique=True, nullable=False, index=True)
    order_date = Column(DateTime(timezone=True), nullable=True)
    total_amount = Column(Numeric(12, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Indexes
    __table_args__ = (
        Index("idx_po_number", "po_number"),
        Index("idx_total_amount", "total_amount"),
    )


class PurchaseOrderCreate(BaseModel):
    """Schema for creating a purchase order."""
    
    po_number: str
    order_date: Optional[datetime] = None
    total_amount: Decimal
    
    @validator("po_number")
    def validate_po_number(cls, v):
        """Validate PO number format."""
        if not v or not v.strip():
            raise ValueError("PO number cannot be empty")
        if len(v.strip()) > 100:
            raise ValueError("PO number too long")
        return v.strip().upper()
    
    @validator("total_amount")
    def validate_total_amount(cls, v):
        """Validate total amount is positive."""
        if v <= 0:
            raise ValueError("Total amount must be positive")
        return v


class PurchaseOrderResponse(BaseModel):
    """Schema for purchase order responses."""
    
    id: UUID
    po_number: str
    order_date: Optional[datetime]
    total_amount: Decimal
    created_at: datetime
    
    class Config:
        from_attributes = True 