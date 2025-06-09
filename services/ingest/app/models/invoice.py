"""
Data models for invoice ingestion and processing
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from decimal import Decimal

from pydantic import BaseModel, Field, validator
from sqlalchemy import Column, Integer, String, DateTime, Text, Numeric, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID
import uuid


# SQLAlchemy Base
Base = declarative_base()


class InvoiceStatus(str, Enum):
    """Invoice processing status enumeration"""
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    UPLOAD_FAILED = "upload_failed"
    VALIDATION_FAILED = "validation_failed"
    INVALID_SCHEMA = "invalid_schema"


class InvoiceSource(str, Enum):
    """Invoice source enumeration"""
    EMAIL = "email"
    HTTP = "http"
    MANUAL = "manual"
    API = "api"


# Pydantic Models for API and Processing
class InvoiceLineItem(BaseModel):
    """Individual line item in an invoice"""
    description: str = Field(..., min_length=1, max_length=500)
    quantity: Decimal = Field(..., gt=0)
    unit_price: Decimal = Field(..., ge=0)
    total_price: Decimal = Field(..., ge=0)
    tax_amount: Optional[Decimal] = Field(default=None, ge=0)
    
    @validator('total_price')
    def validate_total_price(cls, v, values):
        """Validate that total price matches quantity * unit_price"""
        if 'quantity' in values and 'unit_price' in values:
            expected = values['quantity'] * values['unit_price']
            if abs(v - expected) > Decimal('0.01'):  # Allow for rounding
                raise ValueError(f"Total price {v} doesn't match quantity * unit_price {expected}")
        return v


class InvoiceData(BaseModel):
    """Core invoice data structure"""
    invoice_id: str = Field(..., min_length=1, max_length=100)
    vendor: str = Field(..., min_length=1, max_length=200)
    date: datetime = Field(...)
    amount: Decimal = Field(..., gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    line_items: List[InvoiceLineItem] = Field(default_factory=list)
    
    # Optional fields
    vendor_address: Optional[str] = Field(default=None, max_length=500)
    customer_name: Optional[str] = Field(default=None, max_length=200)
    customer_address: Optional[str] = Field(default=None, max_length=500)
    payment_terms: Optional[str] = Field(default=None, max_length=100)
    due_date: Optional[datetime] = Field(default=None)
    tax_amount: Optional[Decimal] = Field(default=None, ge=0)
    discount_amount: Optional[Decimal] = Field(default=None, ge=0)
    
    @validator('currency')
    def validate_currency(cls, v):
        """Validate currency code"""
        valid_currencies = ['USD', 'EUR', 'GBP', 'CAD', 'AUD', 'JPY']
        if v.upper() not in valid_currencies:
            raise ValueError(f"Invalid currency code: {v}")
        return v.upper()
    
    @validator('amount')
    def validate_amount_matches_line_items(cls, v, values):
        """Validate that total amount matches line items sum"""
        if 'line_items' in values and values['line_items']:
            line_items_total = sum(item.total_price for item in values['line_items'])
            if abs(v - line_items_total) > Decimal('0.01'):
                raise ValueError(f"Amount {v} doesn't match line items total {line_items_total}")
        return v


class ProcessingResult(BaseModel):
    """Result of processing an invoice file"""
    success: bool
    invoice_data: Optional[InvoiceData] = None
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    processing_time: float = Field(..., ge=0)
    file_size: int = Field(..., ge=0)
    ocr_used: bool = False


class IngestRequest(BaseModel):
    """Request to ingest an invoice"""
    source: InvoiceSource
    source_identifier: str = Field(..., min_length=1, max_length=200)
    file_url: Optional[str] = Field(default=None)
    file_content: Optional[bytes] = Field(default=None)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IngestResponse(BaseModel):
    """Response from invoice ingestion"""
    request_id: str
    status: InvoiceStatus
    s3_key: Optional[str] = None
    processing_result: Optional[ProcessingResult] = None
    message: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


# SQLAlchemy Models for Database Storage
class InvoiceRaw(Base):
    """Raw invoice data table"""
    __tablename__ = "invoices_raw"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = Column(String(50), nullable=False)
    source_identifier = Column(String(200), nullable=False)
    s3_key = Column(String(500), nullable=True)
    filename = Column(String(255), nullable=True)
    payload_json = Column(JSON, nullable=True)
    status = Column(String(50), nullable=False, default=InvoiceStatus.PENDING.value)
    
    # Processing metadata
    processing_attempts = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    file_size = Column(Integer, nullable=True)
    content_type = Column(String(100), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime, nullable=True)
    
    # Extracted data (normalized from payload_json)
    invoice_id = Column(String(100), nullable=True)
    vendor = Column(String(200), nullable=True)
    invoice_date = Column(DateTime, nullable=True)
    amount = Column(Numeric(10, 2), nullable=True)
    currency = Column(String(3), nullable=True)


# OpenSearch Document Schema
class InvoiceDocument(BaseModel):
    """OpenSearch document structure for invoices"""
    id: str
    invoice_id: str
    vendor: str
    date: datetime
    amount: Decimal
    currency: str = "USD"
    status: InvoiceStatus
    source: InvoiceSource
    
    # Search-optimized fields
    vendor_normalized: str  # Lowercase, trimmed vendor name
    amount_range: str  # e.g., "1000-5000", "5000-10000"
    date_year: int
    date_month: int
    date_quarter: int
    
    # Full text search
    line_items_text: str = ""  # Concatenated line item descriptions
    
    # Metadata
    created_at: datetime
    updated_at: datetime
    
    @classmethod
    def from_invoice_data(cls, raw_id: str, invoice_data: InvoiceData, 
                         status: InvoiceStatus, source: InvoiceSource) -> 'InvoiceDocument':
        """Create OpenSearch document from invoice data"""
        
        # Determine amount range
        amount_ranges = [
            (0, 100, "0-100"),
            (100, 500, "100-500"),
            (500, 1000, "500-1000"),
            (1000, 5000, "1000-5000"),
            (5000, 10000, "5000-10000"),
            (10000, float('inf'), "10000+")
        ]
        
        amount_range = "unknown"
        for min_amt, max_amt, range_str in amount_ranges:
            if min_amt <= invoice_data.amount < max_amt:
                amount_range = range_str
                break
        
        # Concatenate line items for full text search
        line_items_text = " ".join([item.description for item in invoice_data.line_items])
        
        return cls(
            id=raw_id,
            invoice_id=invoice_data.invoice_id,
            vendor=invoice_data.vendor,
            date=invoice_data.date,
            amount=invoice_data.amount,
            currency=invoice_data.currency,
            status=status,
            source=source,
            vendor_normalized=invoice_data.vendor.lower().strip(),
            amount_range=amount_range,
            date_year=invoice_data.date.year,
            date_month=invoice_data.date.month,
            date_quarter=(invoice_data.date.month - 1) // 3 + 1,
            line_items_text=line_items_text,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )


# SQLAlchemy Models for Database Storage
class IngestionRaw(Base):
    """Raw ingestion table for tracking uploaded files"""
    __tablename__ = "ingestions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    filename = Column(String, nullable=False)
    s3_key = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False, default=InvoiceStatus.PENDING.value)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class IngestionStatus(BaseModel):
    """Model for ingestion status response"""
    request_id: str
    filename: str
    status: InvoiceStatus
    created_at: datetime
    updated_at: datetime
    s3_key: Optional[str] = None


class IngestionStats(BaseModel):
    """Model for ingestion statistics"""
    pending: int
    processing: int
    failed: int
    completed: int
    total: int


class MessagePayload(BaseModel):
    """Message payload for RabbitMQ"""
    request_id: str
    filename: str
    s3_key: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class OpenSearchInvoiceDocument(BaseModel):
    """OpenSearch document structure"""
    id: str
    filename: str
    status: str
    source: str
    created_at: datetime
    updated_at: datetime
    
    # Extracted data for search
    invoice_id: Optional[str] = None
    vendor: Optional[str] = None
    vendor_normalized: Optional[str] = None
    amount: Optional[float] = None
    currency: str = "USD"
    invoice_date: Optional[datetime] = None
    
    # Search fields
    full_text: Optional[str] = None
    tags: List[str] = []
    
    # Processing metadata
    processing_attempts: int = 0
    last_error: Optional[str] = None 