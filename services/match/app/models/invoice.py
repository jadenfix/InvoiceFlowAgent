"""Invoice database models for matching."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, validator
from sqlalchemy import JSON, CheckConstraint, DateTime, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class Invoice(Base):
    """Invoice database model with matching fields."""

    __tablename__ = "invoices"

    id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)
    request_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    # Original invoice fields
    vendor_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    invoice_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    line_items: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    po_numbers: Mapped[list[str] | None] = mapped_column(JSON)  # List of PO numbers from extraction

    # Matching fields
    matched_status: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint("matched_status IN ('AUTO_APPROVED', 'NEEDS_REVIEW')"),
        nullable=False,
        default="NEEDS_REVIEW",
        index=True,
    )
    matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    matched_details: Mapped[dict[str, Any] | None] = mapped_column(
        JSON
    )  # PO#, matched_amount, variance_pct

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

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
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    def __init__(self, **data):
        if "timestamp" not in data:
            data["timestamp"] = datetime.utcnow()
        super().__init__(**data)
