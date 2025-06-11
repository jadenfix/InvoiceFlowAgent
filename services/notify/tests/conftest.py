"""
Pytest configuration and fixtures for notification service tests
"""
import pytest
import asyncio
import uuid
from unittest.mock import Mock, AsyncMock
from datetime import datetime
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from testcontainers.postgres import PostgresContainer

from app.models.notification import Base, Invoice, Notification, NotificationMethod, NotificationStatus
from app.core.database import get_sync_db
from app.services.notification_service import NotificationService
from app.services.email_service import EmailService
from app.services.sms_service import SMSService


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def postgres_container():
    """PostgreSQL test container"""
    with PostgresContainer("postgres:15") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def test_engine(postgres_container):
    """Create test database engine"""
    engine = create_engine(
        postgres_container.get_connection_url(),
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        echo=False
    )
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    yield engine
    
    # Cleanup
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_db(test_engine):
    """Create test database session"""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def sample_invoice(test_db) -> Invoice:
    """Create a sample invoice for testing"""
    invoice = Invoice(
        id=uuid.uuid4(),
        matched_status="NEEDS_REVIEW",
        vendor_name="Test Vendor",
        total_amount="$1,234.56"
    )
    test_db.add(invoice)
    test_db.commit()
    test_db.refresh(invoice)
    return invoice


@pytest.fixture
def sample_invoices(test_db) -> list[Invoice]:
    """Create multiple sample invoices for testing"""
    invoices = []
    for i in range(3):
        invoice = Invoice(
            id=uuid.uuid4(),
            matched_status="NEEDS_REVIEW",
            vendor_name=f"Test Vendor {i+1}",
            total_amount=f"${(i+1)*100}.00"
        )
        test_db.add(invoice)
        invoices.append(invoice)
    
    test_db.commit()
    for invoice in invoices:
        test_db.refresh(invoice)
    
    return invoices


@pytest.fixture
def mock_email_service():
    """Mock email service"""
    service = Mock(spec=EmailService)
    service.is_valid_email = Mock(return_value=True)
    service.send_notification = AsyncMock(return_value=(True, None))
    service.check_health = Mock(return_value=True)
    return service


@pytest.fixture
def mock_sms_service():
    """Mock SMS service"""
    service = Mock(spec=SMSService)
    service.is_valid_phone_number = Mock(return_value=True)
    service.send_notification = AsyncMock(return_value=(True, None))
    service.check_health = Mock(return_value=True)
    return service


@pytest.fixture
def notification_service(mock_email_service, mock_sms_service):
    """Notification service with mocked dependencies"""
    service = NotificationService()
    service.email_service = mock_email_service
    service.sms_service = mock_sms_service
    return service


@pytest.fixture
def mock_settings(monkeypatch):
    """Mock application settings"""
    monkeypatch.setenv("NOTIFICATION_RECIPIENTS", "test@example.com,+15551234567")
    monkeypatch.setenv("SENDGRID_API_KEY", "test_sendgrid_key")
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "test_twilio_sid")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test_twilio_token")
    monkeypatch.setenv("TWILIO_FROM_NUMBER", "+15559999999")
    
    # Reload settings
    from app.core.config import Settings
    return Settings() 