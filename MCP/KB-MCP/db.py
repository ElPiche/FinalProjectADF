# db.py - Database client wrappers and connection management for KB-MCP

import os
import time
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
from elasticsearch import Elasticsearch
from instrumentation import timed
from mcp_tools_pkg.config import (
    ELASTICSEARCH_QUERY_TIMEOUT,
    MONGODB_OPERATION_TIMEOUT,
)

# Global Configuration Variables (moved from main)
db_kb_name = "knowledge_base"
db_kb_collection_name = "kb_configs"
db_logger_name = "knowledge_base_mcp_logs"
mongo_connection_string = "mongodb://admin:1q2w3E*@mongodb:27017/?authSource=admin&replicaSet=rs0"
mongo_timeout_ms = max(MONGODB_OPERATION_TIMEOUT, 1) * 1000

# Elasticsearch Configuration
es_host = "http://elasticsearch-dataset:9200"


@timed
def connect_mongodb() -> MongoClient:
    """
    Connect to MongoDB KB instance with proper error handling and logging.
    Optimized for replica set connections.

    Returns:
        MongoClient: Connected MongoDB client, or None if connection fails
    """
    try:
        from utils import log_message

        log_message(f"Attempting to connect to MongoDB at {mongo_connection_string.replace('1q2w3E%2A', '***')}",
                    "info", "connect_mongodb", "connection")

        # Enhanced client configuration for replica sets
        client = MongoClient(
            mongo_connection_string,
            serverSelectionTimeoutMS=mongo_timeout_ms,
            connectTimeoutMS=mongo_timeout_ms,
            socketTimeoutMS=mongo_timeout_ms,
            retryWrites=True,
            retryReads=True,
            readPreference='primaryPreferred'  # Allow reads from secondary if primary unavailable
        )

        # Test the connection with detailed error information
        result = client.admin.command('ping')
        log_message(f"MongoDB ping successful: {result}", "info", "connect_mongodb", "ping")

        # Check replica set status for additional debugging
        try:
            rs_status = client.admin.command('replSetGetStatus')
            log_message(f"Replica set status: {rs_status.get('set', 'unknown')}", "info", "connect_mongodb", "replica_set")
        except Exception as rs_e:
            log_message(f"Could not get replica set status (may be normal): {rs_e}", "warning", "connect_mongodb", "replica_set")

        log_message("MongoDB connection successful", "info", "connect_mongodb", "connection")

        # Verify database access
        db = client[db_kb_name]
        log_message(f"MongoDB database '{db_kb_name}' accessible", "info", "connect_mongodb", "database")
        return client

    except ConnectionFailure as e:
        log_message(f"MongoDB connection failed: {str(e)}", "error", "connect_mongodb", "connection")
        return None
    except OperationFailure as e:
        log_message(f"MongoDB authentication/authorization failed: {str(e)}", "error", "connect_mongodb", "auth")
        return None
    except Exception as e:
        log_message(f"Unexpected MongoDB connection error: {str(e)}", "error", "connect_mongodb", "connection")
        return None


@timed
def connect_elasticsearch() -> Elasticsearch:
    """
    Connect to Elasticsearch with timeout configuration.

    Returns:
        Elasticsearch: Connected Elasticsearch client, or None if connection fails
    """
    try:
        from utils import log_message

        log_message(f"Attempting to connect to Elasticsearch at {es_host}", "info", "connect_elasticsearch", "connection")

        # Create client with timeout
        es = Elasticsearch(es_host, timeout=ELASTICSEARCH_QUERY_TIMEOUT)

        # Test connection
        if es.ping():
            log_message("Elasticsearch connection successful", "info", "connect_elasticsearch", "ping")
            return es
        else:
            log_message("Elasticsearch ping failed", "error", "connect_elasticsearch", "ping")
            return None

    except Exception as e:
        from utils import log_message
        log_message(f"Elasticsearch connection failed: {str(e)}", "error", "connect_elasticsearch", "connection")
        return None


def safe_close_client(client):
    """
    Safely close a database client.

    Args:
        client: Database client to close (MongoClient or Elasticsearch)
    """
    try:
        if hasattr(client, 'close'):
            client.close()
    except Exception:
        pass  # Ignore errors during cleanup


class DatabaseWrapper:
    """Wrapper that provides collection access from a MongoDB database."""
    
    def __init__(self, db):
        self._db = db
    
    def get_collection(self, name: str):
        """Get a collection by name."""
        return self._db[name]
    
    def __getitem__(self, name: str):
        """Allow dict-style access to collections."""
        return self._db[name]


def get_db() -> DatabaseWrapper:
    """
    Get the anomaly_detection database wrapper.
    
    Returns:
        DatabaseWrapper: Wrapper providing access to MongoDB collections.
    
    Raises:
        RuntimeError: If MongoDB connection fails.
    """
    client = connect_mongodb()
    if client is None:
        raise RuntimeError("Failed to connect to MongoDB")
    
    # Use anomaly_detection database for bucket profiles and KB configs
    return DatabaseWrapper(client["anomaly_detection"])