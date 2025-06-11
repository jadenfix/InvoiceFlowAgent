"""
Stress tests and advanced edge cases for Anthropic integration
"""
import json
import pytest
import time
import threading
from unittest.mock import Mock, patch
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.services.parser import QueryParser
from app.core.config import settings


class TestStressAndConcurrency:
    """Test stress conditions and concurrency edge cases"""
    
    def test_rapid_sequential_queries(self):
        """Test handling of rapid sequential queries"""
        parser = QueryParser()
        queries = [
            "luxury apartment downtown",
            "family home with pool",
            "studio near university",
            "penthouse with view",
            "cozy cottage by lake"
        ] * 20  # 100 queries total
        
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
        
        # Should complete in reasonable time (rough benchmark)
        total_time = end_time - start_time
        assert total_time < 30, f"Took too long: {total_time}s for {len(queries)} queries"
    
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


class TestAnthropicAPIFailureScenarios:
    """Test various Anthropic API failure scenarios"""
    
    def test_intermittent_network_failures(self):
        """Test handling of intermittent network failures"""
        parser = QueryParser()
        mock_client = Mock()
        
        # Simulate intermittent failures
        responses = [
            Exception("Network timeout"),
            Exception("Connection reset"),
            Mock(completion='{"beds": 3, "baths": 2, "city": "Portland", "max_price": 550000}'),
            Exception("Temporary server error"),
            Mock(completion='{"beds": 1, "baths": 1, "city": "Austin", "max_price": 350000}'),
        ]
        
        call_count = 0
        def side_effect(*args, **kwargs):
            nonlocal call_count
            response = responses[call_count % len(responses)]
            call_count += 1
            if isinstance(response, Exception):
                raise response
            return response
        
        mock_client.completions.create.side_effect = side_effect
        parser.anthropic_client = mock_client
        
        # Test multiple queries with intermittent failures
        queries = ["cozy apartment", "family home", "luxury condo"]
        
        with patch('time.sleep'):  # Speed up retries
            for query in queries:
                result, confidence = parser.parse_query(query)
                # Should either succeed with Anthropic or fall back to Tier 1
                assert result is not None
                assert 'beds' in result
    
    def test_anthropic_response_corruption(self):
        """Test handling of corrupted Anthropic responses"""
        parser = QueryParser()
        mock_client = Mock()
        
        # Various types of corrupted responses
        corrupted_responses = [
            '{"beds": 2, "baths": 1, "city": "Boston", "max_p',  # Truncated
            '{"beds": 2, "baths": 1, "city": "Boston"} extra text',  # Extra text
            '{"beds": 2, "baths": 1, "city": "Boston", "max_price": 400000}{"beds": 1}',  # Multiple JSON
            'HTTP/1.1 500 Internal Server Error\n{"beds": 2}',  # HTTP error mixed with JSON
            'beds: 2, baths: 1, city: Boston, max_price: 400000',  # Invalid JSON format
        ]
        
        for corrupted_response in corrupted_responses:
            mock_response = Mock()
            mock_response.completion = corrupted_response
            mock_client.completions.create.return_value = mock_response
            parser.anthropic_client = mock_client
            
            result, confidence = parser.parse_query("studio apartment")
            
            # Should fall back to Tier 1 gracefully
            assert result['city'] == "Denver"
            assert result['max_price'] == 1_000_000.0


