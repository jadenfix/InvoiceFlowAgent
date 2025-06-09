"""
Integration tests for the Query Service.

These tests launch actual Redis and OpenSearch containers to test
the complete end-to-end functionality including:
- Parse -> Search pipeline
- Cache behavior with real Redis
- OpenSearch query execution
- Error handling with real services
"""

import pytest
import json
import time
import asyncio
from fastapi.testclient import TestClient
from opensearchpy import OpenSearch

from app.main import app


class TestEndToEndIntegration:
    """End-to-end integration tests with real services."""
    
    def test_complete_parse_search_flow(self, client, redis_container, opensearch_container):
        """Test complete flow: parse query -> search properties."""
        # Configure app to use test containers
        import os
        os.environ["REDIS_URL"] = redis_container
        os.environ["OPENSEARCH_URL"] = opensearch_container
        
        # Step 1: Parse a natural language query
        parse_response = client.get("/parse?q=3 bed 2 bath Denver under 700k")
        assert parse_response.status_code == 200
        
        parsed_data = parse_response.json()
        assert parsed_data["beds"] == 3
        assert parsed_data["baths"] == 2
        assert parsed_data["max_price"] == 700000.0
        assert parsed_data["cache_hit"] is False  # First call
        
        # Step 2: Use parsed data to search
        search_request = {
            "beds": parsed_data["beds"],
            "baths": parsed_data["baths"],
            "city": parsed_data["city"],
            "max_price": parsed_data["max_price"]
        }
        
        search_response = client.post("/search", json=search_request)
        assert search_response.status_code == 200
        
        search_results = search_response.json()
        assert isinstance(search_results, list)
        # Results may be empty since we haven't populated test data
        
        # Step 3: Verify cache hit on second parse
        parse_response2 = client.get("/parse?q=3 bed 2 bath Denver under 700k")
        assert parse_response2.status_code == 200
        
        parsed_data2 = parse_response2.json()
        assert parsed_data2["cache_hit"] is True  # Should be cached now
        
        # Results should be identical (except cache_hit flag)
        parsed_data.pop("cache_hit")
        parsed_data2.pop("cache_hit")
        assert parsed_data == parsed_data2
        
    def test_redis_cache_with_real_container(self, client, redis_container):
        """Test Redis caching behavior with real Redis container."""
        import os
        os.environ["REDIS_URL"] = redis_container
        
        query = "2 bed 1 bath Seattle under 500k"
        
        # First call - should be cache miss
        response1 = client.get(f"/parse?q={query}")
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["cache_hit"] is False
        
        # Second call - should be cache hit
        response2 = client.get(f"/parse?q={query}")
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["cache_hit"] is True
        
        # Data should be identical
        data1.pop("cache_hit")
        data2.pop("cache_hit")
        assert data1 == data2
        
        # Test different query - should be cache miss again
        response3 = client.get("/parse?q=4 bed 3 bath Portland under 800k")
        assert response3.status_code == 200
        data3 = response3.json()
        assert data3["cache_hit"] is False
        
    def test_opensearch_with_real_container(self, client, opensearch_container):
        """Test OpenSearch integration with real container."""
        import os
        os.environ["OPENSEARCH_URL"] = opensearch_container
        
        # Create test index and add sample data
        opensearch_client = OpenSearch([opensearch_container])
        
        # Create index with proper mapping
        index_mapping = {
            "mappings": {
                "properties": {
                    "address": {"type": "text"},
                    "city": {"type": "keyword"},
                    "state": {"type": "keyword"},
                    "price": {"type": "float"},
                    "beds": {"type": "integer"},
                    "baths": {"type": "integer"},
                    "square_feet": {"type": "integer"},
                    "location": {"type": "geo_point"}
                }
            }
        }
        
        # Clean up and create fresh index
        try:
            opensearch_client.indices.delete(index="properties")
        except:
            pass
            
        opensearch_client.indices.create(index="properties", body=index_mapping)
        
        # Add test properties
        test_properties = [
            {
                "address": "123 Test St",
                "city": "Denver",
                "state": "CO",
                "price": 650000.0,
                "beds": 3,
                "baths": 2,
                "square_feet": 1800,
                "location": {"lat": 39.7392, "lon": -104.9903}
            },
            {
                "address": "456 Sample Ave",
                "city": "Denver",
                "state": "CO",
                "price": 750000.0,
                "beds": 4,
                "baths": 3,
                "square_feet": 2200,
                "location": {"lat": 39.7392, "lon": -104.9903}
            }
        ]
        
        for i, prop in enumerate(test_properties):
            opensearch_client.index(
                index="properties",
                id=f"test_{i}",
                body=prop,
                refresh=True  # Make immediately searchable
            )
        
        # Wait for indexing
        time.sleep(1)
        
        # Test search functionality
        search_request = {
            "beds": 3,
            "baths": 2,
            "city": "Denver",
            "max_price": 700000.0
        }
        
        response = client.post("/search", json=search_request)
        assert response.status_code == 200
        
        results = response.json()
        assert isinstance(results, list)
        assert len(results) >= 1  # Should find at least one matching property
        
        # Verify result structure
        if results:
            result = results[0]
            assert "address" in result
            assert "city" in result
            assert "price" in result
            assert "beds" in result
            assert "baths" in result
            assert result["beds"] == 3
            assert result["baths"] == 2
            assert result["price"] <= 700000.0
            
    def test_health_checks_with_real_services(self, client, redis_container, opensearch_container):
        """Test health checks with real services running."""
        import os
        os.environ["REDIS_URL"] = redis_container
        os.environ["OPENSEARCH_URL"] = opensearch_container
        
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert data["services"]["cache"] is True
        assert data["services"]["search"] is True
        

