"""Database models and session management."""

from datetime import datetime
from typing import Optional, AsyncGenerator
from sqlalchemy import create_engine, Column, String, DateTime, Numeric, Text, Integer
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID
import uuid

from ..core.config import settings

# Base model class
Base = declarative_base()

# Async engine and session
async_engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=10,
    max_overflow=20,
)

async_session_factory = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Invoice(Base):
    """Invoice model with review fields."""
    
    __tablename__ = "invoices"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Core invoice data
    vendor_name = Column(String(255))
    invoice_number = Column(String(100))
    total_amount = Column(Numeric(10, 2))
    invoice_date = Column(DateTime)
    due_date = Column(DateTime)
    
    # File information
    file_path = Column(String(500))
    file_type = Column(String(50))
    
    # Processing status
    status = Column(String(50), default="PENDING")
    matched_status = Column(String(50), default="PENDING")
    
    # Extraction data (JSON fields would be better, but keeping simple)
    extracted_vendor = Column(String(255))
    extracted_amount = Column(Numeric(10, 2))
    extracted_invoice_number = Column(String(100))
    extracted_date = Column(DateTime)
    
    # Matching data
    confidence_score = Column(Numeric(5, 4))
    match_details = Column(Text)
    
    # Review fields (NEW)
    reviewed_by = Column(String(255))
    reviewed_at = Column(DateTime)
    review_notes = Column(Text)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database tables."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Close database connections."""
    await async_engine.dispose() 