import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, String, DateTime, Numeric, JSON, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base

class PostedStatusEnum(str, Enum):
    PENDING = "PENDING"
    POSTED = "POSTED"
    FAILED = "FAILED"


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_name: Mapped[str] = mapped_column(String(255))  # simplified fields
    invoice_number: Mapped[str] = mapped_column(String(255))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    posted_status: Mapped[str] = mapped_column(String(10), default="PENDING")
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    posted_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow) 