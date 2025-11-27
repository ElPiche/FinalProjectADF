"""Elasticsearch Injector

Injects generated logs into Elasticsearch.
Handles index creation, bulk insertion, and cleanup.

Usage:
    from log_generator import ElasticsearchInjector, LogSchema, LogGenerator
    
    schema = create_http_access_schema(index_name="my-test-logs")
    generator = LogGenerator(schema)
    
    result = generator.generate_batch(...)
    
    injector = ElasticsearchInjector(es_url="http://localhost:9200")
    injector.create_index(schema)
    injector.bulk_insert(result.documents, schema.index_name)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import json

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

try:
    from .log_schema import LogSchema
except ImportError:
    from log_schema import LogSchema


@dataclass
class InjectionResult:
    """Result of injecting logs into Elasticsearch."""
    success_count: int
    error_count: int
    errors: List[Dict[str, Any]]
    index_name: str
    
    @property
    def total(self) -> int:
        return self.success_count + self.error_count
    
    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.success_count / self.total


@dataclass
class ElasticsearchInjector:
    """Injects logs into Elasticsearch.
    
    Attributes:
        es_url: Elasticsearch URL
        es_client: Elasticsearch client (created if not provided)
    """
    
    es_url: str = "http://localhost:9200"
    es_client: Optional[Elasticsearch] = None
    
    def __post_init__(self):
        if self.es_client is None:
            self.es_client = Elasticsearch(self.es_url)
    
    def ping(self) -> bool:
        """Test connection to Elasticsearch."""
        try:
            return self.es_client.ping()
        except Exception:
            return False
    
    def create_index(
        self, 
        schema: LogSchema, 
        delete_existing: bool = True,
    ) -> bool:
        """Create an index based on the schema.
        
        Args:
            schema: Log schema with mapping info
            delete_existing: Delete index if it already exists
        
        Returns:
            True if successful
        """
        index_name = schema.index_name
        
        # Delete if exists and requested
        if delete_existing and self.es_client.indices.exists(index=index_name):
            self.es_client.indices.delete(index=index_name)
        
        # Create index with mapping
        mapping = schema.get_es_mapping()
        
        settings = schema.index_settings or {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        }
        
        body = {
            "settings": settings,
            **mapping,
        }
        
        self.es_client.indices.create(index=index_name, body=body)
        return True
    
    def insert_document(
        self, 
        document: Dict[str, Any], 
        index_name: str,
    ) -> str:
        """Insert a single document.
        
        Returns:
            Document ID
        """
        result = self.es_client.index(index=index_name, body=document)
        return result["_id"]
    
    def bulk_insert(
        self, 
        documents: List[Dict[str, Any]], 
        index_name: str,
        refresh: bool = True,
    ) -> InjectionResult:
        """Insert multiple documents using bulk API.
        
        Args:
            documents: List of documents to insert
            index_name: Target index
            refresh: Refresh index after insert for immediate search
        
        Returns:
            InjectionResult with success/error counts
        """
        if not documents:
            return InjectionResult(
                success_count=0,
                error_count=0,
                errors=[],
                index_name=index_name,
            )
        
        # Prepare bulk actions
        actions = [
            {
                "_index": index_name,
                "_source": doc,
            }
            for doc in documents
        ]
        
        # Execute bulk insert
        success_count, errors = bulk(
            self.es_client,
            actions,
            raise_on_error=False,
            refresh=refresh,
        )
        
        error_list = []
        if errors:
            for error in errors:
                error_list.append(error)
        
        return InjectionResult(
            success_count=success_count,
            error_count=len(error_list),
            errors=error_list,
            index_name=index_name,
        )
    
    def delete_index(self, index_name: str) -> bool:
        """Delete an index.
        
        Returns:
            True if deleted, False if didn't exist
        """
        if self.es_client.indices.exists(index=index_name):
            self.es_client.indices.delete(index=index_name)
            return True
        return False
    
    def get_document_count(self, index_name: str) -> int:
        """Get number of documents in an index."""
        try:
            result = self.es_client.count(index=index_name)
            return result["count"]
        except Exception:
            return 0
    
    def search(
        self, 
        index_name: str, 
        query: Optional[Dict[str, Any]] = None,
        size: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search for documents.
        
        Args:
            index_name: Index to search
            query: Elasticsearch query (default: match_all)
            size: Max results
        
        Returns:
            List of document sources
        """
        body = {"query": query or {"match_all": {}}, "size": size}
        result = self.es_client.search(index=index_name, body=body)
        return [hit["_source"] for hit in result["hits"]["hits"]]
    
    def wait_for_index(self, index_name: str, timeout: int = 30) -> bool:
        """Wait for index to be ready.
        
        Args:
            index_name: Index to wait for
            timeout: Timeout in seconds
        
        Returns:
            True if index is ready
        """
        import time
        start = time.time()
        
        while time.time() - start < timeout:
            try:
                if self.es_client.indices.exists(index=index_name):
                    health = self.es_client.cluster.health(
                        index=index_name, 
                        wait_for_status="yellow",
                        timeout="5s"
                    )
                    if health.get("status") in ("yellow", "green"):
                        return True
            except Exception:
                pass
            time.sleep(1)
        
        return False
