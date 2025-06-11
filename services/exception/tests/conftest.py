"""Pytest configuration and fixtures for exception service tests."""

import asyncio
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import AsyncGenerator, Generator
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from testcontainers.postgres import PostgresContainer
from testcontainers.rabbitmq import RabbitMqContainer

from app.main import app
from app.models.database import Base, Invoice, get_db_session
from app.services.message_service import MessageService
from app.core.config import settings


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def postgres_container():
    """Start PostgreSQL container for testing."""
    with PostgresContainer("postgres:15") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def rabbitmq_container():
    """Start RabbitMQ container for testing."""
    with RabbitMqContainer("rabbitmq:3-management") as rabbitmq:
        yield rabbitmq


@pytest.fixture(scope="session")
def test_database_url(postgres_container):
    """Get test database URL."""
    return postgres_container.get_connection_url().replace("psycopg2", "asyncpg")


@pytest.fixture(scope="session")
def test_rabbitmq_url(rabbitmq_container):
    """Get test RabbitMQ URL."""
    return rabbitmq_container.get_connection_url()


@pytest_asyncio.fixture(scope="session")
async def test_engine(test_database_url):
    """Create test database engine."""
    engine = create_async_engine(test_database_url, echo=False)
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Cleanup
    await engine.dispose()


@pytest_asyncio.fixture
async def test_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    async_session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def test_message_service(test_rabbitmq_url):
    """Create test message service."""
    # Override settings for test
    original_url = settings.rabbitmq_url
    settings.rabbitmq_url = test_rabbitmq_url
    
    message_service = MessageService()
    await message_service.connect()
    
    yield message_service
    
    await message_service.disconnect()
    settings.rabbitmq_url = original_url


@pytest_asyncio.fixture
async def test_client(test_session, test_message_service):
    """Create test HTTP client."""
    # Override database dependency
    async def override_get_db():
        yield test_session
    
    app.dependency_overrides[get_db_session] = override_get_db
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    
    # Clear overrides
    app.dependency_overrides.clear()


@pytest.fixture
def sample_invoice_data():
    """Sample invoice data for testing."""
    return {
        "vendor_name": "Test Vendor Inc.",
        "invoice_number": "INV-2024-001",
        "total_amount": Decimal("1500.00"),
        "invoice_date": datetime.utcnow() - timedelta(days=5),
        "due_date": datetime.utcnow() + timedelta(days=25),
        "file_path": "/test/invoices/invoice_001.pdf",
        "file_type": "PDF",
        "status": "PROCESSED",
        "matched_status": "NEEDS_REVIEW",
        "extracted_vendor": "Test Vendor Inc.",
        "extracted_amount": Decimal("1500.00"),
        "extracted_invoice_number": "INV-2024-001",
        "extracted_date": datetime.utcnow() - timedelta(days=5),
        "confidence_score": Decimal("0.85"),
        "match_details": "High confidence match based on vendor name and amount",
    }


@pytest_asyncio.fixture
async def sample_invoice(test_session: AsyncSession, sample_invoice_data):
    """Create a sample invoice in the database."""
    invoice = Invoice(**sample_invoice_data)
    test_session.add(invoice)
    await test_session.commit()
    await test_session.refresh(invoice)
    return invoice


@pytest_asyncio.fixture
async def reviewed_invoice(test_session: AsyncSession, sample_invoice_data):
    """Create a reviewed invoice in the database."""
    invoice_data = sample_invoice_data.copy()
    invoice_data.update({
        "matched_status": "AUTO_APPROVED",
        "reviewed_by": "test_reviewer",
        "reviewed_at": datetime.utcnow(),
        "review_notes": "Approved during testing",
    })
    
    invoice = Invoice(**invoice_data)
    test_session.add(invoice)
    await test_session.commit()
    await test_session.refresh(invoice)
    return invoice


@pytest_asyncio.fixture
async def multiple_invoices(test_session: AsyncSession, sample_invoice_data):
    """Create multiple invoices for pagination testing."""
    invoices = []
    
    for i in range(25):  # Create 25 invoices for pagination testing
        invoice_data = sample_invoice_data.copy()
        invoice_data.update({
            "vendor_name": f"Vendor {i+1}",
            "invoice_number": f"INV-2024-{i+1:03d}",
            "total_amount": Decimal(f"{1000 + i * 100}.00"),
            "created_at": datetime.utcnow() - timedelta(hours=i),
        })
        
        invoice = Invoice(**invoice_data)
        test_session.add(invoice)
        invoices.append(invoice)
    
    await test_session.commit()
    
    # Refresh all invoices
    for invoice in invoices:
        await test_session.refresh(invoice)
    
    return invoices


@pytest.fixture
def approve_request_data():
    """Sample approve request data."""
    return {
        "reviewed_by": "test_approver",
        "review_notes": "Invoice approved - all details match PO",
    }


@pytest.fixture
def reject_request_data():
    """Sample reject request data."""
    return {
        "reviewed_by": "test_reviewer",
        "review_notes": "Invoice rejected - amount discrepancy with PO",
    } 