"""
Explain API endpoints for RAG-powered invoice processing explanations
"""
from fastapi import APIRouter, HTTPException, status, Depends
from typing import List, Dict, Any, Optional
import asyncio
import os
from datetime import datetime

from ..core.config import settings
from ..core.logging import get_logger
from ..services.rag_service import RAGService, RAGError

logger = get_logger(__name__)

router = APIRouter()


def get_rag_service() -> RAGService:
    """Dependency to get RAG service instance"""
    return RAGService()


@router.get("/explain/health")
async def explain_service_health(
    rag_service: RAGService = Depends(get_rag_service)
) -> Dict[str, Any]:
    """
    Check health of explanation service components
    
    Returns:
        Health status of vector store and related services
    """
    try:
        health_status = await rag_service.health_check()
        
        return {
            "service": "explain",
            "status": "healthy" if health_status["vector_store"] else "degraded",
            "components": health_status,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error checking explain service health: {str(e)}")
        
        return {
            "service": "explain",
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


@router.post("/explain/batch")
async def explain_batch_requests(
    request_ids: List[str],
    top_k: int = 3,
    rag_service: RAGService = Depends(get_rag_service)
) -> Dict[str, Any]:
    """
    Get explanations for multiple invoice requests in batch
    
    Args:
        request_ids: List of invoice request IDs
        top_k: Number of explanations per request
        
    Returns:
        Dictionary with explanations for each valid request_id
    """
    if len(request_ids) > 50:  # Reasonable batch limit
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Batch size limited to 50 requests"
        )
    
    try:
        start_time = datetime.utcnow()
        
        logger.info(f"Processing batch explain request for {len(request_ids)} requests")
        
        # Process requests concurrently
        tasks = [
            rag_service.get_explanations(request_id, top_k)
            for request_id in request_ids
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Compile results
        batch_results = {}
        successful_count = 0
        error_count = 0
        
        for request_id, result in zip(request_ids, results):
            if isinstance(result, Exception):
                batch_results[request_id] = {
                    "status": "error",
                    "error": str(result)
                }
                error_count += 1
            elif result is None:
                batch_results[request_id] = {
                    "status": "not_found",
                    "explanations": []
                }
            else:
                batch_results[request_id] = {
                    "status": "success",
                    "explanations": result
                }
                successful_count += 1
        
        query_time = (datetime.utcnow() - start_time).total_seconds()
        
        logger.info(f"Batch explain completed: {successful_count} successful, {error_count} errors, {query_time:.3f}s")
        
        return {
            "results": batch_results,
            "summary": {
                "total_requests": len(request_ids),
                "successful": successful_count,
                "errors": error_count,
                "query_time": query_time
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in batch explain request ({len(request_ids)} requests): {str(e)}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing batch explanation request"
        )


@router.get("/explain/{request_id}/categories")
async def get_explanation_categories(
    request_id: str,
    rag_service: RAGService = Depends(get_rag_service)
) -> Dict[str, Any]:
    """
    Get available explanation categories for a specific invoice
    
    Args:
        request_id: The invoice request ID
        
    Returns:
        Dictionary containing available categories and their descriptions
    """
    try:
        categories = await rag_service.get_available_categories(request_id)
        
        return {
            "request_id": request_id,
            "categories": categories,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting explanation categories for {request_id}: {str(e)}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving explanation categories"
        )


@router.get("/explain/{request_id}")
async def explain_processing_decision(
    request_id: str,
    top_k: int = 3,
    rag_service: RAGService = Depends(get_rag_service)
) -> Dict[str, Any]:
    """
    Get AI-powered explanations for invoice processing decisions
    
    Args:
        request_id: The invoice request ID to explain
        top_k: Number of explanation documents to return (default: 3)
        
    Returns:
        Dictionary containing:
        - request_id: The invoice ID
        - explanations: List of relevant explanation documents
        - query_time: Time taken for the query
        - status: Success/error status
        
    Raises:
        404: If request_id not found
        204: If no explanations found
        502: If vector store is unavailable
    """
    start_time = datetime.utcnow()
    
    try:
        logger.info(f"Processing explain request for {request_id} with top_k={top_k}")
        
        # Get explanations from RAG service
        explanations = await rag_service.get_explanations(
            request_id=request_id,
            top_k=top_k
        )
        
        query_time = (datetime.utcnow() - start_time).total_seconds()
        
        # Handle different response scenarios
        if explanations is None:
            # Invoice not found
            logger.warning(f"Invoice not found for explain request: {request_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Invoice with request_id '{request_id}' not found"
            )
        
        if len(explanations) == 0:
            # No explanations found
            logger.info(f"No explanations found for {request_id}")
            raise HTTPException(
                status_code=status.HTTP_204_NO_CONTENT,
                detail="No explanations found for this invoice"
            )
        
        # Success - return explanations
        response = {
            "request_id": request_id,
            "explanations": explanations,
            "query_time": query_time,
            "status": "success",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Explain request completed for {request_id}: {len(explanations)} explanations, {query_time:.3f}s")
        
        return response
        
    except HTTPException:
        # Re-raise HTTP exceptions (404, 204)
        raise
        
    except RAGError as e:
        # Vector store connectivity issues
        logger.error(f"RAG service error for {request_id}: {str(e)}")
        
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Explanation service temporarily unavailable. Please try again later."
        )
        
    except Exception as e:
        # Unexpected errors
        logger.error(f"Unexpected error in explain endpoint for {request_id}: {str(e)}", exc_info=True)
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error occurred while processing explanation request"
        ) 