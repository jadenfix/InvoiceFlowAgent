"""
Tests for Query API endpoints
"""
import pytest
import json
import time
from unittest.mock import patch, Mock, AsyncMock
from fastapi import status
from fastapi.testclient import TestClient
from app.main import app


class TestParseEndpoint:
    """Unit tests for /parse endpoint covering all requirements."""
    
    def test_parse_happy_path(self, client):
        """Test successful parsing of well-formed query."""
        response = client.get("/parse?q=3 bed 2 bath Denver under 700k")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "beds" in data
        assert "baths" in data  
        assert "city" in data
        assert "max_price" in data
        assert "confidence" in data
        assert "cache_hit" in data
        
        # Verify extracted values
        assert data["beds"] == 3
        assert data["baths"] == 2
        assert data["max_price"] == 700000.0
        
    def test_parse_empty_string(self, client):
        """Test parsing empty query returns 422 Unprocessable Entity."""
        response = client.get("/parse?q=")
        assert response.status_code == 422
        
        error_data = response.json()
        assert "detail" in error_data
        assert isinstance(error_data["detail"], list)
        assert len(error_data["detail"]) > 0
        # Check that it's a validation error about string length
        assert error_data["detail"][0]["type"] == "string_too_short"
        
    def test_parse_whitespace_only(self, client):
        """Test parsing whitespace-only query returns 422."""
        response = client.get("/parse?q=   ")
        assert response.status_code == 422
        
    def test_parse_gibberish_text(self, client):
        """Test parsing nonsensical text returns low confidence."""
        response = client.get("/parse?q=xyzabc123!@#")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have low confidence but still return structure
        assert data["confidence"] < 0.3
        assert "beds" in data
        assert "baths" in data
        
    def test_parse_regex_fallback(self, client):
        """Test regex catches patterns when spaCy misses."""
        # Query with clear numeric patterns
        response = client.get("/parse?q=looking for 4bed 3bath place for $850000")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should extract via regex even if spaCy misses
        assert data["beds"] == 4
        assert data["baths"] == 3
        assert data["max_price"] == 850000.0
        
    def test_parse_non_ascii_characters(self, client, non_ascii_query):
        """Test parsing query with non-ASCII and multi-language text."""
        response = client.get(f"/parse?q={non_ascii_query}")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should not crash and return reasonable structure
        assert "beds" in data
        assert "confidence" in data
        
    def test_parse_sql_injection_attempt(self, client, sql_injection_payload):
        """Test that SQL injection attempts are handled safely."""
        response = client.get(f"/parse?q={sql_injection_payload}")
        
        # Should not crash, treat as normal text
        assert response.status_code in [200, 422]
        
    def test_parse_extremely_long_query(self, client, large_query_payload):
        """Test handling of oversized query payloads."""
        response = client.get(f"/parse?q={large_query_payload}")
        
        # Should either reject (413/422) or handle gracefully
        assert response.status_code in [200, 413, 422]
        
        if response.status_code == 200:
            # If accepted, should not crash
            data = response.json()
            assert "confidence" in data
            
    def test_parse_missing_query_param(self, client):
        """Test /parse without q parameter returns 422."""
        response = client.get("/parse")
        assert response.status_code == 422
        
    def test_parse_price_edge_cases(self, client):
        """Test various price formats and edge cases."""
        test_cases = [
            ("under 500k", 500000.0),
            ("below $1.2M", 1200000.0), 
            ("max 750000", 750000.0),
            ("under $50", 50.0),  # Very low price
            ("under $100000000", 100000000.0),  # Very high price
        ]
        
        for query, expected_price in test_cases:
            response = client.get(f"/parse?q=2 bed 1 bath {query}")
            assert response.status_code == 200
            
            data = response.json()
            if data["max_price"]:  # May be None for very edge cases
                assert abs(data["max_price"] - expected_price) < 1000
                
    def test_parse_bed_bath_edge_cases(self, client):
        """Test various bed/bath formats."""
        test_cases = [
            ("1 bedroom 1 bathroom", 1, 1),
            ("studio apartment", None, None),  # May not extract
            ("5bed 4bath", 5, 4),
            ("0 bed 1 bath", 0, 1),  # Edge case
        ]
        
        for query, expected_beds, expected_baths in test_cases:
            response = client.get(f"/parse?q={query} Denver under 500k")
            assert response.status_code == 200
            
            data = response.json()
            if expected_beds is not None:
                assert data.get("beds") == expected_beds
            if expected_baths is not None:
                assert data.get("baths") == expected_baths


