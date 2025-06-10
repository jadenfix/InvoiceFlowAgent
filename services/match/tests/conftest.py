"""Pytest configuration and shared fixtures."""

import asyncio
import pytest
import pytest_asyncio
from decimal import Decimal
from typing import AsyncGenerator, Dict, Any
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import event
from testcontainers.postgres import PostgresContainer
from testcontainers.rabbitmq import RabbitMqContainer

from app.models.purchase_order import Base as PurchaseOrderBase, PurchaseOrder
from app.models.invoice import Base as InvoiceBase, Invoice
from app.services.database_service import DatabaseService
from app.services.message_queue import MessageQueueService
from app.services.matching_service import MatchingService


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def postgres_container():
    """Start a PostgreSQL container for testing."""
    with PostgresContainer("postgres:15") as postgres:
        yield postgres


@pytest_asyncio.fixture(scope="function")
async def rabbitmq_container():
    """Start a RabbitMQ container for testing."""
    with RabbitMqContainer("rabbitmq:3-management") as rabbitmq:
        yield rabbitmq


@pytest_asyncio.fixture
async def db_engine(postgres_container):
    """Create test database engine."""
    database_url = postgres_container.get_connection_url().replace(
        "postgresql://", "postgresql+asyncpg://"
    )
    
    engine = create_async_engine(database_url, echo=False)
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(PurchaseOrderBase.metadata.create_all)
        await conn.run_sync(InvoiceBase.metadata.create_all)
    
    yield engine
    
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Create test database session."""
    async_session = async_sessionmaker(db_engine, class_=AsyncSession)
    
    async with async_session() as session:
        yield session


@pytest_asyncio.fixture
async def db_service(db_engine):
    """Create test database service."""
    service = DatabaseService()
    service.engine = db_engine
    service.session_factory = async_sessionmaker(db_engine, class_=AsyncSession)
    service._is_healthy = True
    return service


@pytest_asyncio.fixture
async def mq_service():
    """Create mock message queue service."""
    service = AsyncMock(spec=MessageQueueService)
    service.is_healthy = True
    service.publish_invoice_matched = AsyncMock()
    service.health_check = AsyncMock(return_value=True)
    return service


@pytest_asyncio.fixture
async def matching_service(db_service, mq_service):
    """Create test matching service."""
    service = MatchingService()
    # Replace the global services with test versions
    import app.services.matching_service
    app.services.matching_service.db_service = db_service
    app.services.matching_service.mq_service = mq_service
    return service


@pytest_asyncio.fixture
async def sample_purchase_order(db_session):
    """Create sample purchase order for testing."""
    po = PurchaseOrder(
        po_number="PO123456",
        total_amount=Decimal("1000.00")
    )
    db_session.add(po)
    await db_session.commit()
    await db_session.refresh(po)
    return po


@pytest_asyncio.fixture
async def sample_invoice(db_session):
    """Create sample invoice for testing."""
    invoice = Invoice(
        request_id="test-request-123",
        vendor_name="Test Vendor",
        invoice_number="INV-001",
        total_amount=Decimal("990.00"),
        po_numbers=["PO123456"]
    )
    db_session.add(invoice)
    await db_session.commit()
    await db_session.refresh(invoice)
    return invoice


@pytest.fixture
def invoice_extracted_message():
    """Sample invoice extracted message."""
    return {
        "request_id": "test-request-123",
        "raw_key": "invoices/test.pdf",
        "fields": {
            "total_amount": 990.00,
            "po_numbers": ["PO123456"],
            "vendor_name": "Test Vendor",
            "invoice_number": "INV-001"
        }
    }


@pytest.fixture
def invoice_extracted_message_no_po():
    """Sample invoice extracted message without PO number."""
    return {
        "request_id": "test-request-456",
        "raw_key": "invoices/test2.pdf",
        "fields": {
            "total_amount": 500.00,
            "po_numbers": [],
            "vendor_name": "Test Vendor 2",
            "invoice_number": "INV-002"
        }
    }


@pytest.fixture
def invoice_extracted_message_high_variance():
    """Sample invoice extracted message with high variance."""
    return {
        "request_id": "test-request-789",
        "raw_key": "invoices/test3.pdf",
        "fields": {
            "total_amount": 1500.00,  # 50% higher than PO
            "po_numbers": ["PO123456"],
            "vendor_name": "Test Vendor 3",
            "invoice_number": "INV-003"
        }
    } 