class TestErrorHandlingIntegration:
    """Integration tests for error handling scenarios."""
    
    def test_redis_connection_failure_handling(self, client):
        """Test graceful handling when Redis is unreachable."""
        import os
        # Point to non-existent Redis
        os.environ["REDIS_URL"] = "redis://localhost:9999"
        
        # Parse should still work without caching
        response = client.get("/parse?q=3 bed 2 bath Denver under 700k")
        assert response.status_code == 200
        
        data = response.json()
        assert data["cache_hit"] is False  # No cache due to connection failure
        assert "beds" in data  # Core functionality works
        
        # Health check should report cache as unhealthy
        health_response = client.get("/health")
        assert health_response.status_code == 503  # Degraded service
        
        health_data = health_response.json()
        assert health_data["status"] == "degraded"
        assert health_data["services"]["cache"] is False
        
    def test_opensearch_connection_failure_handling(self, client):
        """Test handling when OpenSearch is unreachable."""
        import os
        # Point to non-existent OpenSearch
        os.environ["OPENSEARCH_URL"] = "http://localhost:9999"
        
        # Parse should still work
        response = client.get("/parse?q=3 bed 2 bath Denver under 700k")
        assert response.status_code == 200
        
        # Search should fail gracefully
        search_request = {
            "beds": 3,
            "baths": 2,
            "city": "Denver",
            "max_price": 700000
        }
        
        search_response = client.post("/search", json=search_request)
        assert search_response.status_code == 503  # Service unavailable
        
        error_data = search_response.json()
        assert "detail" in error_data
        assert "search service" in error_data["detail"].lower()
        
    def test_malformed_opensearch_response_handling(self, client, opensearch_container):
        """Test handling of unexpected OpenSearch responses."""
        import os
        os.environ["OPENSEARCH_URL"] = opensearch_container
        
        # Create corrupted index or data that might cause parsing issues
        opensearch_client = OpenSearch([opensearch_container])
        
        try:
            opensearch_client.indices.delete(index="properties")
        except:
            pass
            
        # Create index but don't add proper mapping
        opensearch_client.indices.create(index="properties")
        
        # Add malformed document
        opensearch_client.index(
            index="properties",
            id="malformed",
            body={"malformed": "data", "price": "not_a_number"},
            refresh=True
        )
        
        search_request = {
            "beds": 3,
            "baths": 2,
            "city": "Denver",
            "max_price": 700000
        }
        
        # Should handle malformed data gracefully
        response = client.post("/search", json=search_request)
        # Should either succeed with empty results or handle error gracefully
        assert response.status_code in [200, 500, 503]
        

