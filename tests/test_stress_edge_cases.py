"""
Stress tests and performance edge cases for Anthropic integration
"""
import json
import pytest
import time
import threading
from unittest.mock import Mock, patch
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.services.parser import QueryParser
from app.core.config import settings


class TestStressEdgeCases:
    """Test stress conditions and edge cases that could break the system"""
    
    def test_rapid_sequential_queries(self):
        """Test handling of rapid sequential queries"""
        parser = QueryParser()
        queries = [
            "luxury apartment downtown",
            "family home with pool", 
            "studio near university",
            "penthouse with view",
            "cozy cottage by lake"
        ] * 10  # 50 queries total
        
        results = []
        start_time = time.time()
        
        for query in queries:
            try:
                result, confidence = parser.parse_query(query)
                results.append((result, confidence))
            except Exception as e:
                pytest.fail(f"Failed on query '{query}': {e}")
        
        end_time = time.time()
        
        # All queries should complete successfully
        assert len(results) == len(queries)
        
        # Should complete in reasonable time
        total_time = end_time - start_time
        assert total_time < 15, f"Took too long: {total_time}s for {len(queries)} queries"
    
    def test_memory_usage_with_large_queries(self):
        """Test memory usage doesn't explode with large queries"""
        parser = QueryParser()
        
        # Create progressively larger queries
        base_query = "I'm looking for a beautiful home with "
        for size in [100, 200, 400, 500]:  # Up to max length
            if size <= settings.max_query_length:
                large_query = base_query + "amazing features " * (size // 20)
                large_query = large_query[:settings.max_query_length]  # Truncate to max
                
                # Should handle without memory issues
                result, confidence = parser.parse_query(large_query)
                assert result is not None
    
    def test_regex_performance_with_pathological_input(self):
        """Test regex performance with inputs designed to cause backtracking"""
        parser = QueryParser()
        
        # Pathological cases for regex engines
        pathological_queries = [
            "bed" * 50 + "room",  # Many repeated patterns
            "1" * 30 + " bed house",  # Very long numbers
            "a" * 100 + " 3 bed " + "b" * 100,  # Long text around pattern
            "3" + "." * 50 + "bed",  # Many dots (can cause backtracking)
        ]
        
        for query in pathological_queries:
            start_time = time.time()
            result, confidence = parser.parse_query(query)
            end_time = time.time()
            
            # Should complete quickly even with pathological input
            assert end_time - start_time < 1.0, f"Query took too long: {end_time - start_time}s"
            assert result is not None


class TestAnthropicFailureRecovery:
    """Test various Anthropic failure and recovery scenarios"""
    
    def test_anthropic_timeout_recovery(self):
        """Test recovery from Anthropic timeout scenarios"""
        parser = QueryParser()
        mock_client = Mock()
        
        # Simulate timeout followed by success
        timeout_count = 0
        def timeout_then_success(*args, **kwargs):
            nonlocal timeout_count
            timeout_count += 1
            if timeout_count <= 2:
                raise Exception(f"Timeout {timeout_count}")
            
            mock_response = Mock()
            mock_response.completion = '{"beds": 2, "baths": 1, "city": "Phoenix", "max_price": 450000}'
            return mock_response
        
        mock_client.completions.create.side_effect = timeout_then_success
        parser.anthropic_client = mock_client
        
        with patch('time.sleep'):  # Speed up test
            result, confidence = parser.parse_query("downtown loft")
        
        # Should eventually succeed or fall back gracefully
        assert result is not None
        # Either got Anthropic result or Tier 1 fallback
        assert result['city'] in ["Phoenix", "Denver"]


class TestExtremeInputs:
    """Test extreme input variations that could cause issues"""
    
    def test_mixed_language_queries(self):
        """Test queries with mixed languages"""
        parser = QueryParser()
        
        mixed_queries = [
            "3 bed casa in Miami under 500k",  # English + Spanish
            "2 bedroom maison near downtown",  # English + French
            "luxury appartement with 2 bath",  # Mixed French/English
        ]
        
        for query in mixed_queries:
            result, confidence = parser.parse_query(query)
            # Should extract what it can from English parts
            assert result is not None
            assert isinstance(result['beds'], int)
            assert isinstance(result['baths'], int)
    
    def test_nested_structures_and_symbols(self):
        """Test queries with complex nested structures"""
        parser = QueryParser()
        
        complex_queries = [
            "Looking for 3 bed (with master suite) 2 bath [preferably updated] in Denver (or nearby) under $700k",
            "((3 bed)) [[2 bath]] <<Denver>> {{under 500k}}",
            "Property [3-bed] (2-bath) in 'Seattle' under \"600k\"",
        ]
        
        for query in complex_queries:
            result, confidence = parser.parse_query(query)
            # Should parse successfully despite complex structure
            assert result is not None
            # Should extract numeric values correctly
            if 'bed' in query.lower():
                assert result['beds'] >= 0


class TestConcurrencyStress:
    """Test concurrent usage stress scenarios"""
    
    def test_concurrent_anthropic_calls(self):
        """Test concurrent Anthropic API calls with mocked client"""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.completion = '{"beds": 2, "baths": 1, "city": "Seattle", "max_price": 400000}'
        mock_client.completions.create.return_value = mock_response
        
        parser = QueryParser()
        parser.anthropic_client = mock_client
        
        def parse_low_confidence_query(thread_id):
            # Use a query that will trigger Tier 2
            query = f"cozy place thread {thread_id}"
            return parser.parse_query(query)
        
        # Run 10 concurrent queries
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(parse_low_confidence_query, i) for i in range(10)]
            results = [future.result() for future in as_completed(futures)]
        
        # All should succeed
        assert len(results) == 10
        for result, confidence in results:
            assert result['beds'] == 2
            assert result['city'] == "Seattle"


# Performance benchmarking test
def test_performance_benchmark():
    """Performance benchmark test"""
    parser = QueryParser()
    
    test_queries = [
        "3 bed 2 bath Denver under 700k",
        "luxury apartment downtown",
        "family home with pool",
        "cozy cottage by the lake",
        "modern studio near university"
    ]
    
    times = []
    
    for query in test_queries * 5:  # 25 queries total
        start = time.time()
        result, confidence = parser.parse_query(query)
        end = time.time()
        times.append(end - start)
    
    avg_time = sum(times) / len(times)
    max_time = max(times)
    
    # Performance assertions
    assert avg_time < 0.1, f"Average time too slow: {avg_time:.3f}s"
    assert max_time < 0.5, f"Max time too slow: {max_time:.3f}s"
    
    print(f"Performance: avg={avg_time:.3f}s, max={max_time:.3f}s")


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 