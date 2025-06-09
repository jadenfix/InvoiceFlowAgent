"""
Query parsing service using spaCy and regex
"""
import re
import hashlib
import json
from typing import Dict, Optional, Tuple
import spacy
from spacy.lang.en import English

from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger(__name__)


class QueryParser:
    """Natural language query parser"""
    
    def __init__(self):
        """Initialize parser with spaCy model"""
        try:
            self.nlp = spacy.load(settings.spacy_model)
            logger.info(f"Loaded spaCy model: {settings.spacy_model}")
        except OSError:
            logger.warning(f"spaCy model {settings.spacy_model} not found, using blank English model")
            self.nlp = English()
        
        # Compiled regex patterns for performance
        self.bed_pattern = re.compile(r'(\d+)\s*(?:bed|bedroom|br|b)', re.IGNORECASE)
        self.bath_pattern = re.compile(r'(\d+)\s*(?:bath|bathroom|ba)', re.IGNORECASE)
        self.price_pattern = re.compile(r'(?:under|below|max|maximum|<|≤)\s*\$?(\d+(?:,\d{3})*(?:\.\d{2})?)\s*k?', re.IGNORECASE)
        self.city_keywords = {'in', 'at', 'near', 'around', 'by'}
    
    def parse_query(self, query: str) -> Tuple[Dict, float]:
        """
        Parse natural language query into structured data
        
        Args:
            query: Raw query string
            
        Returns:
            Tuple of (parsed_data, confidence_score)
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        
        if len(query) > settings.max_query_length:
            raise ValueError(f"Query too long (max {settings.max_query_length} characters)")
        
        query = query.strip()
        logger.info(f"Parsing query: {query}")
        
        # Extract numeric values
        beds = self._extract_beds(query)
        baths = self._extract_baths(query)
        max_price = self._extract_price(query)
        
        # Extract location using spaCy
        city = self._extract_city(query)
        
        # Calculate confidence score
        confidence = self._calculate_confidence(query, beds, baths, city, max_price)
        
        parsed_data = {
            'beds': beds,
            'baths': baths,
            'city': city,
            'max_price': max_price,
            'confidence': confidence
        }
        
        logger.info(f"Parsed result: {parsed_data}")
        return parsed_data, confidence
    
    def _extract_beds(self, query: str) -> int:
        """Extract number of bedrooms"""
        match = self.bed_pattern.search(query)
        if match:
            beds = int(match.group(1))
            if beds > 20:  # Sanity check
                logger.warning(f"Unrealistic bedroom count: {beds}, defaulting to 0")
                return 0
            return beds
        return 0
    
    def _extract_baths(self, query: str) -> int:
        """Extract number of bathrooms"""
        match = self.bath_pattern.search(query)
        if match:
            baths = int(match.group(1))
            if baths > 20:  # Sanity check
                logger.warning(f"Unrealistic bathroom count: {baths}, defaulting to 0")
                return 0
            return baths
        return 0
    
    def _extract_price(self, query: str) -> float:
        """Extract maximum price"""
        match = self.price_pattern.search(query)
        if match:
            price_str = match.group(1).replace(',', '')
            price = float(price_str)
            
            # Handle 'k' suffix (thousands)
            if 'k' in match.group(0).lower():
                price *= 1000
            
            # Sanity checks
            if price > 100_000_000:  # $100M max
                logger.warning(f"Unrealistic price: {price}, defaulting to 1M")
                return 1_000_000.0
            if price < 1000:  # $1k minimum
                logger.warning(f"Price too low: {price}, defaulting to 1M")
                return 1_000_000.0
                
            return price
        
        # Default fallback price
        return 1_000_000.0
    
    def _extract_city(self, query: str) -> str:
        """Extract city name using spaCy NER"""
        doc = self.nlp(query)
        
        # Look for GPE (Geopolitical entities) or LOC (Locations)
        locations = []
        for ent in doc.ents:
            if ent.label_ in {'GPE', 'LOC'}:
                # Filter out common non-city words
                city_name = ent.text.strip()
                if (len(city_name) > 1 and 
                    city_name.lower() not in {'us', 'usa', 'america', 'united states'}):
                    locations.append(city_name)
        
        if locations:
            # Return the first valid location
            city = locations[0].title()
            logger.info(f"Extracted city from NER: {city}")
            return city
        
        # Fallback: look for words after location keywords
        words = query.lower().split()
        for i, word in enumerate(words):
            if word in self.city_keywords and i + 1 < len(words):
                potential_city = words[i + 1].title()
                # Basic validation
                if potential_city.isalpha() and len(potential_city) > 2:
                    logger.info(f"Extracted city from keywords: {potential_city}")
                    return potential_city
        
        # Final fallback
        logger.warning("Could not extract city, using default")
        return "Denver"
    
    def _calculate_confidence(self, query: str, beds: int, baths: int, city: str, max_price: float) -> float:
        """Calculate confidence score based on extraction results"""
        score = 0.0
        total_factors = 4
        
        # Beds confidence
        if beds > 0 and 'bed' in query.lower():
            score += 0.25
        elif beds == 0:
            score += 0.1  # Partial credit for default
        
        # Baths confidence
        if baths > 0 and 'bath' in query.lower():
            score += 0.25
        elif baths == 0:
            score += 0.1  # Partial credit for default
        
        # City confidence
        if city != "Denver":  # Not default
            score += 0.25
        else:
            score += 0.1  # Partial credit for default
        
        # Price confidence
        if max_price != 1_000_000.0:  # Not default
            score += 0.25
        else:
            score += 0.1  # Partial credit for default
        
        return round(score, 2)
    
    @staticmethod
    def generate_cache_key(query: str) -> str:
        """Generate cache key for query"""
        normalized_query = query.strip().lower()
        return hashlib.sha256(normalized_query.encode()).hexdigest() 