#!/usr/bin/env python3
"""
Document Embedding Pipeline for Invoice Processing Explanations

This script embeds documentation and explanation texts into Pinecone vector database
for use in the RAG-powered explain feature.
"""

import os
import json
import time
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
import hashlib

try:
    import pinecone
    from pinecone import Pinecone, PodSpec
except ImportError:
    print("ERROR: pinecone-client not installed. Run: pip install pinecone-client")
    exit(1)

try:
    import anthropic
except ImportError:
    print("ERROR: anthropic not installed. Run: pip install anthropic")
    exit(1)

import structlog


# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


class DocumentEmbedder:
    """Service for embedding documents into Pinecone vector database"""
    
    def __init__(self):
        """Initialize embedding service with API clients"""
        # Pinecone configuration
        self.pinecone_api_key = os.getenv("PINECONE_API_KEY")
        self.pinecone_env = os.getenv("PINECONE_ENV", "gcp-starter")
        self.index_name = os.getenv("PINECONE_INDEX_NAME", "invoice-docs")
        self.namespace = os.getenv("PINECONE_NAMESPACE", "explanation_docs")
        
        # Anthropic configuration
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        
        if not self.pinecone_api_key:
            raise ValueError("PINECONE_API_KEY environment variable required")
        if not self.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable required")
        
        # Initialize clients
        self.pc = Pinecone(api_key=self.pinecone_api_key)
        self.anthropic_client = anthropic.Anthropic(api_key=self.anthropic_api_key)
        
        # Vector configuration
        self.vector_dimension = 1536  # Standard for text embeddings
        self.batch_size = 100
        
        logger.info("DocumentEmbedder initialized", 
                   index_name=self.index_name, 
                   namespace=self.namespace)
    
    async def setup_pinecone_index(self) -> bool:
        """Create Pinecone index if it doesn't exist"""
        try:
            # Check if index exists
            existing_indexes = self.pc.list_indexes()
            index_names = [idx.name for idx in existing_indexes.indexes]
            
            if self.index_name not in index_names:
                logger.info("Creating Pinecone index", index_name=self.index_name)
                
                self.pc.create_index(
                    name=self.index_name,
                    dimension=self.vector_dimension,
                    metric="cosine",
                    spec=PodSpec(
                        environment=self.pinecone_env,
                        pod_type="p1.x1"
                    )
                )
                
                # Wait for index to be ready
                logger.info("Waiting for index to be ready...")
                time.sleep(30)
            
            # Connect to index
            self.index = self.pc.Index(self.index_name)
            
            # Get index stats
            stats = self.index.describe_index_stats()
            logger.info("Connected to Pinecone index", 
                       index_name=self.index_name,
                       total_vectors=stats.total_vector_count)
            
            return True
            
        except Exception as e:
            logger.error("Failed to setup Pinecone index", error=str(e))
            return False
    
    def get_explanation_documents(self) -> List[Dict[str, Any]]:
        """Get documents to embed for explanations"""
        
        # Static explanation documents
        documents = [
            {
                "doc_id": "matching_rules_001",
                "title": "Invoice Auto-Approval Rules",
                "category": "matching_logic",
                "text": """
                Invoices are automatically approved when they meet these criteria:
                1. Valid PO Number: Invoice must contain a valid purchase order number that exists in our system
                2. Amount Tolerance: Invoice amount must be within 2% of the purchase order amount
                3. Vendor Match: Vendor name should match or be similar to the PO vendor
                4. Date Validity: Invoice date should be after the PO date and not in the future
                
                When these conditions are met, the invoice status is set to AUTO_APPROVED and no manual review is required.
                """.strip()
            },
            {
                "doc_id": "matching_rules_002", 
                "title": "Invoice Review Requirements",
                "category": "matching_logic",
                "text": """
                Invoices require manual review (NEEDS_REVIEW status) in these cases:
                1. No PO Number: Invoice doesn't contain a recognizable purchase order number
                2. PO Not Found: The PO number doesn't exist in our purchase order database
                3. Amount Variance: Invoice amount differs from PO amount by more than 2%
                4. Duplicate Invoice: Invoice number has already been processed for this PO
                5. Vendor Mismatch: Vendor name significantly differs from PO vendor
                6. Date Issues: Invoice date is before PO date or suspiciously in the future
                
                These cases indicate potential errors or fraud and require human verification.
                """.strip()
            },
            {
                "doc_id": "extraction_process_001",
                "title": "Invoice Data Extraction Process", 
                "category": "extraction",
                "text": """
                Our invoice extraction process uses a two-stage approach:
                
                Stage 1 - OCR Text Extraction:
                - Convert PDF to text using OCR technology
                - Extract raw text content with confidence scores
                - Identify text blocks and regions
                
                Stage 2 - AI Field Extraction:
                - Use AI to identify key fields: total amount, PO numbers, vendor name, invoice number, due date
                - Apply business rules to validate extracted data
                - Generate confidence scores for each extracted field
                
                This dual approach ensures high accuracy while maintaining processing speed.
                """.strip()
            },
            {
                "doc_id": "search_ranking_001",
                "title": "Invoice Search and Ranking",
                "category": "search",
                "text": """
                Invoice search results are ranked based on multiple factors:
                
                1. Relevance Score: How well the invoice matches the search criteria
                2. Processing Status: Completed invoices rank higher than pending ones
                3. Date Recency: More recent invoices get slight boost in ranking
                4. Confidence Score: Invoices with higher extraction confidence rank better
                5. Exact Matches: Perfect matches for PO numbers or vendor names rank highest
                
                The search algorithm uses both lexical matching and semantic similarity to find relevant invoices.
                """.strip()
            },
            {
                "doc_id": "error_handling_001",
                "title": "Invoice Processing Error Handling",
                "category": "error_handling", 
                "text": """
                When invoice processing encounters errors, the system follows these protocols:
                
                1. OCR Failures: If text extraction fails, retry with different OCR settings
                2. AI Extraction Errors: Fall back to rule-based extraction for critical fields
                3. Database Errors: Use transaction rollback and retry with exponential backoff
                4. Network Issues: Queue invoices for retry and notify administrators
                5. File Corruption: Quarantine corrupt files and alert users
                
                All errors are logged with detailed context for debugging and monitoring.
                """.strip()
            },
            {
                "doc_id": "amount_tolerance_001",
                "title": "PO Amount Matching Tolerance Explained",
                "category": "matching_logic",
                "text": """
                The 2% amount tolerance for PO matching exists for practical business reasons:
                
                1. Tax Variations: Different tax rates or tax-inclusive vs tax-exclusive amounts
                2. Shipping Costs: Small shipping charges added to the base PO amount
                3. Rounding Differences: Currency rounding in international transactions
                4. Discount Applications: Early payment discounts or volume discounts
                5. Currency Fluctuations: Exchange rate changes for foreign currency invoices
                
                This tolerance balances automation efficiency with fraud protection.
                """.strip()
            }
        ]
        
        logger.info("Loaded explanation documents", count=len(documents))
        return documents
    
    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using hash-based approach (demo implementation)"""
        embeddings = []
        
        for text in texts:
            try:
                # Note: In production, use OpenAI's embedding API or similar
                # This is a deterministic demo implementation
                text_hash = hashlib.sha256(text.encode()).hexdigest()
                
                # Convert hash to float values (normalized to [-1, 1])
                embedding = []
                for i in range(0, min(len(text_hash), self.vector_dimension * 2), 2):
                    hex_val = text_hash[i:i+2]
                    float_val = (int(hex_val, 16) - 128) / 128.0
                    embedding.append(float_val)
                
                # Pad or truncate to exact dimension
                while len(embedding) < self.vector_dimension:
                    embedding.append(0.0)
                embedding = embedding[:self.vector_dimension]
                
                embeddings.append(embedding)
                
                # Rate limiting
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error("Failed to generate embedding", text_preview=text[:100], error=str(e))
                embeddings.append([0.0] * self.vector_dimension)
        
        logger.info("Generated embeddings", count=len(embeddings))
        return embeddings
    
    async def upsert_documents(self, documents: List[Dict[str, Any]]) -> bool:
        """Upsert documents into Pinecone"""
        try:
            texts = [doc["text"] for doc in documents]
            
            logger.info("Generating embeddings for documents...")
            embeddings = await self.generate_embeddings(texts)
            
            upsert_data = []
            for doc, embedding in zip(documents, embeddings):
                vector_data = {
                    "id": doc["doc_id"],
                    "values": embedding,
                    "metadata": {
                        "title": doc["title"],
                        "category": doc["category"],
                        "text": doc["text"][:1000],
                        "full_text": doc["text"],
                        "embedded_at": datetime.utcnow().isoformat()
                    }
                }
                upsert_data.append(vector_data)
            
            logger.info("Upserting vectors to Pinecone", count=len(upsert_data))
            
            for i in range(0, len(upsert_data), self.batch_size):
                batch = upsert_data[i:i + self.batch_size]
                
                response = self.index.upsert(
                    vectors=batch,
                    namespace=self.namespace
                )
                
                logger.info("Upserted batch", 
                           batch_start=i, 
                           batch_size=len(batch),
                           upserted_count=response.upserted_count)
                
                await asyncio.sleep(0.5)
            
            logger.info("Successfully upserted all documents")
            return True
            
        except Exception as e:
            logger.error("Failed to upsert documents", error=str(e))
            return False
    
    async def test_similarity_search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Test similarity search on embedded documents"""
        try:
            query_embeddings = await self.generate_embeddings([query])
            query_vector = query_embeddings[0]
            
            search_results = self.index.query(
                vector=query_vector,
                namespace=self.namespace,
                top_k=top_k,
                include_metadata=True
            )
            
            results = []
            for match in search_results.matches:
                results.append({
                    "doc_id": match.id,
                    "score": match.score,
                    "title": match.metadata.get("title", ""),
                    "category": match.metadata.get("category", ""),
                    "text_snippet": match.metadata.get("text", "")[:300] + "..."
                })
            
            logger.info("Similarity search completed", 
                       query=query, 
                       results_count=len(results))
            
            return results
            
        except Exception as e:
            logger.error("Similarity search failed", query=query, error=str(e))
            return []


