"""
Database service for extraction operations
"""
import uuid
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from ..core.config import settings, get_database_url
from ..core.logging import get_logger, log_processing_step, log_error
from ..models.invoice import IngestionRaw, InvoiceRaw, ExtractionStatus, InvoiceFields


logger = get_logger(__name__)


class DatabaseService:
    """Database service for extraction operations"""
    
    def __init__(self):
        self.engine = None
        self.SessionLocal = None
        self._setup_database()
    
    def _setup_database(self):
        """Setup database connection"""
        try:
            database_url = get_database_url()
            
            self.engine = create_async_engine(
                database_url,
                pool_size=settings.DB_POOL_SIZE,
                max_overflow=settings.DB_MAX_OVERFLOW,
                echo=settings.DB_ECHO,
                pool_pre_ping=True,
                pool_recycle=3600,
            )
            
            self.SessionLocal = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            logger.info("Database service initialized")
            
        except Exception as e:
            log_error(e, {"operation": "database_setup"})
            self.engine = None
            self.SessionLocal = None
    
    async def get_session(self) -> AsyncSession:
        """Get database session"""
        if not self.SessionLocal:
            raise RuntimeError("Database not initialized")
        return self.SessionLocal()
    
    async def update_ingestion_status(self, request_id: str, status: str) -> bool:
        """
        Update ingestion status
        
        Args:
            request_id: Request ID
            status: New status
            
        Returns:
            True if successful, False otherwise
        """
        log_processing_step("update_ingestion_status", request_id, status=status)
        
        try:
            async with await self.get_session() as session:
                stmt = (
                    update(IngestionRaw)
                    .where(IngestionRaw.id == uuid.UUID(request_id))
                    .values(
                        status=status,
                        updated_at=datetime.utcnow()
                    )
                )
                
                result = await session.execute(stmt)
                await session.commit()
                
                if result.rowcount > 0:
                    logger.info(f"Updated ingestion status to {status} for request {request_id}")
                    return True
                else:
                    logger.warning(f"No ingestion record found for request {request_id}")
                    return False
                    
        except SQLAlchemyError as e:
            log_error(e, {"operation": "update_ingestion_status", "request_id": request_id})
            return False
        except Exception as e:
            log_error(e, {"operation": "update_ingestion_status", "request_id": request_id})
            return False
    
    async def create_invoice_raw(
        self, 
        request_id: str, 
        raw_s3_key: str, 
        fields: InvoiceFields,
        status: ExtractionStatus = ExtractionStatus.PROCESSING
    ) -> Optional[str]:
        """
        Create invoice raw record
        
        Args:
            request_id: Original request ID
            raw_s3_key: S3 key for raw OCR data
            fields: Extracted fields
            status: Extraction status
            
        Returns:
            Invoice raw ID if successful, None otherwise
        """
        log_processing_step("create_invoice_raw", request_id, status=status.value)
        
        try:
            async with await self.get_session() as session:
                invoice_raw = InvoiceRaw(
                    request_id=uuid.UUID(request_id),
                    raw_s3_key=raw_s3_key,
                    fields=fields.model_dump(),
                    status=status.value
                )
                
                session.add(invoice_raw)
                await session.commit()
                await session.refresh(invoice_raw)
                
                logger.info(f"Created invoice raw record {invoice_raw.id} for request {request_id}")
                return str(invoice_raw.id)
                
        except SQLAlchemyError as e:
            log_error(e, {"operation": "create_invoice_raw", "request_id": request_id})
            return None
        except Exception as e:
            log_error(e, {"operation": "create_invoice_raw", "request_id": request_id})
            return None
    
    async def update_invoice_raw_status(
        self, 
        request_id: str, 
        status: ExtractionStatus,
        fields: Optional[InvoiceFields] = None
    ) -> bool:
        """
        Update invoice raw status and fields
        
        Args:
            request_id: Request ID
            status: New status
            fields: Updated fields (optional)
            
        Returns:
            True if successful, False otherwise
        """
        log_processing_step("update_invoice_raw_status", request_id, status=status.value)
        
        try:
            async with await self.get_session() as session:
                update_values = {
                    'status': status.value,
                    'updated_at': datetime.utcnow()
                }
                
                if fields:
                    update_values['fields'] = fields.model_dump()
                
                stmt = (
                    update(InvoiceRaw)
                    .where(InvoiceRaw.request_id == uuid.UUID(request_id))
                    .values(**update_values)
                )
                
                result = await session.execute(stmt)
                await session.commit()
                
                if result.rowcount > 0:
                    logger.info(f"Updated invoice raw status to {status.value} for request {request_id}")
                    return True
                else:
                    logger.warning(f"No invoice raw record found for request {request_id}")
                    return False
                    
        except SQLAlchemyError as e:
            log_error(e, {"operation": "update_invoice_raw_status", "request_id": request_id})
            return False
        except Exception as e:
            log_error(e, {"operation": "update_invoice_raw_status", "request_id": request_id})
            return False
    
    async def get_invoice_raw(self, request_id: str) -> Optional[InvoiceRaw]:
        """
        Get invoice raw record by request ID
        
        Args:
            request_id: Request ID
            
        Returns:
            InvoiceRaw record or None if not found
        """
        try:
            async with await self.get_session() as session:
                stmt = select(InvoiceRaw).where(InvoiceRaw.request_id == uuid.UUID(request_id))
                result = await session.execute(stmt)
                return result.scalar_one_or_none()
                
        except SQLAlchemyError as e:
            log_error(e, {"operation": "get_invoice_raw", "request_id": request_id})
            return None
        except Exception as e:
            log_error(e, {"operation": "get_invoice_raw", "request_id": request_id})
            return None
    
    async def get_ingestion(self, request_id: str) -> Optional[IngestionRaw]:
        """
        Get ingestion record by request ID
        
        Args:
            request_id: Request ID
            
        Returns:
            IngestionRaw record or None if not found
        """
        try:
            async with await self.get_session() as session:
                stmt = select(IngestionRaw).where(IngestionRaw.id == uuid.UUID(request_id))
                result = await session.execute(stmt)
                return result.scalar_one_or_none()
                
        except SQLAlchemyError as e:
            log_error(e, {"operation": "get_ingestion", "request_id": request_id})
            return None
        except Exception as e:
            log_error(e, {"operation": "get_ingestion", "request_id": request_id})
            return None
    
    async def health_check(self) -> bool:
        """Health check for database service"""
        if not self.engine:
            return False
        
        try:
            async with await self.get_session() as session:
                # Simple query to test connectivity
                result = await session.execute(select(1))
                result.scalar_one()
                return True
                
        except Exception as e:
            log_error(e, {"operation": "database_health_check"})
            return False
    
    async def close(self):
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()


# Create service instance
database_service = DatabaseService() 