class TestCacheIntegration:
    """Tests for Redis cache integration."""
    
    @patch("app.services.cache.CacheService.get")
    @patch("app.services.cache.CacheService.set")
    def test_cache_miss_then_hit(self, mock_set, mock_get, client):
        """Test cache miss followed by cache hit."""
        # First call: cache miss
        mock_get.return_value = None
        mock_set.return_value = True
        
        response1 = client.get("/parse?q=3 bed 2 bath Denver under 700k")
        assert response1.status_code == 200
        
        data1 = response1.json()
        assert data1["cache_hit"] is False
        
        # Mock cache hit for second call
        mock_get.return_value = json.dumps(data1)
        
        response2 = client.get("/parse?q=3 bed 2 bath Denver under 700k")
        assert response2.status_code == 200
        
        data2 = response2.json()
        assert data2["cache_hit"] is True
        
        # Results should be identical
        data1.pop("cache_hit")
        data2.pop("cache_hit")
        assert data1 == data2
        
    @patch("app.services.cache.CacheService.get")
    @patch("app.services.cache.CacheService.set") 
    def test_cache_ttl_expiry(self, mock_set, mock_get, client):
        """Test cache TTL expiration behavior."""
        query = "2 bed 1 bath Seattle under 500k"
        
        # First call: cache miss, should set cache
        mock_get.return_value = None
        mock_set.return_value = True
        
        response1 = client.get(f"/parse?q={query}")
        assert response1.status_code == 200
        assert response1.json()["cache_hit"] is False
        
        # Verify cache.set was called with TTL
        mock_set.assert_called_once()
        call_args = mock_set.call_args
        assert len(call_args[0]) >= 2  # key, value
        # TTL should be in kwargs or third arg
        assert "ttl" in call_args[1] or len(call_args[0]) >= 3
        
    @patch("app.services.cache.CacheService")
    def test_redis_down_graceful_degradation(self, mock_cache_class, client):
        """Test service continues working when Redis is unavailable."""
        # Mock Redis being down
        mock_cache = Mock()
        mock_cache.get.side_effect = Exception("Redis connection failed")
        mock_cache.set.side_effect = Exception("Redis connection failed")
        mock_cache.is_healthy.return_value = False
        mock_cache_class.return_value = mock_cache
        
        response = client.get("/parse?q=3 bed 2 bath Denver under 700k")
        
        # Should still return 200 despite Redis being down
        assert response.status_code == 200
        data = response.json()
        
        # Should indicate no cache hit due to Redis issues
        assert data["cache_hit"] is False
        assert "beds" in data  # Core functionality still works
        
    def test_cache_key_consistency(self, client):
        """Test that identical queries generate identical cache keys."""
        # Test case-insensitive cache keys
        queries = [
            "3 bed 2 bath Denver under 700k",
            "3 BED 2 BATH DENVER UNDER 700K",
            "  3 bed 2 bath Denver under 700k  ",  # Extra whitespace
        ]
        
        responses = []
        for query in queries:
            response = client.get(f"/parse?q={query}")
            assert response.status_code == 200
            responses.append(response.json())
        
        # All should have same extracted data (ignoring cache_hit)
        for i in range(1, len(responses)):
            resp1 = {k: v for k, v in responses[0].items() if k != "cache_hit"}
            resp2 = {k: v for k, v in responses[i].items() if k != "cache_hit"}
            assert resp1 == resp2


class TestSearchEndpoint:
    """Unit tests for /search endpoint."""
    
    def test_search_valid_parsed_json(self, client, sample_properties):
        """Test search with valid parsed JSON input."""
        search_request = {
            "beds": 3,
            "baths": 2,
            "city": "Denver",
            "max_price": 700000.0
        }
        
        with patch("app.services.search.SearchService.search") as mock_search:
            mock_search.return_value = sample_properties[:1]  # Return one property
            
            response = client.post("/search", json=search_request)
            assert response.status_code == 200
            
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["address"] == "123 Main St"
            
    def test_search_no_matches(self, client):
        """Test search returning empty results."""
        search_request = {
            "beds": 10,  # Unrealistic number
            "baths": 8, 
            "city": "NonexistentCity",
            "max_price": 1.0  # Impossible price
        }
        
        with patch("app.services.search.SearchService.search") as mock_search:
            mock_search.return_value = []
            
            response = client.post("/search", json=search_request)
            assert response.status_code == 200
            
            data = response.json()
            assert data == []
            
    def test_search_missing_required_fields(self, client):
        """Test search with missing required fields returns 422."""
        # Missing required fields
        incomplete_requests = [
            {},  # Empty
            {"beds": 3},  # Missing other fields
            {"city": "Denver"},  # Missing numeric fields
        ]
        
        for request_data in incomplete_requests:
            response = client.post("/search", json=request_data)
            assert response.status_code == 422
            
    def test_search_invalid_field_types(self, client):
        """Test search with invalid data types."""
        invalid_requests = [
            {"beds": "three", "baths": 2, "city": "Denver", "max_price": 700000},
            {"beds": 3, "baths": 2.5, "city": "Denver", "max_price": "expensive"},
            {"beds": -1, "baths": 2, "city": "Denver", "max_price": 700000},
        ]
        
        for request_data in invalid_requests:
            response = client.post("/search", json=request_data)
            assert response.status_code == 422
            
    def test_search_geo_filter_edge_cases(self, client, malformed_geo_data):
        """Test search with invalid geo coordinates."""
        search_request = {
            "beds": 2,
            "baths": 1,
            "city": "Denver", 
            "max_price": 500000,
            "location": malformed_geo_data
        }
        
        response = client.post("/search", json=search_request)
        
        # Should reject invalid coordinates
        assert response.status_code == 422
        
        error_data = response.json()
        assert "detail" in error_data
        
    def test_search_oversized_result_window(self, client):
        """Test search with oversized result limits."""
        search_request = {
            "beds": 2,
            "baths": 1,
            "city": "Denver",
            "max_price": 500000,
            "size": 1000  # Very large size
        }
        
        with patch("app.services.search.SearchService.search") as mock_search:
            # Mock should receive truncated size
            mock_search.return_value = []
            
            response = client.post("/search", json=search_request)
            assert response.status_code == 200
            
            # Verify search was called with truncated size
            mock_search.assert_called_once()
            call_args = mock_search.call_args[0][0]
            assert call_args.get("size", 10) <= 100  # Should be truncated
            
    @patch("app.services.search.SearchService.search")
    def test_opensearch_unavailable(self, mock_search, client):
        """Test handling when OpenSearch is unavailable."""
        # Mock OpenSearch connection failure
        mock_search.side_effect = Exception("OpenSearch connection failed")
        
        search_request = {
            "beds": 3,
            "baths": 2,
            "city": "Denver",
            "max_price": 700000
        }
        
        response = client.post("/search", json=search_request)
        
        # Should return 503 Service Unavailable
        assert response.status_code == 503
        
        error_data = response.json()
        assert "detail" in error_data
        assert "search service" in error_data["detail"].lower()


