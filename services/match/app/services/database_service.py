"""Database service for managing connections and operations."""

import asyncio
from decimal import Decimal
from typing import List, Optional
from contextlib import asynccontextmanager

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
import structlog

from ..core.config import settings
from ..core.logging import log_error, log_matching_event
from ..models.purchase_order import PurchaseOrder
from ..models.invoice import Invoice, InvoiceMatchUpdate

logger = structlog.get_logger(__name__)


class DatabaseService:
    """Service for database operations."""
    
    def __init__(self):
        """Initialize database service."""
        self.engine = None
        self.session_factory = None
        self._is_healthy = False
    
    async def initialize(self) -> None:
        """Initialize database connection."""
        try:
            self.engine = create_async_engine(
                settings.database_url,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                echo=settings.log_level == "DEBUG"
            )
            
            self.session_factory = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            # Test connection
            await self.health_check()
            
            logger.info("Database service initialized", service="match-service")
            
        except Exception as e:
            log_error(logger, e, "system", {"operation": "database_init"})
            raise
    
    async def close(self) -> None:
        """Close database connections."""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database connections closed", service="match-service")
    
    async def health_check(self) -> bool:
        """Check database health."""
        try:
            async with self.session_factory() as session:
                result = await session.execute(select(1))
                result.scalar()
                self._is_healthy = True
                return True
        except Exception as e:
            self._is_healthy = False
            log_error(logger, e, "system", {"operation": "health_check"})
            return False
    
    @property
    def is_healthy(self) -> bool:
        """Get current health status."""
        return self._is_healthy
    
    @asynccontextmanager
    async def get_session(self):
        """Get database session with automatic cleanup."""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    
    async def find_purchase_order_by_number(
        self, 
        po_number: str,
        request_id: str = "system"
    ) -> Optional[PurchaseOrder]:
        """Find purchase order by PO number."""
        try:
            async with self.get_session() as session:
                result = await session.execute(
                    select(PurchaseOrder).where(
                        PurchaseOrder.po_number == po_number.upper()
                    )
                )
                po = result.scalar_one_or_none()
                
                log_matching_event(
                    logger, 
                    "Purchase order lookup",
                    request_id,
                    po_number=po_number,
                    found=po is not None
                )
                
                return po
                
        except SQLAlchemyError as e:
            log_error(
                logger, 
                e, 
                request_id, 
                {"operation": "find_purchase_order", "po_number": po_number}
            )
            raise
    
    async def update_invoice_match_status(
        self,
        request_id: str,
        match_update: InvoiceMatchUpdate
    ) -> bool:
        """Update invoice match status and details."""
        try:
            async with self.get_session() as session:
                result = await session.execute(
                    update(Invoice)
                    .where(Invoice.request_id == request_id)
                    .values(
                        matched_status=match_update.matched_status,
                        matched_at=func.now(),
                        matched_details=match_update.matched_details.dict()
                    )
                )
                
                updated = result.rowcount > 0
                
                log_matching_event(
                    logger,
                    "Invoice match status updated",
                    request_id,
                    status=match_update.matched_status,
                    updated=updated
                )
                
                return updated
                
        except SQLAlchemyError as e:
            log_error(
                logger,
                e,
                request_id,
                {"operation": "update_invoice_match"}
            )
            raise
    
    async def get_invoice_by_request_id(
        self,
        request_id: str
    ) -> Optional[Invoice]:
        """Get invoice by request ID."""
        try:
            async with self.get_session() as session:
                result = await session.execute(
                    select(Invoice).where(Invoice.request_id == request_id)
                )
                return result.scalar_one_or_none()
                
        except SQLAlchemyError as e:
            log_error(
                logger,
                e,
                request_id,
                {"operation": "get_invoice"}
            )
            raise
    
    async def retry_with_backoff(
        self,
        operation,
        *args,
        max_retries: int = 3,
        base_delay: float = 1.0,
        **kwargs
    ):
        """Retry database operation with exponential backoff."""
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                return await operation(*args, **kwargs)
            except SQLAlchemyError as e:
                last_exception = e
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        "Database operation failed, retrying",
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        delay=delay,
                        error=str(e)
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "Database operation failed after all retries",
                        attempts=max_retries + 1,
                        error=str(e)
                    )
                    raise last_exception


# Global database service instance
db_service = DatabaseService() 