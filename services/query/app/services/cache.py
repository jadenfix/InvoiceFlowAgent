"""
Redis cache service for query results
"""
import json
import time
from typing import Dict, Optional
import redis
from redis.exceptions import RedisError, ConnectionError, TimeoutError

from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger(__name__)


class CacheService:
    """Redis cache service"""
    
    def __init__(self):
        """Initialize Redis connection"""
        self.redis_client = None
        self.cache_enabled = True
        self._connect()
    
    def _connect(self) -> None:
        """Connect to Redis with error handling"""
        try:
            self.redis_client = redis.from_url(
                settings.redis_url,
                password=settings.redis_password,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
            
            # Test connection
            self.redis_client.ping()
            logger.info("Connected to Redis successfully")
            
        except (ConnectionError, TimeoutError, RedisError) as e:
            logger.warning(f"Failed to connect to Redis: {e}")
            logger.warning("Cache disabled - continuing without cache")
            self.cache_enabled = False
            self.redis_client = None
    
    def get(self, key: str) -> Optional[Dict]:
        """
        Get cached value by key
        
        Args:
            key: Cache key
            
        Returns:
            Cached data or None if not found/error
        """
        if not self.cache_enabled or not self.redis_client:
            return None
        
        try:
            start_time = time.time()
            cached_data = self.redis_client.get(key)
            
            if cached_data:
                result = json.loads(cached_data)
                cache_time = (time.time() - start_time) * 1000
                logger.info(f"Cache hit for key {key[:8]}... (retrieved in {cache_time:.1f}ms)")
                return result
            
            logger.debug(f"Cache miss for key {key[:8]}...")
            return None
            
        except (RedisError, json.JSONDecodeError) as e:
            logger.warning(f"Cache get error for key {key[:8]}...: {e}")
            return None
    
    def set(self, key: str, value: Dict, ttl: Optional[int] = None) -> bool:
        """
        Set cached value with TTL
        
        Args:
            key: Cache key
            value: Data to cache
            ttl: Time to live in seconds (uses default if None)
            
        Returns:
            True if successfully cached, False otherwise
        """
        if not self.cache_enabled or not self.redis_client:
            return False
        
        try:
            ttl = ttl or settings.cache_ttl
            serialized_value = json.dumps(value, default=str)
            
            result = self.redis_client.setex(
                key, 
                ttl, 
                serialized_value
            )
            
            if result:
                logger.debug(f"Cached key {key[:8]}... with TTL {ttl}s")
                return True
            
        except (RedisError, TypeError) as e:
            logger.warning(f"Cache set error for key {key[:8]}...: {e}")
        
        return False
    
    def delete(self, key: str) -> bool:
        """
        Delete cached value
        
        Args:
            key: Cache key to delete
            
        Returns:
            True if successfully deleted, False otherwise
        """
        if not self.cache_enabled or not self.redis_client:
            return False
        
        try:
            result = self.redis_client.delete(key)
            if result:
                logger.debug(f"Deleted cache key {key[:8]}...")
                return True
                
        except RedisError as e:
            logger.warning(f"Cache delete error for key {key[:8]}...: {e}")
        
        return False
    
    def health_check(self) -> Dict[str, any]:
        """
        Check cache health status
        
        Returns:
            Health status dictionary
        """
        if not self.cache_enabled or not self.redis_client:
            return {
                "status": "disabled",
                "message": "Cache is disabled",
                "connected": False
            }
        
        try:
            start_time = time.time()
            self.redis_client.ping()
            response_time = (time.time() - start_time) * 1000
            
            info = self.redis_client.info()
            
            return {
                "status": "healthy",
                "connected": True,
                "response_time_ms": round(response_time, 1),
                "memory_usage": info.get('used_memory_human'),
                "connected_clients": info.get('connected_clients'),
                "uptime_seconds": info.get('uptime_in_seconds')
            }
            
        except RedisError as e:
            logger.error(f"Cache health check failed: {e}")
            return {
                "status": "unhealthy", 
                "connected": False,
                "error": str(e)
            }
    
    def clear_all(self) -> bool:
        """
        Clear all cached data (for testing)
        
        Returns:
            True if successful, False otherwise
        """
        if not self.cache_enabled or not self.redis_client:
            return False
        
        try:
            self.redis_client.flushdb()
            logger.info("Cleared all cache data")
            return True
            
        except RedisError as e:
            logger.error(f"Failed to clear cache: {e}")
            return False


# Global cache instance
cache_service = CacheService() 