"""
RAG (Retrieval-Augmented Generation) service for invoice processing explanations

This service handles querying the vector store for relevant explanation documents
based on invoice processing context and status.
"""
import os
import asyncio
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime
import json

try:
    import pinecone
    from pinecone import Pinecone
except ImportError:
    pinecone = None

import structlog
from ..core.config import settings

logger = structlog.get_logger(__name__)


class RAGError(Exception):
    """Custom exception for RAG service errors"""
    pass


class RAGService:
    """Service for handling RAG-powered explanations"""
    
    def __init__(self):
        """Initialize RAG service"""
        self.pinecone_api_key = os.getenv("PINECONE_API_KEY")
        self.index_name = os.getenv("PINECONE_INDEX_NAME", "invoice-docs")
        self.namespace = os.getenv("PINECONE_NAMESPACE", "explanation_docs")
        self.vector_dimension = 1536
        
        # Initialize Pinecone client if available
        if self.pinecone_api_key and pinecone:
            try:
                self.pc = Pinecone(api_key=self.pinecone_api_key)
                self.index = self.pc.Index(self.index_name)
                self.vector_store_available = True
                logger.info("RAG service initialized with vector store")
            except Exception as e:
                self.vector_store_available = False
                logger.warning("Vector store unavailable", error=str(e))
        else:
            self.vector_store_available = False
            logger.warning("Vector store not configured - explanations will be limited")
    
    async def get_explanations(
        self, 
        request_id: str, 
        top_k: int = 3
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get explanations for an invoice processing decision
        
        Args:
            request_id: Invoice request ID
            top_k: Number of explanation documents to return
            
        Returns:
            List of explanation documents or None if invoice not found
            
        Raises:
            RAGError: If vector store is unavailable
        """
        try:
            # Get invoice information from database
            invoice_info = await self._get_invoice_info(request_id)
            if not invoice_info:
                return None  # Invoice not found
            
            # Construct semantic query based on invoice context
            query_text = self._construct_explanation_query(invoice_info)
            
            logger.info("Generating explanations", 
                       request_id=request_id, 
                       query=query_text)
            
            # Get relevant documents from vector store
            if self.vector_store_available:
                explanations = await self._query_vector_store(query_text, top_k)
            else:
                # Fallback to static explanations
                explanations = self._get_static_explanations(invoice_info, top_k)
            
            # Enhance explanations with invoice-specific context
            enhanced_explanations = self._enhance_explanations(explanations, invoice_info)
            
            logger.info("Explanations generated", 
                       request_id=request_id, 
                       count=len(enhanced_explanations))
            
            return enhanced_explanations
            
        except Exception as e:
            logger.error("Error generating explanations", 
                        request_id=request_id, 
                        error=str(e))
            raise RAGError(f"Failed to generate explanations: {str(e)}")
    
    async def _get_invoice_info(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Get invoice information from database"""
        try:
            # This would connect to the actual invoice database
            # For now, simulate invoice data based on request_id patterns
            
            # Simulate different invoice types for demonstration
            if "auto" in request_id.lower():
                return {
                    "request_id": request_id,
                    "status": "AUTO_APPROVED",
                    "total_amount": 1250.00,
                    "po_number": "PO-2024-001",
                    "vendor_name": "ACME Corp",
                    "processing_date": "2024-01-15",
                    "confidence_score": 0.95,
                    "extracted_fields": {
                        "amount_variance": 0.8,  # 0.8% variance
                        "vendor_match_score": 0.92,
                        "po_exists": True
                    }
                }
            elif "review" in request_id.lower():
                return {
                    "request_id": request_id,
                    "status": "NEEDS_REVIEW",
                    "total_amount": 2800.00,
                    "po_number": None,
                    "vendor_name": "Unknown Vendor LLC",
                    "processing_date": "2024-01-15",
                    "confidence_score": 0.45,
                    "extracted_fields": {
                        "amount_variance": None,
                        "vendor_match_score": 0.12,
                        "po_exists": False
                    }
                }
            elif "extract" in request_id.lower():
                return {
                    "request_id": request_id,
                    "status": "PROCESSING",
                    "total_amount": 890.50,
                    "po_number": "PO-2024-025",
                    "vendor_name": "TechSupply Inc",
                    "processing_date": "2024-01-15",
                    "confidence_score": 0.88,
                    "extracted_fields": {
                        "ocr_confidence": 0.94,
                        "field_extraction_confidence": 0.82
                    }
                }
            else:
                # Default case
                return {
                    "request_id": request_id,
                    "status": "COMPLETED",
                    "total_amount": 1500.00,
                    "po_number": "PO-2024-010",
                    "vendor_name": "Sample Vendor",
                    "processing_date": "2024-01-15",
                    "confidence_score": 0.85
                }
                
        except Exception as e:
            logger.error("Error fetching invoice info", 
                        request_id=request_id, 
                        error=str(e))
            return None
    
    def _construct_explanation_query(self, invoice_info: Dict[str, Any]) -> str:
        """Construct semantic query based on invoice context"""
        status = invoice_info.get("status", "")
        
        if status == "AUTO_APPROVED":
            return "Why was invoice automatically approved? Auto-approval rules and criteria"
        elif status == "NEEDS_REVIEW":
            return "Why does invoice need manual review? Review requirements and validation"
        elif status == "PROCESSING":
            return "How does invoice data extraction work? OCR and field extraction process"
        else:
            return "Invoice processing workflow and decision logic"
    
    async def _query_vector_store(
        self, 
        query_text: str, 
        top_k: int
    ) -> List[Dict[str, Any]]:
        """Query vector store for relevant documents"""
        if not self.vector_store_available:
            raise RAGError("Vector store not available")
        
        try:
            # Generate query embedding (using same hash approach as embed_docs.py)
            query_embedding = self._generate_query_embedding(query_text)
            
            # Query Pinecone
            search_results = self.index.query(
                vector=query_embedding,
                namespace=self.namespace,
                top_k=top_k,
                include_metadata=True
            )
            
            # Process results
            explanations = []
            for match in search_results.matches:
                explanation = {
                    "doc_id": match.id,
                    "title": match.metadata.get("title", ""),
                    "category": match.metadata.get("category", ""),
                    "snippet": match.metadata.get("text", "")[:300] + "...",
                    "full_text": match.metadata.get("full_text", ""),
                    "relevance_score": float(match.score),
                    "source": "vector_store"
                }
                explanations.append(explanation)
            
            return explanations
            
        except Exception as e:
            logger.error("Vector store query failed", error=str(e))
            raise RAGError(f"Vector store query failed: {str(e)}")
    
    def _generate_query_embedding(self, text: str) -> List[float]:
        """Generate embedding for query text (demo implementation)"""
        # Same approach as in embed_docs.py for consistency
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        
        embedding = []
        for i in range(0, min(len(text_hash), self.vector_dimension * 2), 2):
            hex_val = text_hash[i:i+2]
            float_val = (int(hex_val, 16) - 128) / 128.0
            embedding.append(float_val)
        
        # Pad or truncate to exact dimension
        while len(embedding) < self.vector_dimension:
            embedding.append(0.0)
        embedding = embedding[:self.vector_dimension]
        
        return embedding
    
    def _get_static_explanations(
        self, 
        invoice_info: Dict[str, Any], 
        top_k: int
    ) -> List[Dict[str, Any]]:
        """Fallback to static explanations when vector store unavailable"""
        status = invoice_info.get("status", "")
        
        static_explanations = {
            "AUTO_APPROVED": [
                {
                    "doc_id": "static_auto_approval",
                    "title": "Auto-Approval Criteria",
                    "category": "matching_logic",
                    "snippet": "Invoice was auto-approved because it met all validation criteria: valid PO number, amount within 2% tolerance, vendor match, and valid dates.",
                    "full_text": "Auto-approval occurs when invoices pass all validation checks without requiring manual review.",
                    "relevance_score": 0.95,
                    "source": "static_fallback"
                }
            ],
            "NEEDS_REVIEW": [
                {
                    "doc_id": "static_review_required",
                    "title": "Manual Review Requirements", 
                    "category": "matching_logic",
                    "snippet": "Invoice requires manual review due to missing PO number, amount variance, or vendor mismatch.",
                    "full_text": "Manual review is triggered when invoices fail validation checks or contain suspicious data.",
                    "relevance_score": 0.90,
                    "source": "static_fallback"
                }
            ]
        }
        
        explanations = static_explanations.get(status, [
            {
                "doc_id": "static_general",
                "title": "Invoice Processing Overview",
                "category": "general",
                "snippet": "Invoice undergoes OCR extraction, field validation, and PO matching before approval.",
                "full_text": "Standard invoice processing workflow includes multiple validation stages.",
                "relevance_score": 0.80,
                "source": "static_fallback"
            }
        ])
        
        return explanations[:top_k]
    
    def _enhance_explanations(
        self, 
        explanations: List[Dict[str, Any]], 
        invoice_info: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Enhance explanations with invoice-specific context"""
        enhanced = []
        
        for explanation in explanations:
            enhanced_explanation = explanation.copy()
            
            # Add invoice-specific context
            context = self._generate_invoice_context(invoice_info, explanation)
            enhanced_explanation["invoice_context"] = context
            
            # Add confidence indicators
            enhanced_explanation["confidence"] = self._calculate_explanation_confidence(
                explanation, invoice_info
            )
            
            enhanced.append(enhanced_explanation)
        
        return enhanced
    
    def _generate_invoice_context(
        self, 
        invoice_info: Dict[str, Any], 
        explanation: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate invoice-specific context for explanation"""
        context = {
            "invoice_amount": invoice_info.get("total_amount"),
            "po_number": invoice_info.get("po_number"),
            "vendor": invoice_info.get("vendor_name"),
            "status": invoice_info.get("status"),
            "processing_date": invoice_info.get("processing_date")
        }
        
        # Add specific details based on explanation category
        category = explanation.get("category", "")
        
        if category == "matching_logic" and invoice_info.get("extracted_fields"):
            fields = invoice_info["extracted_fields"]
            context["amount_variance"] = fields.get("amount_variance")
            context["vendor_match_score"] = fields.get("vendor_match_score")
            context["po_exists"] = fields.get("po_exists")
        
        return context
    
    def _calculate_explanation_confidence(
        self, 
        explanation: Dict[str, Any], 
        invoice_info: Dict[str, Any]
    ) -> float:
        """Calculate confidence score for explanation relevance"""
        base_score = explanation.get("relevance_score", 0.5)
        
        # Boost confidence if explanation category matches invoice status
        status = invoice_info.get("status", "")
        category = explanation.get("category", "")
        
        if (status == "AUTO_APPROVED" and category == "matching_logic") or \
           (status == "NEEDS_REVIEW" and category == "matching_logic") or \
           (status == "PROCESSING" and category == "extraction"):
            base_score = min(base_score + 0.1, 1.0)
        
        return round(base_score, 3)
    
    async def get_available_categories(self, request_id: str) -> List[Dict[str, Any]]:
        """Get available explanation categories for an invoice"""
        categories = [
            {
                "category": "matching_logic",
                "title": "PO Matching & Approval",
                "description": "Rules for automatic approval and manual review triggers"
            },
            {
                "category": "extraction",
                "title": "Data Extraction",
                "description": "OCR and AI field extraction processes"
            },
            {
                "category": "search",
                "title": "Search & Ranking",
                "description": "How invoices are ranked and searched"
            },
            {
                "category": "error_handling",
                "title": "Error Handling",
                "description": "How the system handles processing errors"
            }
        ]
        
        return categories
    
    async def health_check(self) -> Dict[str, Any]:
        """Check health of RAG service components"""
        health_status = {
            "vector_store": False,
            "database": False,
            "embedding_service": False
        }
        
        # Check vector store
        if self.vector_store_available:
            try:
                stats = self.index.describe_index_stats()
                health_status["vector_store"] = True
                health_status["vector_count"] = stats.total_vector_count
            except Exception as e:
                logger.error("Vector store health check failed", error=str(e))
        
        # Check embedding service (always available in demo)
        health_status["embedding_service"] = True
        
        # Check database (simulate)
        health_status["database"] = True
        
        return health_status 