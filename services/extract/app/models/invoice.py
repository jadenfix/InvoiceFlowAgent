"""
Database models for invoice extraction
"""
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
from sqlalchemy import Column, String, DateTime, Integer, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pydantic import BaseModel, Field
import uuid


# SQLAlchemy Base
Base = declarative_base()


class ExtractionStatus(str, Enum):
    """Extraction processing status"""
    PROCESSING = "PROCESSING"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


class IngestionStatus(str, Enum):
    """Ingestion status from ingestion service"""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


# SQLAlchemy Models
class IngestionRaw(Base):
    """Reference to ingestion table (from ingestion service)"""
    __tablename__ = "ingestions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    filename = Column(String, nullable=False)
    s3_key = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False, default=IngestionStatus.PENDING.value)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class InvoiceRaw(Base):
    """Raw invoice extraction results"""
    __tablename__ = "invoices_raw"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    request_id = Column(UUID(as_uuid=True), ForeignKey('ingestions.id'), nullable=False, index=True)
    raw_s3_key = Column(String, nullable=False)  # S3 key for raw OCR JSON
    fields = Column(JSONB, nullable=False)  # Extracted fields from LLM
    status = Column(String, nullable=False, default=ExtractionStatus.PROCESSING.value)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# Pydantic Models
class InvoiceFields(BaseModel):
    """Structured invoice fields extracted by LLM"""
    vendor_name: Optional[str] = Field(None, description="Vendor/supplier name")
    invoice_number: Optional[str] = Field(None, description="Invoice number")
    invoice_date: Optional[str] = Field(None, description="Invoice date (ISO format)")
    due_date: Optional[str] = Field(None, description="Due date (ISO format)")
    total_amount: Optional[float] = Field(None, description="Total invoice amount")
    currency: Optional[str] = Field(default="USD", description="Currency code")
    subtotal: Optional[float] = Field(None, description="Subtotal before tax")
    tax_amount: Optional[float] = Field(None, description="Tax amount")
    po_number: Optional[str] = Field(None, description="Purchase order number")
    line_items: list[Dict[str, Any]] = Field(default_factory=list, description="Invoice line items")


class LineItem(BaseModel):
    """Individual line item on an invoice"""
    description: Optional[str] = Field(None, description="Item description")
    quantity: Optional[float] = Field(None, description="Quantity")
    unit_price: Optional[float] = Field(None, description="Unit price")
    total_price: Optional[float] = Field(None, description="Total price for line")
    sku: Optional[str] = Field(None, description="SKU or item code")


class ExtractionResult(BaseModel):
    """Result of the extraction process"""
    request_id: str = Field(description="Original request ID")
    raw_s3_key: str = Field(description="S3 key for raw OCR data")
    fields: InvoiceFields = Field(description="Extracted fields")
    status: ExtractionStatus = Field(description="Extraction status")
    processing_time: Optional[float] = Field(None, description="Processing time in seconds")
    error_message: Optional[str] = Field(None, description="Error message if failed")


class IngestMessage(BaseModel):
    """Message payload from ingestion queue"""
    request_id: str = Field(description="Request ID")
    filename: str = Field(description="Original filename")
    s3_key: str = Field(description="S3 key for raw PDF")
    timestamp: datetime = Field(description="Upload timestamp")


class ExtractedMessage(BaseModel):
    """Message payload for extracted queue"""
    request_id: str = Field(description="Request ID")
    raw_key: str = Field(description="S3 key for raw OCR data")
    fields: InvoiceFields = Field(description="Extracted fields")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Extraction timestamp")


class OCRResult(BaseModel):
    """OCR processing result"""
    text: str = Field(description="Extracted text")
    confidence: Optional[float] = Field(None, description="OCR confidence score")
    method: str = Field(description="OCR method used (textract/tesseract)")
    blocks: Optional[list[Dict[str, Any]]] = Field(None, description="Textract blocks if available")


class HealthStatus(BaseModel):
    """Health check status"""
    service: str = Field(description="Service status")
    dependencies: Dict[str, str] = Field(description="Dependency statuses")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Check timestamp") 