"""
Query parsing service using spaCy, regex, and Anthropic Tier 2 fallback
"""
import re
import hashlib
import json
import time
from typing import Dict, Optional, Tuple
import spacy
from spacy.lang.en import English

try:
    import anthropic
    from anthropic import APIError, APIConnectionError, RateLimitError
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

from ..core.config import settings
from ..core.logging import get_logger
from ..prompts import TIER2_SYSTEM, TIER2_USER

logger = get_logger(__name__)


class QueryParser:
    """Natural language query parser with Anthropic Tier 2 fallback"""
    
    def __init__(self):
        """Initialize parser with spaCy model and Anthropic client"""
        try:
            self.nlp = spacy.load(settings.spacy_model)
            logger.info(f"Loaded spaCy model: {settings.spacy_model}")
        except OSError:
            logger.warning(f"spaCy model {settings.spacy_model} not found, using blank English model")
            self.nlp = English()
        
        # Initialize Anthropic client if available
        self.anthropic_client = None
        if ANTHROPIC_AVAILABLE and settings.anthropic_api_key:
            try:
                self.anthropic_client = anthropic.Client(api_key=settings.anthropic_api_key)
                logger.info("Anthropic client initialized for Tier 2 fallback")
            except Exception as e:
                logger.warning(f"Failed to initialize Anthropic client: {e}")
        else:
            if not ANTHROPIC_AVAILABLE:
                logger.warning("Anthropic library not available, Tier 2 fallback disabled")
            else:
                logger.warning("ANTHROPIC_API_KEY not set, Tier 2 fallback disabled")
        
        # Compiled regex patterns for performance
        self.bed_pattern = re.compile(r'(\d+)\s*(?:bed|bedroom|br|b)', re.IGNORECASE)
        self.bath_pattern = re.compile(r'(\d+)\s*(?:bath|bathroom|ba)', re.IGNORECASE)
        self.price_pattern = re.compile(r'(?:under|below|max|maximum|<|≤)\s*\$?(\d+(?:,\d{3})*(?:\.\d{2})?)\s*k?', re.IGNORECASE)
        self.city_keywords = {'in', 'at', 'near', 'around', 'by'}
    
    def parse_query(self, query: str) -> Tuple[Dict, float]:
        """Parse natural language query with Tier 2 fallback"""
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        
        if len(query) > settings.max_query_length:
            raise ValueError(f"Query too long (max {settings.max_query_length} characters)")
        
        query = query.strip()
        logger.info(f"Parsing query: {query}")
        
        # Tier 1: Extract using spaCy and regex
        tier1_result = self._tier1_parse(query)
        confidence = tier1_result["confidence"]
        
        # Check if Tier 2 fallback is needed
        if confidence < settings.tier2_confidence_threshold and self.anthropic_client:
            logger.info(f"Confidence {confidence} below threshold {settings.tier2_confidence_threshold}, using Tier 2 fallback")
            tier2_result = self._tier2_anthropic_parse(query)
            
            if tier2_result:
                merged_result = self._merge_parse_results(tier1_result, tier2_result)
                logger.info(f"Tier 2 fallback successful: {merged_result}")
                return merged_result, min(1.0, confidence + 0.2)
            else:
                logger.warning("Tier 2 fallback failed, using Tier 1 only")
        
        logger.info(f"Using Tier 1 result: {tier1_result}")
        return tier1_result, confidence
    
    def _tier1_parse(self, query: str) -> Dict:
        """Tier 1 parsing using spaCy and regex"""
        beds = self._extract_beds(query)
        baths = self._extract_baths(query)
        max_price = self._extract_price(query)
        city = self._extract_city(query)
        confidence = self._calculate_confidence(query, beds, baths, city, max_price)
        
        return {
            'beds': beds,
            'baths': baths,
            'city': city,
            'max_price': max_price,
            'confidence': confidence
        }
    
    def _tier2_anthropic_parse(self, query: str) -> Optional[Dict]:
        """Tier 2 parsing using Anthropic Claude with retries"""
        if not self.anthropic_client:
            return None
        
        for attempt in range(settings.anthropic_max_retries + 1):
            try:
                prompt = TIER2_SYSTEM + f"\n\nHuman: {TIER2_USER.format(user_query=query)}\n\nAssistant:"
                
                response = self.anthropic_client.completions.create(
                    model=settings.anthropic_model,
                    prompt=prompt,
                    max_tokens=settings.anthropic_max_tokens,
                    temperature=settings.anthropic_temperature,
                    stop_sequences=["\n\nHuman:"]
                )
                
                try:
                    llm_json = json.loads(response.completion.strip())
                    
                    if all(field in llm_json for field in ['beds', 'baths', 'city', 'max_price']):
                        validated_result = {
                            'beds': max(0, min(20, int(llm_json['beds']) if llm_json['beds'] is not None else 0)),
                            'baths': max(0, min(20, int(llm_json['baths']) if llm_json['baths'] is not None else 0)),
                            'city': str(llm_json['city']) if llm_json['city'] else "Denver",
                            'max_price': max(1000, min(100_000_000, float(llm_json['max_price']) if llm_json['max_price'] is not None else 1_000_000.0))
                        }
                        
                        logger.info(f"Anthropic parse successful: {validated_result}")
                        return validated_result
                    else:
                        logger.warning(f"Anthropic response missing fields: {llm_json}")
                        
                except (json.JSONDecodeError, ValueError, TypeError) as e:
                    logger.warning(f"Failed to parse Anthropic response: {e}")
                
            except Exception as e:
                logger.warning(f"Anthropic API error on attempt {attempt + 1}: {e}")
                
                if attempt < settings.anthropic_max_retries:
                    delay = settings.anthropic_retry_delay * (settings.anthropic_retry_backoff ** attempt)
                    time.sleep(delay)
                else:
                    logger.error("All Anthropic API retry attempts failed")
        
        return None
    
    def _merge_parse_results(self, tier1: Dict, tier2: Dict) -> Dict:
        """Merge Tier 1 and Tier 2 results, preferring Tier 2 for non-default values"""
        merged = tier1.copy()
        
        # Safely handle None values
        if tier2.get('beds') is not None and tier2.get('beds', 0) > 0:
            merged['beds'] = tier2['beds']
        if tier2.get('baths') is not None and tier2.get('baths', 0) > 0:
            merged['baths'] = tier2['baths']
        if tier2.get('city') and tier2['city'] != "Denver":
            merged['city'] = tier2['city']
        if tier2.get('max_price') is not None and tier2.get('max_price', 0) > 0 and tier2['max_price'] != 1_000_000.0:
            merged['max_price'] = tier2['max_price']
        
        return merged
    
    def _extract_beds(self, query: str) -> int:
        """Extract number of bedrooms"""
        match = self.bed_pattern.search(query)
        if match:
            beds = int(match.group(1))
            return beds if beds <= 20 else 0
        return 0
    
    def _extract_baths(self, query: str) -> int:
        """Extract number of bathrooms"""
        match = self.bath_pattern.search(query)
        if match:
            baths = int(match.group(1))
            return baths if baths <= 20 else 0
        return 0
    
    def _extract_price(self, query: str) -> float:
        """Extract maximum price"""
        match = self.price_pattern.search(query)
        if match:
            price_str = match.group(1).replace(',', '')
            price = float(price_str)
            
            if 'k' in match.group(0).lower():
                price *= 1000
            
            if 1000 <= price <= 100_000_000:
                return price
                
        return 1_000_000.0
    
    def _extract_city(self, query: str) -> str:
        """Extract city name using spaCy NER"""
        doc = self.nlp(query)
        
        locations = []
        for ent in doc.ents:
            if ent.label_ in {'GPE', 'LOC'}:
                city_name = ent.text.strip()
                if (len(city_name) > 1 and 
                    city_name.lower() not in {'us', 'usa', 'america', 'united states'}):
                    locations.append(city_name)
        
        if locations:
            return locations[0].title()
        
        # Fallback: look for words after location keywords
        words = query.lower().split()
        for i, word in enumerate(words):
            if word in self.city_keywords and i + 1 < len(words):
                potential_city = words[i + 1].title()
                if potential_city.isalpha() and len(potential_city) > 2:
                    return potential_city
        
        return "Denver"
    
    def _calculate_confidence(self, query: str, beds: int, baths: int, city: str, max_price: float) -> float:
        """Calculate confidence score based on extraction results"""
        score = 0.0
        
        # Beds confidence
        if beds > 0 and 'bed' in query.lower():
            score += 0.25
        elif beds == 0:
            score += 0.1
        
        # Baths confidence
        if baths > 0 and 'bath' in query.lower():
            score += 0.25
        elif baths == 0:
            score += 0.1
        
        # City confidence
        if city != "Denver":
            score += 0.25
        else:
            score += 0.1
        
        # Price confidence
        if max_price != 1_000_000.0:
            score += 0.25
        else:
            score += 0.1
        
        return round(score, 2)
    
    @staticmethod
    def generate_cache_key(query: str) -> str:
        """Generate cache key for query"""
        normalized_query = query.strip().lower()
        return hashlib.sha256(normalized_query.encode()).hexdigest()
