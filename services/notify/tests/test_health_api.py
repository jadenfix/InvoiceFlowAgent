"""
Tests for health API endpoints
"""
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.main import app


@pytest.fixture
def client():
    """Test client for FastAPI app"""
    return TestClient(app)


class TestHealthAPI:
    """Test health API endpoints"""
    
    def test_liveness_probe(self, client):
        """Test liveness probe endpoint"""
        response = client.get("/health/live")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"
        assert "timestamp" in data
    
    @patch('app.api.health.check_async_database_connection')
    @patch('app.api.health.check_broker_connection')
    def test_readiness_probe_healthy(self, mock_broker, mock_db, client):
        """Test readiness probe when all services are healthy"""
        mock_db.return_value = True
        mock_broker.return_value = True
        
        response = client.get("/health/ready")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["database"] == "healthy"
        assert data["broker"] == "healthy"
    
    @patch('app.api.health.check_async_database_connection')
    @patch('app.api.health.check_broker_connection')
    def test_readiness_probe_unhealthy_db(self, mock_broker, mock_db, client):
        """Test readiness probe when database is unhealthy"""
        mock_db.return_value = False
        mock_broker.return_value = True
        
        response = client.get("/health/ready")
        
        assert response.status_code == 503
        data = response.json()
        assert "not_ready" in str(data)
    
    @patch('app.api.health.check_async_database_connection')
    @patch('app.api.health.check_broker_connection')
    def test_readiness_probe_unhealthy_broker(self, mock_broker, mock_db, client):
        """Test readiness probe when broker is unhealthy"""
        mock_db.return_value = True
        mock_broker.return_value = False
        
        response = client.get("/health/ready")
        
        assert response.status_code == 503
        data = response.json()
        assert "not_ready" in str(data)
    
    @patch('app.api.health.check_async_database_connection')
    @patch('app.api.health.check_broker_connection')
    def test_detailed_status_healthy(self, mock_broker, mock_db, client):
        """Test detailed status endpoint when all services are healthy"""
        mock_db.return_value = True
        mock_broker.return_value = True
        
        with patch('app.api.health.NotificationService') as mock_service_class:
            mock_service = mock_service_class.return_value
            mock_service.check_health.return_value = {
                'email_service': True,
                'sms_service': True
            }
            
            response = client.get("/health/status")
            
            assert response.status_code == 200
            data = response.json()
            assert data["service"] == "notification-service"
            assert data["status"] == "healthy"
            assert data["components"]["database"]["status"] == "healthy"
            assert data["components"]["broker"]["status"] == "healthy"
            assert data["components"]["email_service"]["status"] == "healthy"
            assert data["components"]["sms_service"]["status"] == "healthy"
    
    @patch('app.api.health.check_async_database_connection')
    @patch('app.api.health.check_broker_connection')
    def test_detailed_status_degraded(self, mock_broker, mock_db, client):
        """Test detailed status endpoint when some services are unhealthy"""
        mock_db.return_value = False
        mock_broker.return_value = True
        
        with patch('app.api.health.NotificationService') as mock_service_class:
            mock_service = mock_service_class.return_value
            mock_service.check_health.return_value = {
                'email_service': True,
                'sms_service': False
            }
            
            response = client.get("/health/status")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "degraded"
            assert data["components"]["database"]["status"] == "unhealthy"
            assert data["components"]["sms_service"]["status"] == "unhealthy"
    
    @patch('app.api.health.check_async_database_connection')
    def test_health_check_exception(self, mock_db, client):
        """Test health check when exception occurs"""
        mock_db.side_effect = Exception("Database connection failed")
        
        response = client.get("/health/ready")
        
        assert response.status_code == 503
        data = response.json()
        assert "error" in str(data).lower()
    
    @patch('app.api.health.redis.from_url')
    def test_broker_connection_success(self, mock_redis_class):
        """Test broker connection check success"""
        from app.api.health import check_broker_connection
        
        mock_client = mock_redis_class.return_value
        mock_client.ping.return_value = True
        
        result = pytest.asyncio.run(check_broker_connection())
        assert result is True
    
    @patch('app.api.health.redis.from_url')
    def test_broker_connection_failure(self, mock_redis_class):
        """Test broker connection check failure"""
        from app.api.health import check_broker_connection
        
        mock_redis_class.side_effect = Exception("Redis connection failed")
        
        result = pytest.asyncio.run(check_broker_connection())
        assert result is False


class TestHealthAPIEdgeCases:
    """Test edge cases for health API"""
    
    def test_root_endpoint(self, client):
        """Test root endpoint"""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "notification-service"
        assert data["status"] == "running"
    
    def test_service_info_endpoint(self, client):
        """Test service info endpoint"""
        response = client.get("/info")
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "notification-service"
        assert "features" in data
        assert "endpoints" in data
        assert "configuration" in data
    
    @patch('app.api.health.check_async_database_connection')
    @patch('app.api.health.check_broker_connection')
    def test_concurrent_health_checks(self, mock_broker, mock_db, client):
        """Test concurrent health check requests"""
        mock_db.return_value = True
        mock_broker.return_value = True
        
        import threading
        import time
        
        results = []
        
        def make_request():
            response = client.get("/health/ready")
            results.append(response.status_code)
        
        # Make concurrent requests
        threads = [threading.Thread(target=make_request) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        
        # All should succeed
        assert all(status == 200 for status in results)
        assert len(results) == 5 