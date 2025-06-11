"""
Database models for notification service
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Column, String, DateTime, Text, UUID, CheckConstraint, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from pydantic import BaseModel, Field

Base = declarative_base()


class NotificationMethod(str, Enum):
    """Notification delivery methods"""
    EMAIL = "email"
    SMS = "sms"


class NotificationStatus(str, Enum):
    """Notification delivery status"""
    SENT = "SENT"
    FAILED = "FAILED"


class Notification(Base):
    """Notification database model"""
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id = Column(UUID(as_uuid=True), nullable=False)
    method = Column(String, nullable=False)
    recipient = Column(String, nullable=False)
    sent_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    status = Column(String, nullable=False)
    error_message = Column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("method IN ('email','sms')", name='check_method'),
        CheckConstraint("status IN ('SENT','FAILED')", name='check_status'),
        UniqueConstraint('invoice_id', 'method', 'recipient', name='unique_notification')
    )


class Invoice(Base):
    """Invoice model for querying invoices that need review"""
    __tablename__ = "invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    matched_status = Column(String, nullable=False)
    vendor_name = Column(String, nullable=True)
    total_amount = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# Pydantic models for API responses
class NotificationResponse(BaseModel):
    """Response model for notification creation"""
    id: uuid.UUID
    invoice_id: uuid.UUID
    method: NotificationMethod
    recipient: str
    status: NotificationStatus
    sent_at: datetime
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class NotificationCreate(BaseModel):
    """Request model for creating notifications"""
    invoice_id: uuid.UUID
    method: NotificationMethod
    recipient: str = Field(..., description="Email address or phone number")


class HealthResponse(BaseModel):
    """Health check response model"""
    status: str
    database: str
    broker: str
    timestamp: datetime 