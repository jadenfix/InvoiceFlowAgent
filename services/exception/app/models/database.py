"""Database models and session management."""

from datetime import datetime
from decimal import Decimal
from typing import AsyncGenerator
from sqlalchemy import String, DateTime, Numeric, Text, Uuid
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from contextlib import asynccontextmanager
import uuid

from ..core.config import settings


# Base model class
class Base(DeclarativeBase):
    pass


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
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Core invoice data
    vendor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    invoice_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # File information
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Processing status
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=True)
    matched_status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=True)

    # Extraction data (JSON fields would be better, but keeping simple)
    extracted_vendor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extracted_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    extracted_invoice_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    extracted_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Matching data
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    match_details: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Review fields (NEW)
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True
    )


@asynccontextmanager
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
