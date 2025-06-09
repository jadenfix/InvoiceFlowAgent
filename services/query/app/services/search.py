"""
OpenSearch service for property search
"""
import time
from typing import Dict, List, Optional
from opensearchpy import OpenSearch, RequestsHttpConnection
from opensearchpy.exceptions import ConnectionError, RequestError, NotFoundError

from ..core.config import settings
from ..core.logging import get_logger
from ..models.query import SearchRequest, PropertyResult

logger = get_logger(__name__)


class SearchService:
    """OpenSearch service for property search"""
    
    def __init__(self):
        """Initialize OpenSearch client"""
        self.client = None
        self.search_enabled = True
        self.index_name = "listings_dev"
        self._connect()
    
    def _connect(self) -> None:
        """Connect to OpenSearch with error handling"""
        try:
            # Build connection configuration
            connection_config = {
                'hosts': [{
                    'host': settings.opensearch_host,
                    'port': settings.opensearch_port,
                    'scheme': settings.opensearch_scheme
                }],
                'timeout': 30,
                'max_retries': 3,
                'retry_on_timeout': True,
                'connection_class': RequestsHttpConnection
            }
            
            # Add authentication if configured
            if settings.opensearch_username and settings.opensearch_password:
                connection_config['http_auth'] = (
                    settings.opensearch_username,
                    settings.opensearch_password
                )
            
            # SSL configuration
            if settings.opensearch_use_ssl:
                connection_config['use_ssl'] = True
                connection_config['verify_certs'] = settings.opensearch_verify_certs
                if not settings.opensearch_verify_certs:
                    connection_config['ssl_show_warn'] = False
            
            self.client = OpenSearch(**connection_config)
            
            # Test connection
            info = self.client.info()
            logger.info(f"Connected to OpenSearch: {info['version']['number']}")
            
        except Exception as e:
            logger.warning(f"Failed to connect to OpenSearch: {e}")
            logger.warning("Search disabled - continuing without search")
            self.search_enabled = False
            self.client = None
    
    def search_properties(self, search_request: SearchRequest) -> Dict:
        """
        Search for properties matching criteria
        
        Args:
            search_request: Search parameters
            
        Returns:
            Search results with properties and metadata
        """
        if not self.search_enabled or not self.client:
            logger.warning("Search service not available")
            return {
                "results": [],
                "total": 0,
                "query_time_ms": 0
            }
        
        try:
            start_time = time.time()
            
            # Build OpenSearch query
            query = self._build_search_query(search_request)
            
            logger.info(f"Executing search query: {query}")
            
            # Execute search
            response = self.client.search(
                index=self.index_name,
                body=query,
                size=search_request.limit or settings.default_max_results
            )
            
            query_time = int((time.time() - start_time) * 1000)
            
            # Parse results
            results = self._parse_search_results(response)
            total = response.get('hits', {}).get('total', {})
            
            # Handle different total formats
            if isinstance(total, dict):
                total_count = total.get('value', 0)
            else:
                total_count = total
            
            logger.info(f"Search completed: {len(results)} results, {total_count} total, {query_time}ms")
            
            return {
                "results": results,
                "total": total_count,
                "query_time_ms": query_time
            }
            
        except NotFoundError:
            logger.warning(f"Index {self.index_name} not found")
            return {
                "results": [],
                "total": 0,
                "query_time_ms": 0
            }
            
        except (ConnectionError, RequestError) as e:
            logger.error(f"OpenSearch error: {e}")
            raise Exception(f"Search service unavailable: {str(e)}")
        
        except Exception as e:
            logger.error(f"Search error: {e}")
            raise Exception(f"Search failed: {str(e)}")
    
    def _build_search_query(self, search_request: SearchRequest) -> Dict:
        """
        Build OpenSearch bool query from search request
        
        Args:
            search_request: Search parameters
            
        Returns:
            OpenSearch query dictionary
        """
        must_clauses = []
        
        # Beds filter (>= requested beds)
        if search_request.beds > 0:
            must_clauses.append({
                "range": {
                    "beds": {
                        "gte": search_request.beds
                    }
                }
            })
        
        # Baths filter (>= requested baths)
        if search_request.baths > 0:
            must_clauses.append({
                "range": {
                    "baths": {
                        "gte": search_request.baths
                    }
                }
            })
        
        # City filter (exact match, lowercase)
        if search_request.city:
            must_clauses.append({
                "term": {
                    "city.keyword": search_request.city.lower()
                }
            })
        
        # Price filter (<= max price)
        if search_request.max_price > 0:
            must_clauses.append({
                "range": {
                    "price": {
                        "lte": search_request.max_price
                    }
                }
            })
        
        # Build final query
        query = {
            "query": {
                "bool": {
                    "must": must_clauses if must_clauses else [{"match_all": {}}]
                }
            },
            "sort": [
                {"price": {"order": "asc"}}  # Sort by price ascending
            ],
            "_source": [
                "id", "price", "beds", "baths", "city", "location"
            ]
        }
        
        return query
    
    def _parse_search_results(self, response: Dict) -> List[PropertyResult]:
        """
        Parse OpenSearch response into PropertyResult objects
        
        Args:
            response: OpenSearch response
            
        Returns:
            List of PropertyResult objects
        """
        results = []
        hits = response.get('hits', {}).get('hits', [])
        
        for hit in hits:
            source = hit.get('_source', {})
            
            try:
                # Extract location coordinates
                location = source.get('location', {})
                if isinstance(location, dict):
                    latitude = location.get('lat', 0.0)
                    longitude = location.get('lon', 0.0)
                elif isinstance(location, list) and len(location) >= 2:
                    longitude, latitude = location[0], location[1]
                else:
                    latitude = longitude = 0.0
                
                property_result = PropertyResult(
                    id=source.get('id', hit.get('_id')),
                    latitude=float(latitude),
                    longitude=float(longitude),
                    price=float(source.get('price', 0)),
                    beds=int(source.get('beds', 0)),
                    baths=int(source.get('baths', 0)),
                    city=source.get('city', '')
                )
                
                results.append(property_result)
                
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse search result: {e}")
                continue
        
        return results
    
    def health_check(self) -> Dict[str, any]:
        """
        Check search service health
        
        Returns:
            Health status dictionary
        """
        if not self.search_enabled or not self.client:
            return {
                "status": "disabled",
                "message": "Search service is disabled",
                "connected": False
            }
        
        try:
            start_time = time.time()
            cluster_health = self.client.cluster.health()
            response_time = (time.time() - start_time) * 1000
            
            # Check if index exists
            index_exists = self.client.indices.exists(index=self.index_name)
            
            return {
                "status": "healthy",
                "connected": True,
                "response_time_ms": round(response_time, 1),
                "cluster_status": cluster_health.get('status'),
                "number_of_nodes": cluster_health.get('number_of_nodes'),
                "index_exists": index_exists
            }
            
        except Exception as e:
            logger.error(f"Search health check failed: {e}")
            return {
                "status": "unhealthy",
                "connected": False,
                "error": str(e)
            }
    
    def create_index(self) -> bool:
        """
        Create the listings index with proper mapping
        
        Returns:
            True if successful, False otherwise
        """
        if not self.search_enabled or not self.client:
            return False
        
        mapping = {
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "price": {"type": "float"},
                    "beds": {"type": "integer"},
                    "baths": {"type": "integer"},
                    "city": {
                        "type": "text",
                        "fields": {
                            "keyword": {
                                "type": "keyword",
                                "normalizer": "lowercase"
                            }
                        }
                    },
                    "location": {"type": "geo_point"}
                }
            },
            "settings": {
                "analysis": {
                    "normalizer": {
                        "lowercase": {
                            "type": "lowercase"
                        }
                    }
                }
            }
        }
        
        try:
            # Check if index already exists
            if self.client.indices.exists(index=self.index_name):
                logger.info(f"Index {self.index_name} already exists")
                return True
            
            # Create index
            self.client.indices.create(index=self.index_name, body=mapping)
            logger.info(f"Created index {self.index_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create index: {e}")
            return False


# Global search service instance
search_service = SearchService() 