class TestExtremeInputVariations:
    """Test extreme variations in input queries"""
    
    def test_mixed_language_queries(self):
        """Test queries with mixed languages"""
        parser = QueryParser()
        
        mixed_queries = [
            "3 bed casa in Miami under 500k",  # English + Spanish
            "2 bedroom maison near downtown",  # English + French
            "luxury appartement with 2 bath",  # Mixed French/English
            "Studio wohnung under $300000",  # English + German
        ]
        
        for query in mixed_queries:
            result, confidence = parser.parse_query(query)
            # Should extract what it can from English parts
            assert result is not None
            assert isinstance(result['beds'], int)
            assert isinstance(result['baths'], int)
    
    def test_nested_parentheses_and_brackets(self):
        """Test queries with complex nested structures"""
        parser = QueryParser()
        
        complex_queries = [
            "Looking for 3 bed (with master suite) 2 bath [preferably updated] in Denver (or nearby) under $700k",
            "House: {3 bedrooms, 2 bathrooms, location: 'Austin', price < 600000}",
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
    
    def test_mathematical_expressions_in_queries(self):
        """Test queries with mathematical expressions"""
        parser = QueryParser()
        
        math_queries = [
            "Looking for 2+1 bed house under 500*1000",  # Simple math
            "House with 3^1 bedrooms under $5e5",  # Scientific notation
            "Property with sqrt(9) bedrooms under 0.5M",  # Math functions
            "Apartment with 10/5 bathrooms under 600000/1",  # Division
        ]
        
        for query in math_queries:
            result, confidence = parser.parse_query(query)
            # Should handle gracefully, likely not evaluating math
            assert result is not None
            # Should extract some values or fall back to defaults
            assert isinstance(result['beds'], int)
            assert isinstance(result['max_price'], (int, float))
    
    def test_queries_with_urls_and_emails(self):
        """Test queries containing URLs and email addresses"""
        parser = QueryParser()
        
        url_queries = [
            "3 bed house like the one at https://example.com/property/123 under 600k",
            "Contact agent@realty.com for 2 bath condo in Denver",
            "Property details: www.homes.com/listing?id=456 - 4 bed under 800k",
            "See photos at http://photos.realtor.net/prop789 for this 2 bed 1 bath",
        ]
        
        for query in url_queries:
            result, confidence = parser.parse_query(query)
            # Should extract relevant info while ignoring URLs/emails
            assert result is not None
            if 'bed' in query and any(char.isdigit() for char in query):
                # Should extract bed count if clearly stated
                assert result['beds'] >= 0


class TestPerformanceEdgeCases:
    """Test performance under various conditions"""
    
    def test_regex_performance_with_pathological_input(self):
        """Test regex performance with inputs designed to cause backtracking"""
        parser = QueryParser()
        
        # Pathological cases for regex engines
        pathological_queries = [
            "bed" * 100 + "room",  # Many repeated patterns
            "1" * 50 + " bed house",  # Very long numbers
            "a" * 200 + " 3 bed " + "b" * 200,  # Long text around pattern
            "3" + "." * 100 + "bed",  # Many dots (can cause backtracking)
        ]
        
        for query in pathological_queries:
            start_time = time.time()
            result, confidence = parser.parse_query(query)
            end_time = time.time()
            
            # Should complete quickly even with pathological input
            assert end_time - start_time < 1.0, f"Query took too long: {end_time - start_time}s"
            assert result is not None
    
    def test_spacy_performance_with_complex_text(self):
        """Test spaCy performance with complex linguistic structures"""
        parser = QueryParser()
        
        complex_queries = [
            "I am interested in finding a beautiful, spacious, modern, luxurious, and well-appointed residence with exactly three comfortable bedrooms and precisely two fully-equipped bathrooms located in the vibrant and bustling metropolitan area of Denver, Colorado, with a maximum purchase price not exceeding six hundred thousand dollars",
            "Property requirements: bedrooms (count: 3), bathrooms (quantity: 2), location (city: Denver, state: Colorado), financial constraint (maximum: $600,000)",
            "Looking for 3BR/2BA home in Denver under $600K - must have: updated kitchen, hardwood floors, large backyard, garage, good school district, quiet neighborhood, convenient shopping",
        ]
        
        for query in complex_queries:
            start_time = time.time()
            result, confidence = parser.parse_query(query)
            end_time = time.time()
            
            # Should handle complex text efficiently
            assert end_time - start_time < 2.0, f"Complex query took too long: {end_time - start_time}s"
            assert result is not None
            # Should still extract key information
            assert result['beds'] >= 0
            assert result['baths'] >= 0


class TestErrorRecoveryScenarios:
    """Test error recovery in various scenarios"""
    
    def test_recovery_from_anthropic_timeout_chains(self):
        """Test recovery from chains of Anthropic timeouts"""
        parser = QueryParser()
        mock_client = Mock()
        
        # Simulate a series of timeouts followed by success
        timeout_count = 0
        def timeout_then_success(*args, **kwargs):
            nonlocal timeout_count
            timeout_count += 1
            if timeout_count <= 3:
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
    
    def test_graceful_degradation_sequence(self):
        """Test graceful degradation through multiple failure modes"""
        parser = QueryParser()
        
        # Simulate a sequence of failures
        with patch.object(parser, '_tier2_anthropic_parse') as mock_tier2:
            # First call: Anthropic completely fails
            mock_tier2.return_value = None
            
            result1, confidence1 = parser.parse_query("luxury penthouse")
            
            # Should fall back to Tier 1
            assert result1['city'] == "Denver"
            assert result1['max_price'] == 1_000_000.0
            
            # Second call: Anthropic returns partial data
            mock_tier2.return_value = {'beds': 3, 'baths': 0, 'city': 'Denver', 'max_price': 1_000_000.0}
            
            result2, confidence2 = parser.parse_query("modern apartment")
            
            # Should merge Tier 1 and partial Tier 2 data
            assert result2 is not None


# Performance benchmarking utilities
def benchmark_query_performance():
    """Utility function to benchmark query performance"""
    parser = QueryParser()
    
    test_queries = [
        "3 bed 2 bath Denver under 700k",
        "luxury apartment downtown",
        "family home with pool",
        "cozy cottage by the lake",
        "modern studio near university"
    ]
    
    times = []
    
    for query in test_queries * 10:  # 50 queries total
        start = time.time()
        result, confidence = parser.parse_query(query)
        end = time.time()
        times.append(end - start)
    
    avg_time = sum(times) / len(times)
    max_time = max(times)
    min_time = min(times)
    
    print(f"Performance benchmark:")
    print(f"  Average time: {avg_time:.3f}s")
    print(f"  Max time: {max_time:.3f}s")
    print(f"  Min time: {min_time:.3f}s")
    print(f"  Total queries: {len(times)}")
    
    return avg_time, max_time, min_time


if __name__ == "__main__":
    # Run benchmark if executed directly
    benchmark_query_performance() 