async def main():
    """Main embedding pipeline execution"""
    try:
        embedder = DocumentEmbedder()
        
        logger.info("Setting up Pinecone index...")
        if not await embedder.setup_pinecone_index():
            logger.error("Failed to setup Pinecone index")
            return False
        
        documents = embedder.get_explanation_documents()
        
        logger.info("Starting document embedding process...")
        if not await embedder.upsert_documents(documents):
            logger.error("Failed to upsert documents")
            return False
        
        logger.info("Testing similarity search...")
        test_queries = [
            "Why was my invoice auto-approved?",
            "What causes an invoice to need manual review?",
            "How does the system extract data from invoices?"
        ]
        
        for query in test_queries:
            results = await embedder.test_similarity_search(query)
            print(f"\nQuery: {query}")
            for i, result in enumerate(results):
                print(f"  {i+1}. {result['title']} (score: {result['score']:.3f})")
                print(f"     {result['text_snippet']}")
        
        logger.info("Document embedding pipeline completed successfully")
        return True
        
    except Exception as e:
        logger.error("Embedding pipeline failed", error=str(e))
        return False


if __name__ == "__main__":
    required_vars = ["PINECONE_API_KEY", "ANTHROPIC_API_KEY"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"ERROR: Missing required environment variables: {', '.join(missing_vars)}")
        print("\nPlease set:")
        for var in missing_vars:
            print(f"  export {var}='your-api-key-here'")
        exit(1)
    
    success = asyncio.run(main())
    exit(0 if success else 1) 