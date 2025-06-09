"""
OpenSearch indexer service for invoice documents
"""
import asyncio
import time
from typing import Optional, Dict, Any, List
from datetime import datetime

from opensearchpy import OpenSearch, AsyncOpenSearch
from opensearchpy.exceptions import OpenSearchException, ConnectionError, RequestError

from ..core.config import settings, get_opensearch_config
from ..core.logging import get_logger, log_function_call, log_function_result, log_error, log_performance_metrics
from ..models.invoice import InvoiceData, InvoiceDocument, InvoiceStatus, InvoiceSource


logger = get_logger(__name__)


class OpenSearchIndexer:
    """OpenSearch indexer for invoice documents"""
    
    def __init__(self):
        self.client = None
        self.index_name = settings.OPENSEARCH_INDEX
        self._initialize_client()
    
    def _initialize_client(self) -> None:
        """Initialize OpenSearch client"""
        try:
            config = get_opensearch_config()
            self.client = OpenSearch(**config)
            logger.info(f"OpenSearch client initialized for index {self.index_name}")
        except Exception as e:
            log_error(e, {"operation": "opensearch_client_init"})
            raise
    
    async def health_check(self) -> bool:
        """Check OpenSearch cluster health"""
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: self.client.cluster.health(timeout="5s")
            )
            
            # Check if cluster is at least yellow status
            status = response.get('status', 'red')
            return status in ['green', 'yellow']
            
        except Exception as e:
            log_error(e, {"operation": "opensearch_health_check"})
            return False
    
    async def create_index(self) -> bool:
        """Create index with proper mapping"""
        log_function_call("OpenSearchIndexer.create_index")
        start_time = time.time()
        
        try:
            # Check if index already exists
            loop = asyncio.get_event_loop()
            exists = await loop.run_in_executor(
                None,
                lambda: self.client.indices.exists(index=self.index_name)
            )
            
            if exists:
                logger.info(f"Index {self.index_name} already exists")
                return True
            
            # Define index mapping
            mapping = {
                "settings": {
                    "number_of_shards": 1,
                    "number_of_replicas": 0,
                    "analysis": {
                        "analyzer": {
                            "invoice_analyzer": {
                                "type": "custom",
                                "tokenizer": "standard",
                                "filter": [
                                    "lowercase",
                                    "stop",
                                    "snowball"
                                ]
                            }
                        }
                    }
                },
                "mappings": {
                    "properties": {
                        "id": {"type": "keyword"},
                        "invoice_id": {
                            "type": "text",
                            "analyzer": "invoice_analyzer",
                            "fields": {
                                "keyword": {"type": "keyword"}
                            }
                        },
                        "vendor": {
                            "type": "text",
                            "analyzer": "invoice_analyzer",
                            "fields": {
                                "keyword": {"type": "keyword"}
                            }
                        },
                        "vendor_normalized": {"type": "keyword"},
                        "date": {"type": "date"},
                        "date_year": {"type": "integer"},
                        "date_month": {"type": "integer"},
                        "date_quarter": {"type": "integer"},
                        "amount": {"type": "double"},
                        "amount_range": {"type": "keyword"},
                        "currency": {"type": "keyword"},
                        "status": {"type": "keyword"},
                        "source": {"type": "keyword"},
                        "line_items_text": {
                            "type": "text",
                            "analyzer": "invoice_analyzer"
                        },
                        "created_at": {"type": "date"},
                        "updated_at": {"type": "date"}
                    }
                }
            }
            
            # Create index
            await loop.run_in_executor(
                None,
                lambda: self.client.indices.create(
                    index=self.index_name,
                    body=mapping
                )
            )
            
            logger.info(f"Created OpenSearch index: {self.index_name}")
            return True
            
        except Exception as e:
            log_error(e, {"index": self.index_name})
            return False
        finally:
            log_function_result("OpenSearchIndexer.create_index", 
                              True, time.time() - start_time)
    
    async def upsert_document(self, 
                            document_id: str,
                            invoice_data: InvoiceData,
                            status: InvoiceStatus,
                            source: InvoiceSource) -> bool:
        """Upsert invoice document to OpenSearch"""
        log_function_call("OpenSearchIndexer.upsert_document", 
                         document_id=document_id, invoice_id=invoice_data.invoice_id)
        start_time = time.time()
        
        try:
            # Create document from invoice data
            document = InvoiceDocument.from_invoice_data(
                document_id, invoice_data, status, source
            )
            
            # Convert to dictionary for indexing
            doc_dict = document.model_dump()
            
            # Handle Decimal serialization
            for key, value in doc_dict.items():
                if hasattr(value, '__float__'):
                    doc_dict[key] = float(value)
                elif isinstance(value, datetime):
                    doc_dict[key] = value.isoformat()
            
            # Upsert document
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.index(
                    index=self.index_name,
                    id=document_id,
                    body=doc_dict,
                    refresh=True  # Refresh for immediate search availability
                )
            )
            
            # Check if operation was successful
            success = response.get('result') in ['created', 'updated']
            
            if success:
                logger.info(f"Upserted document {document_id} to OpenSearch")
                
                # Log performance metrics
                duration = time.time() - start_time
                log_performance_metrics(
                    "opensearch_upsert",
                    duration,
                    document_size=len(str(doc_dict))
                )
            else:
                logger.error(f"Failed to upsert document {document_id}: {response}")
            
            return success
            
        except Exception as e:
            log_error(e, {
                "document_id": document_id,
                "invoice_id": invoice_data.invoice_id,
                "operation": "upsert_document"
            })
            return False
        finally:
            log_function_result("OpenSearchIndexer.upsert_document", 
                              success if 'success' in locals() else False,
                              time.time() - start_time)
    
    async def delete_document(self, document_id: str) -> bool:
        """Delete document from OpenSearch"""
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.delete(
                    index=self.index_name,
                    id=document_id,
                    refresh=True
                )
            )
            
            success = response.get('result') == 'deleted'
            if success:
                logger.info(f"Deleted document {document_id} from OpenSearch")
            
            return success
            
        except Exception as e:
            if "not_found" in str(e).lower():
                logger.warning(f"Document {document_id} not found for deletion")
                return True  # Consider not found as success
            
            log_error(e, {"document_id": document_id})
            return False
    
    async def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Get document from OpenSearch"""
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.get(
                    index=self.index_name,
                    id=document_id
                )
            )
            
            if response.get('found'):
                return response.get('_source')
            return None
            
        except Exception as e:
            if "not_found" not in str(e).lower():
                log_error(e, {"document_id": document_id})
            return None
    
    async def search_documents(self, 
                             query: Dict[str, Any],
                             size: int = 10,
                             from_: int = 0) -> Dict[str, Any]:
        """Search documents in OpenSearch"""
        log_function_call("OpenSearchIndexer.search_documents", 
                         size=size, from_=from_)
        start_time = time.time()
        
        try:
            search_body = {
                "query": query,
                "size": size,
                "from": from_,
                "sort": [
                    {"updated_at": {"order": "desc"}}
                ]
            }
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.search(
                    index=self.index_name,
                    body=search_body
                )
            )
            
            # Log performance metrics
            duration = time.time() - start_time
            took_ms = response.get('took', 0)
            hits = response.get('hits', {}).get('total', {}).get('value', 0)
            
            log_performance_metrics(
                "opensearch_search",
                duration,
                took_ms=took_ms,
                hits_returned=hits,
                size=size
            )
            
            return response
            
        except Exception as e:
            log_error(e, {"query": query, "size": size})
            raise
        finally:
            log_function_result("OpenSearchIndexer.search_documents", 
                              hits if 'hits' in locals() else 0,
                              time.time() - start_time)
    
    async def bulk_upsert(self, documents: List[Dict[str, Any]]) -> Dict[str, int]:
        """Bulk upsert documents to OpenSearch"""
        log_function_call("OpenSearchIndexer.bulk_upsert", 
                         document_count=len(documents))
        start_time = time.time()
        
        try:
            if not documents:
                return {"success": 0, "errors": 0}
            
            # Prepare bulk request body
            bulk_body = []
            for doc in documents:
                doc_id = doc.get('id')
                if not doc_id:
                    continue
                
                # Action metadata
                bulk_body.append({
                    "index": {
                        "_index": self.index_name,
                        "_id": doc_id
                    }
                })
                
                # Document source
                bulk_body.append(doc)
            
            if not bulk_body:
                return {"success": 0, "errors": 0}
            
            # Execute bulk request
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.bulk(
                    body=bulk_body,
                    refresh=True
                )
            )
            
            # Process response
            success_count = 0
            error_count = 0
            
            for item in response.get('items', []):
                if 'index' in item:
                    if item['index'].get('status') in [200, 201]:
                        success_count += 1
                    else:
                        error_count += 1
                        logger.warning(f"Bulk index error: {item['index']}")
            
            # Log performance metrics
            duration = time.time() - start_time
            log_performance_metrics(
                "opensearch_bulk_upsert",
                duration,
                document_count=len(documents),
                success_count=success_count,
                error_count=error_count
            )
            
            logger.info(f"Bulk upsert completed: {success_count} success, {error_count} errors")
            
            return {"success": success_count, "errors": error_count}
            
        except Exception as e:
            log_error(e, {"document_count": len(documents)})
            return {"success": 0, "errors": len(documents)}
        finally:
            log_function_result("OpenSearchIndexer.bulk_upsert", 
                              success_count if 'success_count' in locals() else 0,
                              time.time() - start_time)
    
    async def get_index_stats(self) -> Dict[str, Any]:
        """Get index statistics"""
        try:
            loop = asyncio.get_event_loop()
            
            # Get index stats
            stats_response = await loop.run_in_executor(
                None,
                lambda: self.client.indices.stats(index=self.index_name)
            )
            
            # Get document count
            count_response = await loop.run_in_executor(
                None,
                lambda: self.client.count(index=self.index_name)
            )
            
            index_stats = stats_response.get('indices', {}).get(self.index_name, {})
            primary = index_stats.get('primaries', {})
            
            return {
                "document_count": count_response.get('count', 0),
                "index_size_bytes": primary.get('store', {}).get('size_in_bytes', 0),
                "index_size_mb": round(primary.get('store', {}).get('size_in_bytes', 0) / (1024 * 1024), 2),
                "search_total": primary.get('search', {}).get('query_total', 0),
                "search_time_ms": primary.get('search', {}).get('query_time_in_millis', 0),
                "index_total": primary.get('indexing', {}).get('index_total', 0),
                "index_time_ms": primary.get('indexing', {}).get('index_time_in_millis', 0),
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            log_error(e, {"operation": "get_index_stats"})
            raise
    
    async def refresh_index(self) -> bool:
        """Refresh the index to make documents searchable"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.indices.refresh(index=self.index_name)
            )
            
            logger.info(f"Refreshed OpenSearch index: {self.index_name}")
            return True
            
        except Exception as e:
            log_error(e, {"index": self.index_name})
            return False


# Global indexer service instance
indexer_service = OpenSearchIndexer() 