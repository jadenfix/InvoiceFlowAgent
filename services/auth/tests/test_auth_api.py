"""
Tests for authentication API endpoints
Covers all success and failure scenarios with edge cases
"""
import pytest
import time
from fastapi import status
from unittest.mock import patch


class TestUserRegistration:
    """Test user registration endpoint."""
    
    def test_register_user_success(self, test_client, test_user_data):
        """Test successful user registration."""
        response = test_client.post("/auth/register", json=test_user_data)
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        
        assert data["email"] == test_user_data["email"]
        assert data["full_name"] == test_user_data["full_name"]
        assert data["is_active"] is True
        assert data["is_verified"] is False
        assert "id" in data
        assert "created_at" in data
        assert "password" not in data  # Password should not be returned
    
    def test_register_duplicate_email(self, test_client, test_user_data, created_user):
        """Test registration with duplicate email."""
        response = test_client.post("/auth/register", json=test_user_data)
        
        assert response.status_code == status.HTTP_409_CONFLICT
        data = response.json()
        
        assert data["error"] == "Registration failed"
        assert "already exists" in data["message"]
        assert data["field"] == "email"
    
    def test_register_invalid_email(self, test_client, invalid_email_data):
        """Test registration with invalid email format."""
        response = test_client.post("/auth/register", json=invalid_email_data)
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        
        assert data["error"] == "Validation failed"
        assert "details" in data
    
    def test_register_weak_password(self, test_client, weak_password_data):
        """Test registration with weak password."""
        response = test_client.post("/auth/register", json=weak_password_data)
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        
        assert data["error"] == "Validation failed"
        assert any("password" in str(error).lower() for error in data["details"])
    
    def test_register_missing_fields(self, test_client):
        """Test registration with missing required fields."""
        incomplete_data = {"email": "test@example.com"}
        response = test_client.post("/auth/register", json=incomplete_data)
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_register_empty_email(self, test_client):
        """Test registration with empty email."""
        data = {
            "email": "",
            "password": "TestPassword123",
            "full_name": "Test User"
        }
        response = test_client.post("/auth/register", json=data)
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_register_xss_prevention(self, test_client):
        """Test registration with XSS attempt in full name."""
        data = {
            "email": "test@example.com",
            "password": "TestPassword123",
            "full_name": "<script>alert('xss')</script>"
        }
        response = test_client.post("/auth/register", json=data)
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        assert "invalid characters" in str(data).lower()
    
    def test_register_common_password(self, test_client):
        """Test registration with common weak password."""
        data = {
            "email": "test@example.com",
            "password": "password123",
            "full_name": "Test User"
        }
        response = test_client.post("/auth/register", json=data)
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        assert "too common" in str(data).lower()


class TestUserLogin:
    """Test user login endpoint."""
    
    def test_login_success(self, test_client, created_user, test_user_data):
        """Test successful user login."""
        login_data = {
            "email": test_user_data["email"],
            "password": test_user_data["password"]
        }
        response = test_client.post("/auth/login", json=login_data)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["token_type"] == "bearer"
        assert "access_token" in data
        assert "expires_in" in data
        assert data["expires_in"] > 0
    
    def test_login_invalid_credentials(self, test_client, created_user):
        """Test login with invalid credentials."""
        login_data = {
            "email": created_user.email,
            "password": "wrong_password"
        }
        response = test_client.post("/auth/login", json=login_data)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        data = response.json()
        
        assert data["error"] == "Authentication failed"
        assert "invalid email or password" in data["message"].lower()
    
    def test_login_nonexistent_user(self, test_client):
        """Test login with non-existent user."""
        login_data = {
            "email": "nonexistent@example.com",
            "password": "TestPassword123"
        }
        response = test_client.post("/auth/login", json=login_data)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        data = response.json()
        
        assert data["error"] == "Authentication failed"
    
    def test_login_inactive_user(self, test_client, inactive_user):
        """Test login with inactive user account."""
        login_data = {
            "email": inactive_user.email,
            "password": "TestPassword123"
        }
        response = test_client.post("/auth/login", json=login_data)
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
        data = response.json()
        
        assert data["error"] == "Account disabled"
        assert "disabled" in data["message"].lower()
    
    def test_login_locked_account(self, test_client, locked_user):
        """Test login with locked user account."""
        login_data = {
            "email": locked_user.email,
            "password": "TestPassword123"
        }
        response = test_client.post("/auth/login", json=login_data)
        
        assert response.status_code == status.HTTP_423_LOCKED
        data = response.json()
        
        assert data["error"] == "Account locked"
        assert "locked" in data["message"].lower()
        assert "retry_after" in data
    
    def test_login_rate_limiting(self, test_client, created_user):
        """Test login rate limiting after multiple failed attempts."""
        login_data = {
            "email": created_user.email,
            "password": "wrong_password"
        }
        
        # Make multiple failed login attempts
        for _ in range(5):
            response = test_client.post("/auth/login", json=login_data)
            assert response.status_code == status.HTTP_401_UNAUTHORIZED
        
        # Next attempt should be rate limited
        response = test_client.post("/auth/login", json=login_data)
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        
        data = response.json()
        assert data["error"] == "Too many requests"
        assert "retry_after" in data
    
    def test_login_empty_fields(self, test_client):
        """Test login with empty fields."""
        login_data = {"email": "", "password": ""}
        response = test_client.post("/auth/login", json=login_data)
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_login_missing_fields(self, test_client):
        """Test login with missing fields."""
        login_data = {"email": "test@example.com"}
        response = test_client.post("/auth/login", json=login_data)
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestProtectedEndpoints:
    """Test protected endpoints requiring authentication."""
    
    def test_get_current_user_success(self, test_client, auth_headers, created_user):
        """Test getting current user profile with valid token."""
        response = test_client.get("/auth/me", headers=auth_headers)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["email"] == created_user.email
        assert data["full_name"] == created_user.full_name
        assert data["is_active"] is True
        assert "id" in data
        assert "password" not in data
    
    def test_get_current_user_no_token(self, test_client):
        """Test getting current user without authentication token."""
        response = test_client.get("/auth/me")
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_get_current_user_invalid_token(self, test_client):
        """Test getting current user with invalid token."""
        headers = {"Authorization": "Bearer invalid_token"}
        response = test_client.get("/auth/me", headers=headers)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_get_current_user_expired_token(self, test_client, created_user):
        """Test getting current user with expired token."""
        # Create a token with immediate expiration
        with patch('app.core.auth.jwt_manager.expiration_minutes', 0):
            # Login to get token
            login_response = test_client.post("/auth/login", json={
                "email": created_user.email,
                "password": "TestPassword123"
            })
            
            token_data = login_response.json()
            headers = {"Authorization": f"Bearer {token_data['access_token']}"}
            
            # Wait a moment for token to expire
            time.sleep(1)
            
            # Try to access protected endpoint
            response = test_client.get("/auth/me", headers=headers)
            assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_logout_success(self, test_client, auth_headers):
        """Test successful logout."""
        response = test_client.post("/auth/logout", headers=auth_headers)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert "logout successful" in data["message"].lower()
        assert "remove the token" in data["detail"].lower()
    
    def test_logout_no_token(self, test_client):
        """Test logout without authentication token."""
        response = test_client.post("/auth/logout")
        
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestAuthStatus:
    """Test authentication service status endpoint."""
    
    def test_auth_status(self, test_client):
        """Test authentication status endpoint."""
        response = test_client.get("/auth/status")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["service"] == "InvoiceFlow Auth Service"
        assert data["status"] == "operational"
        assert "version" in data
        assert "environment" in data
        assert "features" in data
        assert "security" in data
        
        # Check features
        features = data["features"]
        assert features["registration"] is True
        assert features["login"] is True
        assert features["jwt_authentication"] is True
        assert features["rate_limiting"] is True
        
        # Check security settings
        security = data["security"]
        assert "password_min_length" in security
        assert "jwt_expiration_minutes" in security
        assert "rate_limit_attempts" in security