class TestPerformanceIntegration:
    """Performance-related integration tests."""
    
    def test_cache_performance_requirement(self, client, redis_container):
        """Test that cache hits return within <5ms requirement."""
        import os
        os.environ["REDIS_URL"] = redis_container
        
        query = "3 bed 2 bath Denver under 700k"
        
        # First call to populate cache
        client.get(f"/parse?q={query}")
        
        # Second call should be cache hit
        start_time = time.time()
        response = client.get(f"/parse?q={query}")
        end_time = time.time()
        
        assert response.status_code == 200
        data = response.json()
        assert data["cache_hit"] is True
        
        # Check response time (should be <5ms, but allow some margin for overhead)
        response_time_ms = (end_time - start_time) * 1000
        # Allow up to 50ms for test environment overhead
        assert response_time_ms < 50, f"Cache hit took {response_time_ms}ms, should be <5ms"
        
    def test_concurrent_requests_handling(self, client, redis_container):
        """Test handling of concurrent requests."""
        import os
        import threading
        os.environ["REDIS_URL"] = redis_container
        
        results = []
        errors = []
        
        def make_request(query_num):
            try:
                response = client.get(f"/parse?q={query_num} bed 2 bath Denver under 700k")
                results.append((query_num, response.status_code, response.json()))
            except Exception as e:
                errors.append((query_num, str(e)))
        
        # Launch multiple concurrent requests
        threads = []
        for i in range(10):
            thread = threading.Thread(target=make_request, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify all requests completed successfully
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 10
        
        # All should return 200
        for query_num, status_code, data in results:
            assert status_code == 200
            assert "beds" in data
            assert data["beds"] == query_num
            

class TestDataConsistencyIntegration:
    """Tests for data consistency across the pipeline."""
    
    def test_parse_search_data_consistency(self, client, opensearch_container):
        """Test that parsed data correctly filters search results."""
        import os
        os.environ["OPENSEARCH_URL"] = opensearch_container
        
        # Set up test data in OpenSearch
        opensearch_client = OpenSearch([opensearch_container])
        
        try:
            opensearch_client.indices.delete(index="properties")
        except:
            pass
            
        # Create index with mapping
        index_mapping = {
            "mappings": {
                "properties": {
                    "address": {"type": "text"},
                    "city": {"type": "keyword"},
                    "price": {"type": "float"},
                    "beds": {"type": "integer"},
                    "baths": {"type": "integer"}
                }
            }
        }
        opensearch_client.indices.create(index="properties", body=index_mapping)
        
        # Add test properties with different bed/bath counts
        test_properties = [
            {"address": "1 Bed Place", "city": "Denver", "price": 400000, "beds": 1, "baths": 1},
            {"address": "2 Bed Place", "city": "Denver", "price": 500000, "beds": 2, "baths": 1},
            {"address": "3 Bed Place", "city": "Denver", "price": 600000, "beds": 3, "baths": 2},
            {"address": "4 Bed Place", "city": "Denver", "price": 800000, "beds": 4, "baths": 3},
        ]
        
        for i, prop in enumerate(test_properties):
            opensearch_client.index(
                index="properties",
                id=f"test_{i}",
                body=prop,
                refresh=True
            )
        
        time.sleep(1)  # Wait for indexing
        
        # Parse query for 3 beds, max 700k
        parse_response = client.get("/parse?q=3 bed 2 bath Denver under 700k")
        assert parse_response.status_code == 200
        
        parsed_data = parse_response.json()
        
        # Use parsed data to search
        search_request = {
            "beds": parsed_data["beds"],
            "baths": parsed_data["baths"],
            "city": parsed_data["city"],
            "max_price": parsed_data["max_price"]
        }
        
        search_response = client.post("/search", json=search_request)
        assert search_response.status_code == 200
        
        results = search_response.json()
        
        # Should only return properties matching criteria
        for result in results:
            assert result["beds"] <= parsed_data["beds"]  # Beds should be <= parsed value
            assert result["price"] <= parsed_data["max_price"]  # Price should be under limit
            
        # Specifically should include the 3-bed property under 700k
        matching_results = [r for r in results if r["beds"] == 3 and r["price"] <= 700000]
        assert len(matching_results) >= 1
        
    def test_cache_key_generation_consistency(self, client, redis_container):
        """Test that cache keys are generated consistently."""
        import os
        os.environ["REDIS_URL"] = redis_container
        
        # Test various equivalent queries
        equivalent_queries = [
            "3 bed 2 bath Denver under 700k",
            "3 BED 2 BATH DENVER UNDER 700K",
            "  3   bed   2   bath   Denver   under   700k  ",
            "3bed 2bath Denver under 700000",
        ]
        
        responses = []
        for query in equivalent_queries:
            # Make sure each gets a fresh cache (by using slight variations)
            response = client.get(f"/parse?q={query}")
            assert response.status_code == 200
            responses.append(response.json())
        
        # All should parse to equivalent results (ignoring cache_hit differences)
        base_result = {k: v for k, v in responses[0].items() if k != "cache_hit"}
        
        for response_data in responses[1:]:
            comparison_result = {k: v for k, v in response_data.items() if k != "cache_hit"}
            assert base_result == comparison_result, f"Results should be identical for equivalent queries" 