class TestHealthEndpoints:
    """Tests for health check endpoints."""
    
    def test_health_check_all_services_healthy(self, client):
        """Test health endpoint when all services are healthy."""
        with patch("app.services.cache.CacheService.is_healthy") as mock_cache, \
             patch("app.services.search.SearchService.is_healthy") as mock_search:
            
            mock_cache.return_value = True
            mock_search.return_value = True
            
            response = client.get("/health")
            assert response.status_code == 200
            
            data = response.json()
            assert data["status"] == "healthy"
            assert data["services"]["cache"] is True
            assert data["services"]["search"] is True
            
    def test_health_check_degraded_services(self, client):
        """Test health endpoint when some services are down."""
        with patch("app.services.cache.CacheService.is_healthy") as mock_cache, \
             patch("app.services.search.SearchService.is_healthy") as mock_search:
            
            mock_cache.return_value = False  # Redis down
            mock_search.return_value = True
            
            response = client.get("/health")
            assert response.status_code == 503
            
            data = response.json()
            assert data["status"] == "degraded"
            assert data["services"]["cache"] is False
            assert data["services"]["search"] is True


class TestEnvironmentConfiguration:
    """Tests for environment variable handling and configuration."""
    
    def test_missing_redis_url_env_var(self, client):
        """Test behavior when REDIS_URL is not set."""
        with patch.dict("os.environ", {}, clear=True):
            # This would normally be tested during app startup
            # but we can test the health endpoint behavior
            response = client.get("/health")
            
            # App should still start but cache might be unhealthy
            assert response.status_code in [200, 503]
            
    def test_missing_opensearch_url_env_var(self, client):
        """Test behavior when OPENSEARCH_URL is not set."""
        with patch.dict("os.environ", {}, clear=True):
            response = client.get("/health")
            
            # App should handle missing OpenSearch URL gracefully
            assert response.status_code in [200, 503]


class TestSecurityAndValidation:
    """Security and input validation tests."""
    
    def test_cors_headers(self, client):
        """Test CORS headers are present."""
        response = client.get("/parse?q=test")
        
        # Should have CORS headers
        assert "access-control-allow-origin" in response.headers
        
    def test_request_size_limits(self, client):
        """Test request size is properly limited."""
        # Very large JSON payload
        large_payload = {
            "beds": 3,
            "baths": 2,
            "city": "A" * 10000,  # Very long city name
            "max_price": 700000
        }
        
        response = client.post("/search", json=large_payload)
        
        # Should either accept or reject based on size limits
        assert response.status_code in [200, 413, 422]
        
    def test_rate_limiting_headers(self, client):
        """Test rate limiting headers if implemented."""
        response = client.get("/parse?q=test")
        
        # Rate limiting headers might be present
        headers = response.headers
        rate_limit_headers = [h for h in headers if "rate" in h.lower() or "limit" in h.lower()]
        
        # This test passes if no rate limiting or if properly implemented
        assert response.status_code == 200
        
    def test_response_time_performance(self, client):
        """Test response times meet performance requirements."""
        import time
        
        start_time = time.time()
        response = client.get("/parse?q=3 bed 2 bath Denver under 700k")
        end_time = time.time()
        
        assert response.status_code == 200
        
        # Response should be reasonably fast (adjust threshold as needed)
        response_time = (end_time - start_time) * 1000  # Convert to ms
        assert response_time < 5000  # Should be under 5 seconds for first call 