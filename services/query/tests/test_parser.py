"""
Tests for query parser service
"""
import pytest
from unittest.mock import Mock, patch

from app.services.parser import QueryParser


class TestQueryParser:
    """Test query parser functionality"""
    
    def test_parse_basic_query(self):
        """Test parsing basic property query"""
        with patch('spacy.load') as mock_spacy:
            # Mock spaCy model
            mock_nlp = Mock()
            mock_doc = Mock()
            mock_ent = Mock()
            mock_ent.text = "Denver"
            mock_ent.label_ = "GPE"
            mock_doc.ents = [mock_ent]
            mock_nlp.return_value = mock_doc
            mock_spacy.return_value = mock_nlp
            
            parser = QueryParser()
            result, confidence = parser.parse_query("3 bed 2 bath Denver under 700k")
            
            assert result['beds'] == 3
            assert result['baths'] == 2
            assert result['city'] == "Denver"
            assert result['max_price'] == 700000.0
            assert 0 <= confidence <= 1
    
    def test_parse_empty_query(self):
        """Test parsing empty query raises error"""
        parser = QueryParser()
        
        with pytest.raises(ValueError, match="Query cannot be empty"):
            parser.parse_query("")
        
        with pytest.raises(ValueError, match="Query cannot be empty"):
            parser.parse_query("   ")
    
    def test_parse_long_query(self):
        """Test parsing overly long query raises error"""
        parser = QueryParser()
        long_query = "a" * 501  # Exceeds max length
        
        with pytest.raises(ValueError, match="Query too long"):
            parser.parse_query(long_query)
    
    def test_extract_beds(self):
        """Test bedroom extraction patterns"""
        with patch('spacy.load'):
            parser = QueryParser()
            
            # Test various bed patterns
            assert parser._extract_beds("3 bed house") == 3
            assert parser._extract_beds("2 bedroom apartment") == 2
            assert parser._extract_beds("1 br condo") == 1
            assert parser._extract_beds("4b home") == 4
            assert parser._extract_beds("no beds mentioned") == 0
            
            # Test sanity check
            assert parser._extract_beds("25 bed mansion") == 0  # Too many beds
    
    def test_extract_baths(self):
        """Test bathroom extraction patterns"""
        with patch('spacy.load'):
            parser = QueryParser()
            
            # Test various bath patterns
            assert parser._extract_baths("2 bath house") == 2
            assert parser._extract_baths("1 bathroom condo") == 1
            assert parser._extract_baths("3 ba home") == 3
            assert parser._extract_baths("no baths mentioned") == 0
            
            # Test sanity check
            assert parser._extract_baths("30 bath estate") == 0  # Too many baths
    
    def test_extract_price(self):
        """Test price extraction patterns"""
        with patch('spacy.load'):
            parser = QueryParser()
            
            # Test various price patterns
            assert parser._extract_price("under $500,000") == 500000.0
            assert parser._extract_price("below $1,200,000") == 1200000.0
            assert parser._extract_price("max 800k") == 800000.0
            assert parser._extract_price("maximum $750,000") == 750000.0
            assert parser._extract_price("< 600000") == 600000.0
            
            # Test default fallback
            assert parser._extract_price("no price mentioned") == 1000000.0
            
            # Test sanity checks
            assert parser._extract_price("under $200") == 1000000.0  # Too low
            assert parser._extract_price("under $200000000") == 1000000.0  # Too high
    
    def test_extract_city_with_ner(self):
        """Test city extraction using NER"""
        with patch('spacy.load') as mock_spacy:
            # Mock spaCy with location entity
            mock_nlp = Mock()
            mock_doc = Mock()
            mock_ent = Mock()
            mock_ent.text = "Seattle"
            mock_ent.label_ = "GPE"
            mock_doc.ents = [mock_ent]
            mock_nlp.return_value = mock_doc
            mock_spacy.return_value = mock_nlp
            
            parser = QueryParser()
            city = parser._extract_city("house in Seattle")
            
            assert city == "Seattle"
    
    def test_extract_city_with_keywords(self):
        """Test city extraction using keywords"""
        with patch('spacy.load') as mock_spacy:
            # Mock spaCy with no entities
            mock_nlp = Mock()
            mock_doc = Mock()
            mock_doc.ents = []
            mock_nlp.return_value = mock_doc
            mock_spacy.return_value = mock_nlp
            
            parser = QueryParser()
            
            # Test keyword-based extraction
            assert parser._extract_city("house near Portland") == "Portland"
            assert parser._extract_city("property at Austin") == "Austin"
            assert parser._extract_city("condo by Miami") == "Miami"
    
    def test_extract_city_default(self):
        """Test city extraction default fallback"""
        with patch('spacy.load') as mock_spacy:
            # Mock spaCy with no entities
            mock_nlp = Mock()
            mock_doc = Mock()
            mock_doc.ents = []
            mock_nlp.return_value = mock_doc
            mock_spacy.return_value = mock_nlp
            
            parser = QueryParser()
            city = parser._extract_city("house with no city")
            
            assert city == "Denver"  # Default fallback
    
    def test_confidence_calculation(self):
        """Test confidence score calculation"""
        with patch('spacy.load'):
            parser = QueryParser()
            
            # High confidence - all fields extracted
            confidence = parser._calculate_confidence(
                "3 bed 2 bath Seattle under 500k",
                beds=3, baths=2, city="Seattle", max_price=500000.0
            )
            assert confidence == 1.0
            
            # Lower confidence - some defaults
            confidence = parser._calculate_confidence(
                "house in Denver",
                beds=0, baths=0, city="Denver", max_price=1000000.0
            )
            assert confidence == 0.4  # Partial credit for defaults
    
    def test_cache_key_generation(self):
        """Test cache key generation"""
        key1 = QueryParser.generate_cache_key("3 bed 2 bath Denver")
        key2 = QueryParser.generate_cache_key("3 bed 2 bath denver")  # Different case
        key3 = QueryParser.generate_cache_key("3 bed 2 bath Denver")  # Same as key1
        
        assert key1 == key2  # Case insensitive
        assert key1 == key3  # Consistent
        assert len(key1) == 64  # SHA256 hex length
    
    def test_spacy_model_fallback(self):
        """Test fallback when spaCy model not available"""
        with patch('spacy.load', side_effect=OSError("Model not found")):
            with patch('spacy.lang.en.English') as mock_english:
                mock_nlp = Mock()
                mock_english.return_value = mock_nlp
                
                # Should not raise error, uses English fallback
                parser = QueryParser()
                assert parser.nlp == mock_nlp 