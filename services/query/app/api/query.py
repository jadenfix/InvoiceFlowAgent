"""
Query API endpoints
"""
from fastapi import APIRouter, HTTPException, Query as QueryParam, Depends
from fastapi.responses import JSONResponse
from typing import Dict, Any

from ..core.logging import get_logger, set_request_id
from ..models.query import ParseResponse, SearchRequest, SearchResponse, ErrorResponse
from ..services.parser import QueryParser
from ..services.cache import cache_service
from ..services.search import search_service

logger = get_logger(__name__)
router = APIRouter()

# Global parser instance
query_parser = QueryParser()


@router.get("/parse", response_model=ParseResponse)
async def parse_query(
    q: str = QueryParam(..., min_length=1, max_length=500, description="Query string to parse")
) -> ParseResponse:
    """
    Parse natural language query into structured data
    
    Args:
        q: Raw query string (e.g., "3 bed 2 bath Denver under 700k")
        
    Returns:
        Parsed query with beds, baths, city, max_price, and confidence
        
    Raises:
        HTTPException: 400 for invalid input, 500 for server errors
    """
    request_id = set_request_id()
    
    try:
        # Input validation
        if not q or not q.strip():
            raise HTTPException(
                status_code=400,
                detail=ErrorResponse(
                    error="Invalid query",
                    detail="Query string cannot be empty",
                    request_id=request_id
                ).model_dump()
            )
        
        # Generate cache key
        cache_key = query_parser.generate_cache_key(q)
        
        # Check cache first
        cached_result = cache_service.get(cache_key)
        if cached_result:
            logger.info("Cache hit - returning cached parse result")
            cached_result["cache_hit"] = True
            return ParseResponse(**cached_result)
        
        # Parse query
        parsed_data, confidence = query_parser.parse_query(q)
        
        # Create response with cache_hit = False (new result)
        response = ParseResponse(**parsed_data, cache_hit=False)
        
        # Cache the result (store without cache_hit flag since it varies per request)
        cache_data = response.model_dump()
        cache_data.pop("cache_hit", None)  # Remove cache_hit before caching
        cache_service.set(cache_key, cache_data)
        
        logger.info(f"Successfully parsed query with confidence {confidence}")
        return response
        
    except ValueError as e:
        logger.warning(f"Invalid query: {e}")
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error="Invalid query",
                detail=str(e),
                request_id=request_id
            ).model_dump()
        )
        
    except Exception as e:
        logger.error(f"Parse error: {e}")
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error="Parse failed",
                detail="Internal server error",
                request_id=request_id
            ).model_dump()
        )


@router.post("/search", response_model=SearchResponse)
async def search_properties(search_request: SearchRequest) -> SearchResponse:
    """
    Search for properties matching criteria
    
    Args:
        search_request: Search parameters (beds, baths, city, max_price)
        
    Returns:
        Search results with properties and metadata
        
    Raises:
        HTTPException: 400 for invalid input, 502 for search service errors
    """
    request_id = set_request_id()
    
    try:
        logger.info(f"Search request: {search_request.model_dump()}")
        
        # Validate search request
        if not search_request.city or not search_request.city.strip():
            raise HTTPException(
                status_code=400,
                detail=ErrorResponse(
                    error="Invalid search request",
                    detail="City is required",
                    request_id=request_id
                ).model_dump()
            )
        
        if search_request.max_price <= 0:
            raise HTTPException(
                status_code=400,
                detail=ErrorResponse(
                    error="Invalid search request", 
                    detail="Max price must be greater than 0",
                    request_id=request_id
                ).model_dump()
            )
        
        # Execute search
        search_results = search_service.search_properties(search_request)
        
        # Create response
        response = SearchResponse(
            results=search_results["results"],
            total=search_results["total"],
            query_time_ms=search_results["query_time_ms"]
        )
        
        logger.info(f"Search completed: {len(response.results)} results")
        return response
        
    except HTTPException:
        # Re-raise HTTP exceptions (validation errors)
        raise
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        
        # Check if it's a search service error
        if "Search service unavailable" in str(e) or "Search failed" in str(e):
            raise HTTPException(
                status_code=502,
                detail=ErrorResponse(
                    error="Search service unavailable",
                    detail="OpenSearch service is currently unavailable",
                    request_id=request_id
                ).model_dump()
            )
        
        # Generic server error
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error="Search failed",
                detail="Internal server error", 
                request_id=request_id
            ).model_dump()
        ) 