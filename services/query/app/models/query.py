"""
Query models and schemas
"""
from typing import List, Optional
from pydantic import BaseModel, Field, validator


class ParseResponse(BaseModel):
    """Response model for query parsing"""
    beds: int = Field(..., ge=0, description="Number of bedrooms")
    baths: int = Field(..., ge=0, description="Number of bathrooms")
    city: str = Field(..., min_length=1, description="City name")
    max_price: float = Field(..., gt=0, description="Maximum price")
    confidence: float = Field(..., ge=0, le=1, description="Parse confidence score")
    
    @validator('city')
    def normalize_city(cls, v):
        """Normalize city name"""
        return v.strip().title()


class SearchRequest(BaseModel):
    """Request model for property search"""
    beds: int = Field(..., ge=0, description="Minimum number of bedrooms")
    baths: int = Field(..., ge=0, description="Minimum number of bathrooms")
    city: str = Field(..., min_length=1, description="City name")
    max_price: float = Field(..., gt=0, description="Maximum price")
    limit: Optional[int] = Field(10, ge=1, le=100, description="Maximum results")
    
    @validator('city')
    def normalize_city(cls, v):
        """Normalize city name"""
        return v.strip().lower()


class PropertyResult(BaseModel):
    """Individual property result"""
    id: str = Field(..., description="Property ID")
    latitude: float = Field(..., description="Property latitude")
    longitude: float = Field(..., description="Property longitude")
    price: float = Field(..., description="Property price")
    beds: int = Field(..., description="Number of bedrooms")
    baths: int = Field(..., description="Number of bathrooms")
    city: str = Field(..., description="City name")
    
    class Config:
        schema_extra = {
            "example": {
                "id": "prop_123",
                "latitude": 39.7392,
                "longitude": -104.9903,
                "price": 450000.0,
                "beds": 3,
                "baths": 2,
                "city": "Denver"
            }
        }


class SearchResponse(BaseModel):
    """Response model for property search"""
    results: List[PropertyResult] = Field(..., description="Search results")
    total: int = Field(..., description="Total matching properties")
    query_time_ms: int = Field(..., description="Query execution time in milliseconds")
    
    class Config:
        schema_extra = {
            "example": {
                "results": [
                    {
                        "id": "prop_123",
                        "latitude": 39.7392,
                        "longitude": -104.9903,
                        "price": 450000.0,
                        "beds": 3,
                        "baths": 2,
                        "city": "Denver"
                    }
                ],
                "total": 1,
                "query_time_ms": 45
            }
        }


class ErrorResponse(BaseModel):
    """Error response model"""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Error details")
    request_id: Optional[str] = Field(None, description="Request ID for tracking")
    
    class Config:
        schema_extra = {
            "example": {
                "error": "Invalid query",
                "detail": "Query string cannot be empty",
                "request_id": "req_12345"
            }
        } 