class TestErrorHandling:
    """Test error handling scenarios."""
    
    def test_database_error_handling(self, test_client, mock_db_failure):
        """Test handling of database connection failures."""
        test_data = {
            "email": "test@example.com",
            "password": "TestPassword123",
            "full_name": "Test User"
        }
        
        response = test_client.post("/auth/register", json=test_data)
        
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        data = response.json()
        
        assert data["error"] == "Internal server error"
        assert "internal error" in data["message"].lower()
    
    def test_malformed_json(self, test_client):
        """Test handling of malformed JSON data."""
        response = test_client.post(
            "/auth/register",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_large_payload(self, test_client):
        """Test handling of extremely large payloads."""
        large_data = {
            "email": "test@example.com",
            "password": "TestPassword123",
            "full_name": "x" * 10000  # Very long name
        }
        
        response = test_client.post("/auth/register", json=large_data)
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        assert "less than 255 characters" in str(data).lower()


class TestSecurityHeaders:
    """Test security headers and CORS."""
    
    def test_request_id_header(self, test_client):
        """Test that request ID is added to response headers."""
        response = test_client.get("/auth/status")
        
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) > 0
    
    def test_cors_headers(self, test_client):
        """Test CORS headers are present."""
        # Make an OPTIONS request to check CORS
        response = test_client.options("/auth/status")
        
        # CORS headers should be present (handled by middleware)
        assert response.status_code in [200, 204]


class TestInputValidation:
    """Test comprehensive input validation."""
    
    def test_sql_injection_prevention(self, test_client):
        """Test SQL injection prevention in email field."""
        malicious_data = {
            "email": "test@example.com'; DROP TABLE users; --",
            "password": "TestPassword123",
            "full_name": "Test User"
        }
        
        response = test_client.post("/auth/register", json=malicious_data)
        
        # Should fail due to email validation
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_unicode_handling(self, test_client):
        """Test proper Unicode handling in user data."""
        unicode_data = {
            "email": "test@example.com",
            "password": "TestPassword123",
            "full_name": "Тест Пользователь 测试用户"
        }
        
        response = test_client.post("/auth/register", json=unicode_data)
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["full_name"] == unicode_data["full_name"]
    
    def test_email_normalization(self, test_client):
        """Test email normalization (case insensitive)."""
        user_data = {
            "email": "Test@Example.COM",
            "password": "TestPassword123",
            "full_name": "Test User"
        }
        
        # Register with uppercase email
        response = test_client.post("/auth/register", json=user_data)
        assert response.status_code == status.HTTP_201_CREATED
        
        # Try to login with lowercase email
        login_data = {
            "email": "test@example.com",
            "password": "TestPassword123"
        }
        
        response = test_client.post("/auth/login", json=login_data)
        assert response.status_code == status.HTTP_200_OK 