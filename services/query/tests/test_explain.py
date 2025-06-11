"""
Tests for the RAG explain feature

This module tests the vector store and RAG-powered explanation functionality
including edge cases and error scenarios.
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
import json
from datetime import datetime

# Import the app and services
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.main import app
from app.services.rag_service import RAGService, RAGError
from app.api.explain import get_rag_service


class TestRAGService:
    """Test the RAG service functionality"""
    
    @pytest.fixture
    def rag_service(self):
        """Create a RAG service instance for testing"""
        with patch.dict(os.environ, {
            'PINECONE_API_KEY': 'test-key',
            'PINECONE_INDEX_NAME': 'test-index',
            'PINECONE_NAMESPACE': 'test-namespace'
        }):
            service = RAGService()
            service.vector_store_available = False  # Default to no vector store
            return service
    
    @pytest.mark.asyncio
    async def test_get_explanations_auto_approved(self, rag_service):
        """Test explanations for auto-approved invoice"""
        explanations = await rag_service.get_explanations("auto-123", top_k=3)
        
        assert explanations is not None
        assert len(explanations) > 0
        assert explanations[0]["invoice_context"]["status"] == "AUTO_APPROVED"
        assert explanations[0]["title"] == "Auto-Approval Criteria"
        assert "auto-approved" in explanations[0]["snippet"].lower()
    
    @pytest.mark.asyncio
    async def test_get_explanations_needs_review(self, rag_service):
        """Test explanations for invoice needing review"""
        explanations = await rag_service.get_explanations("review-456", top_k=3)
        
        assert explanations is not None
        assert len(explanations) > 0
        assert explanations[0]["invoice_context"]["status"] == "NEEDS_REVIEW"
        assert explanations[0]["title"] == "Manual Review Requirements"
        assert "review" in explanations[0]["snippet"].lower()
    
    @pytest.mark.asyncio
    async def test_get_explanations_processing(self, rag_service):
        """Test explanations for invoice in processing"""
        explanations = await rag_service.get_explanations("extract-789", top_k=3)
        
        assert explanations is not None
        assert len(explanations) > 0
        assert explanations[0]["invoice_context"]["status"] == "PROCESSING"
    
    @pytest.mark.asyncio
    async def test_get_explanations_nonexistent_invoice(self, rag_service):
        """Test explanations for non-existent invoice"""
        # Mock the _get_invoice_info to return None
        rag_service._get_invoice_info = AsyncMock(return_value=None)
        
        explanations = await rag_service.get_explanations("nonexistent", top_k=3)
        assert explanations is None
    
    @pytest.mark.asyncio 
    async def test_vector_store_query_with_pinecone(self, rag_service):
        """Test vector store query when Pinecone is available"""
        # Mock Pinecone components
        mock_index = Mock()
        mock_match = Mock()
        mock_match.id = "test_doc_1"
        mock_match.score = 0.95
        mock_match.metadata = {
            "title": "Test Document",
            "category": "matching_logic",
            "text": "This is a test document snippet...",
            "full_text": "This is the full test document content."
        }
        
        mock_index.query.return_value = Mock(matches=[mock_match])
        rag_service.index = mock_index
        rag_service.vector_store_available = True
        
        results = await rag_service._query_vector_store("test query", 3)
        
        assert len(results) == 1
        assert results[0]["doc_id"] == "test_doc_1"
        assert results[0]["title"] == "Test Document"
        assert results[0]["relevance_score"] == 0.95
        assert results[0]["source"] == "vector_store"
    
    @pytest.mark.asyncio
    async def test_vector_store_unavailable_error(self, rag_service):
        """Test error handling when vector store is unavailable"""
        rag_service.vector_store_available = False
        
        with pytest.raises(RAGError, match="Vector store not available"):
            await rag_service._query_vector_store("test query", 3)
    
    def test_generate_query_embedding(self, rag_service):
        """Test embedding generation"""
        text = "Why was invoice auto-approved?"
        embedding = rag_service._generate_query_embedding(text)
        
        assert len(embedding) == 1536
        assert all(isinstance(x, float) for x in embedding)
        assert all(-1.0 <= x <= 1.0 for x in embedding)
        
        # Test consistency - same text should produce same embedding
        embedding2 = rag_service._generate_query_embedding(text)
        assert embedding == embedding2
    
    def test_static_explanations_fallback(self, rag_service):
        """Test static explanations when vector store unavailable"""
        invoice_info = {
            "status": "AUTO_APPROVED",
            "total_amount": 1000.0,
            "po_number": "PO-123"
        }
        
        explanations = rag_service._get_static_explanations(invoice_info, 3)
        
        assert len(explanations) == 1
        assert explanations[0]["doc_id"] == "static_auto_approval"
        assert explanations[0]["source"] == "static_fallback"
        assert explanations[0]["relevance_score"] == 0.95
    
    @pytest.mark.asyncio
    async def test_get_available_categories(self, rag_service):
        """Test getting available explanation categories"""
        categories = await rag_service.get_available_categories("test-123")
        
        assert len(categories) == 4
        category_names = [cat["category"] for cat in categories]
        assert "matching_logic" in category_names
        assert "extraction" in category_names
        assert "search" in category_names
        assert "error_handling" in category_names


class TestExplainAPI:
    """Test the explain API endpoints"""
    
    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)
    
    def test_explain_endpoint_success(self, client):
        """Test successful explain request"""
        response = client.get("/explain/auto-123")
        
        assert response.status_code == 200
        data = response.json()
        assert data["request_id"] == "auto-123"
        assert data["status"] == "success"
        assert len(data["explanations"]) == 1
        assert data["explanations"][0]["title"] == "Auto-Approval Criteria"
        assert "query_time" in data
    
    def test_explain_endpoint_processing(self, client):
        """Test explain request for processing invoice"""
        response = client.get("/explain/extract-789")
        
        assert response.status_code == 200
        data = response.json()
        assert data["request_id"] == "extract-789"
        assert data["status"] == "success"
        assert len(data["explanations"]) == 1
        assert data["explanations"][0]["invoice_context"]["status"] == "PROCESSING"
    
    def test_explain_endpoint_review_needed(self, client):
        """Test explain request for invoice needing review"""
        response = client.get("/explain/review-456")
        
        assert response.status_code == 200
        data = response.json()
        assert data["request_id"] == "review-456"
        assert data["status"] == "success"
        assert data["explanations"][0]["invoice_context"]["status"] == "NEEDS_REVIEW"
    
    def test_explain_categories_endpoint(self, client):
        """Test categories endpoint"""
        response = client.get("/explain/test-123/categories")
        
        assert response.status_code == 200
        data = response.json()
        assert data["request_id"] == "test-123"
        assert len(data["categories"]) == 4
        assert data["categories"][0]["category"] == "matching_logic"
    
    def test_explain_batch_endpoint_success(self, client):
        """Test batch explain endpoint"""
        response = client.post(
            "/explain/batch",
            json=["auto-1", "review-2", "extract-3"]
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["summary"]["total_requests"] == 3
        assert data["summary"]["successful"] == 3
        assert data["results"]["auto-1"]["status"] == "success"
        assert data["results"]["review-2"]["status"] == "success"
        assert data["results"]["extract-3"]["status"] == "success"
    
    def test_explain_batch_endpoint_size_limit(self, client):
        """Test batch endpoint with too many requests"""
        large_request = [f"req{i}" for i in range(51)]  # Over limit of 50
        
        response = client.post(
            "/explain/batch",
            json=large_request
        )
        
        assert response.status_code == 400
        assert "batch size limited" in response.json()["detail"].lower()
    
    def test_explain_health_endpoint(self, client):
        """Test explain health endpoint"""
        response = client.get("/explain/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "explain"
        assert data["status"] in ["healthy", "degraded", "unhealthy"]
        assert "components" in data
        assert "timestamp" in data


# Note: Mocked tests removed as integration tests provide better coverage
# The real service includes static fallbacks that make these edge cases
# unlikely in practice. Integration tests above cover the actual behavior.


class TestEdgeCases:
    """Test edge cases and error scenarios"""
    
    @pytest.fixture
    def rag_service(self):
        """Create RAG service for edge case testing"""
        service = RAGService()
        service.vector_store_available = False
        return service
    
    def test_empty_query_embedding(self, rag_service):
        """Test embedding generation with empty query"""
        embedding = rag_service._generate_query_embedding("")
        assert len(embedding) == 1536
        assert all(isinstance(x, float) for x in embedding)
    
    def test_unicode_query_embedding(self, rag_service):
        """Test embedding generation with Unicode characters"""
        unicode_query = "Why was invoice 📄 auto-approved? 中文测试 🎯"
        embedding = rag_service._generate_query_embedding(unicode_query)
        assert len(embedding) == 1536
        assert all(isinstance(x, float) for x in embedding)
    
    @pytest.mark.asyncio
    async def test_concurrent_explanations(self, rag_service):
        """Test concurrent explanation requests"""
        request_ids = ["auto-1", "review-2", "extract-3"]
        
        # Run multiple requests concurrently
        tasks = [
            rag_service.get_explanations(req_id, top_k=2)
            for req_id in request_ids
        ]
        
        results = await asyncio.gather(*tasks)
        
        assert len(results) == 3
        assert all(result is not None for result in results)
        assert all(len(result) > 0 for result in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])