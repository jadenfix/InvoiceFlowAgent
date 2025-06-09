"""
Tests for health check endpoints
Tests liveness, readiness, and detailed health checks
"""
import pytest
from fastapi import status
from unittest.mock import patch, AsyncMock


class TestHealthEndpoints:
    """Test health check endpoints."""
    
    def test_liveness_probe_success(self, test_client):
        """Test successful liveness probe."""
        response = test_client.get("/healthz")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["status"] == "alive"
        assert data["service"] == "invoiceflow-auth"
        assert "uptime_seconds" in data
        assert "timestamp" in data
        assert data["uptime_seconds"] >= 0
    
    def test_readiness_probe_success(self, test_client):
        """Test successful readiness probe with healthy dependencies."""
        response = test_client.get("/readyz")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["status"] == "ready"
        assert data["service"] == "invoiceflow-auth"
        assert "uptime_seconds" in data
        assert "checks" in data
        assert "database" in data["checks"]
        assert "configuration" in data["checks"]
    
    @patch('app.core.database.check_db_health')
    async def test_readiness_probe_database_unhealthy(self, mock_db_health, test_client):
        """Test readiness probe with unhealthy database."""
        # Mock unhealthy database
        mock_db_health.return_value = {
            "status": "unhealthy",
            "database": "disconnected",
            "details": {"error": "Connection failed"}
        }
        
        response = test_client.get("/readyz")
        
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        
        assert data["status"] == "not_ready"
        assert data["service"] == "invoiceflow-auth"
        assert data["checks"]["database"]["status"] == "unhealthy"
    
    def test_detailed_health_check_success(self, test_client):
        """Test detailed health check with all systems healthy."""
        response = test_client.get("/health")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["status"] == "healthy"
        assert data["service"] == "invoiceflow-auth"
        assert data["version"] == "1.0.0"
        assert "environment" in data
        assert "uptime_seconds" in data
        assert "check_duration_ms" in data
        assert "timestamp" in data
        
        # Check detailed sections
        assert "checks" in data
        assert "metrics" in data
        
        checks = data["checks"]
        assert "database" in checks
        assert "configuration" in checks
        assert "features" in checks
        
        # Verify configuration check
        config = checks["configuration"]
        assert config["status"] == "healthy"
        assert "jwt_configured" in config
        assert "database_configured" in config
        
        # Verify features
        features = checks["features"]
        assert features["authentication"] is True
        assert features["rate_limiting"] is True
        assert features["logging"] is True
    
    @patch('app.core.database.check_db_health')
    async def test_detailed_health_check_database_unhealthy(self, mock_db_health, test_client):
        """Test detailed health check with unhealthy database."""
        # Mock unhealthy database
        mock_db_health.return_value = {
            "status": "unhealthy",
            "database": "disconnected",
            "details": {"error": "Connection timeout"}
        }
        
        response = test_client.get("/health")
        
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        
        assert data["status"] == "unhealthy"
        assert data["checks"]["database"]["status"] == "unhealthy"
        assert "Connection timeout" in str(data["checks"]["database"]["details"])
    
    @patch('app.api.health.check_db_health')
    async def test_health_check_exception_handling(self, mock_db_health, test_client):
        """Test health check when database health check raises exception."""
        # Mock exception during health check
        mock_db_health.side_effect = Exception("Database check failed")
        
        response = test_client.get("/health")
        
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        
        assert data["status"] == "unhealthy"
        assert "Database check failed" in data["error"]
    
    def test_liveness_probe_no_dependencies(self, test_client):
        """Test that liveness probe doesn't depend on external services."""
        # Even if database is down, liveness should still work
        with patch('app.core.database.check_db_health', side_effect=Exception("DB down")):
            response = test_client.get("/healthz")
            
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "alive"
    
    def test_health_check_performance(self, test_client):
        """Test that health checks complete within reasonable time."""
        import time
        
        start_time = time.time()
        response = test_client.get("/health")
        duration = time.time() - start_time
        
        assert response.status_code in [200, 503]  # Either healthy or unhealthy is fine
        assert duration < 5.0  # Should complete within 5 seconds
        
        data = response.json()
        assert "check_duration_ms" in data
        assert data["check_duration_ms"] < 5000  # Less than 5 seconds in milliseconds
    
    def test_readiness_probe_configuration_check(self, test_client):
        """Test readiness probe includes configuration validation."""
        response = test_client.get("/readyz")
        
        data = response.json()
        config_check = data["checks"]["configuration"]
        
        assert config_check["status"] == "healthy"
        assert "environment" in config_check
    
    def test_health_metrics_included(self, test_client):
        """Test that health endpoint includes useful metrics."""
        response = test_client.get("/health")
        
        data = response.json()
        metrics = data["metrics"]
        
        assert "uptime_seconds" in metrics
        assert "check_duration_ms" in metrics
        assert metrics["uptime_seconds"] >= 0
        assert metrics["check_duration_ms"] > 0


class TestHealthErrorHandling:
    """Test error handling in health checks."""
    
    @patch('app.api.health.time.time')
    def test_liveness_probe_exception(self, mock_time, test_client):
        """Test liveness probe when time calculation fails."""
        mock_time.side_effect = Exception("Time error")
        
        response = test_client.get("/healthz")
        
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        
        assert data["status"] == "unhealthy"
        assert "not responding properly" in data["error"]
    
    @patch('app.api.health.check_db_health')
    async def test_readiness_probe_db_exception(self, mock_db_health, test_client):
        """Test readiness probe when database health check raises exception."""
        mock_db_health.side_effect = Exception("DB health check failed")
        
        response = test_client.get("/readyz")
        
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        
        assert data["status"] == "not_ready"
        assert "DB health check failed" in data["error"]


class TestHealthIntegration:
    """Integration tests for health checks."""
    
    def test_all_health_endpoints_accessible(self, test_client):
        """Test that all health endpoints are accessible."""
        endpoints = ["/healthz", "/readyz", "/health"]
        
        for endpoint in endpoints:
            response = test_client.get(endpoint)
            assert response.status_code in [200, 503]  # Either healthy or unhealthy
            assert response.headers["content-type"] == "application/json"
    
    def test_health_check_consistency(self, test_client):
        """Test that health checks return consistent information."""
        # Get all health endpoints
        liveness = test_client.get("/healthz").json()
        readiness = test_client.get("/readyz").json()
        detailed = test_client.get("/health").json()
        
        # Check service name consistency
        assert liveness["service"] == "invoiceflow-auth"
        assert readiness["service"] == "invoiceflow-auth"
        assert detailed["service"] == "invoiceflow-auth"
        
        # Check uptime consistency (should be similar, allowing for small differences)
        uptime_diff = abs(detailed["uptime_seconds"] - readiness["uptime_seconds"])
        assert uptime_diff <= 1  # Should be within 1 second
    
    def test_health_endpoints_respond_quickly(self, test_client):
        """Test that all health endpoints respond quickly."""
        import time
        
        endpoints = ["/healthz", "/readyz", "/health"]
        
        for endpoint in endpoints:
            start_time = time.time()
            response = test_client.get(endpoint)
            duration = time.time() - start_time
            
            assert duration < 2.0  # Each endpoint should respond within 2 seconds
            assert response.status_code in [200, 503] 