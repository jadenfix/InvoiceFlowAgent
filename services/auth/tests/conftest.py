"""
Pytest configuration and fixtures for InvoiceFlow Auth Service tests
"""
import os
import pytest
import asyncio
from typing import Generator
from unittest.mock import Mock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import get_db
from app.models.user import Base, User
from app.core.config import settings

# Test database configuration
TEST_DATABASE_URL = "sqlite:///./test_auth.db"


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
def test_db():
    """Create test database and tables."""
    # Create test engine
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    # Create session factory
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    yield TestSessionLocal
    
    # Cleanup
    Base.metadata.drop_all(bind=engine)
    
    # Remove test database file
    if os.path.exists("./test_auth.db"):
        os.remove("./test_auth.db")


@pytest.fixture(scope="function")
def test_client(test_db):
    """Create test client with database override."""
    def override_get_db():
        session = test_db()
        try:
            yield session
        finally:
            session.close()
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as client:
        yield client
    
    # Clear overrides
    app.dependency_overrides.clear()


@pytest.fixture
def test_user_data():
    """Sample user data for testing."""
    return {
        "email": "test@example.com",
        "password": "TestPassword123",
        "full_name": "Test User"
    }


@pytest.fixture
def weak_password_data():
    """User data with weak password for testing validation."""
    return {
        "email": "test@example.com",
        "password": "weak",
        "full_name": "Test User"
    }


@pytest.fixture
def invalid_email_data():
    """User data with invalid email for testing validation."""
    return {
        "email": "invalid-email",
        "password": "TestPassword123",
        "full_name": "Test User"
    }


@pytest.fixture
def created_user(test_db, test_user_data):
    """Create a user in the database for testing."""
    session = test_db()
    
    user = User(
        email=test_user_data["email"],
        full_name=test_user_data["full_name"]
    )
    user.set_password(test_user_data["password"])
    
    session.add(user)
    session.commit()
    session.refresh(user)
    
    yield user
    
    session.close()


@pytest.fixture
def inactive_user(test_db):
    """Create an inactive user for testing."""
    session = test_db()
    
    user = User(
        email="inactive@example.com",
        full_name="Inactive User",
        is_active=False
    )
    user.set_password("TestPassword123")
    
    session.add(user)
    session.commit()
    session.refresh(user)
    
    yield user
    
    session.close()


@pytest.fixture
def locked_user(test_db):
    """Create a locked user for testing."""
    session = test_db()
    
    user = User(
        email="locked@example.com",
        full_name="Locked User",
        failed_login_attempts=settings.rate_limit_attempts
    )
    user.set_password("TestPassword123")
    user.increment_failed_attempts()
    
    session.add(user)
    session.commit()
    session.refresh(user)
    
    yield user
    
    session.close()


@pytest.fixture
def auth_headers(test_client, created_user, test_user_data):
    """Create authentication headers with valid JWT token."""
    # Login to get token
    login_response = test_client.post("/auth/login", json={
        "email": test_user_data["email"],
        "password": test_user_data["password"]
    })
    
    assert login_response.status_code == 200
    token_data = login_response.json()
    
    return {"Authorization": f"Bearer {token_data['access_token']}"}


@pytest.fixture
def mock_db_failure(monkeypatch):
    """Mock database failure for testing error handling."""
    def mock_get_db():
        raise Exception("Database connection failed")
    
    monkeypatch.setattr("app.core.database.get_db", mock_get_db)


@pytest.fixture
def mock_jwt_secret_missing(monkeypatch):
    """Mock missing JWT secret for testing configuration errors."""
    monkeypatch.setenv("JWT_SECRET", "")


# Cleanup fixtures
@pytest.fixture(autouse=True)
def cleanup_rate_limiter():
    """Reset rate limiter state between tests."""
    from app.core.rate_limiter import rate_limiter
    rate_limiter.ip_attempts.clear()
    rate_limiter.email_attempts.clear()
    yield
    rate_limiter.ip_attempts.clear()
    rate_limiter.email_attempts.clear()


# Environment setup
@pytest.fixture(autouse=True)
def setup_test_environment(monkeypatch):
    """Setup test environment variables."""
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-that-is-long-enough-for-testing")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG") 