"""
ARMAX E2E Docker Test

THIS TEST RUNS INSIDE THE DOCKER CONTAINER - NOT ON HOST!

Usage:
    # From project root, rebuild dispatcher then run test
    docker-compose build da-dispatcher
    docker exec da-dispatcher python tests/test_armax_e2e_docker.py

    # Or with pytest
    docker exec da-dispatcher python -m pytest tests/test_armax_e2e_docker.py -v

The test:
1. Generates synthetic logs with known anomalies
2. Injects them into elasticsearch-dataset
3. Creates KB configuration in MongoDB
4. Verifies ARMAX training works
5. Verifies ARMAX detection works

Note: Full pipeline verification (Extractor -> Dispatcher -> Anomalies)
      requires monitoring container logs separately.
"""

import sys
import os
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

# Add MotorDA to path (for running inside /app in container)
sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# Docker Container Configuration (INTERNAL NETWORK NAMES)
# =============================================================================

class DockerConfig:
    """Configuration for Docker internal network.
    
    IMPORTANT: These use Docker container names, not localhost!
    """
    
    # Elasticsearch containers (internal Docker network)
    ES_DATASET_HOST = "http://elasticsearch-dataset:9200"
    ES_ANOMALIES_HOST = "http://elasticsearch-anomalies:9200"
    
    # MongoDB with replica set (internal Docker network)
    MONGO_HOST = "mongodb://admin:1q2w3E*@mongodb:27017/?authSource=admin&replicaSet=rs0"
    MONGO_DATABASE = "anomaly_detection"
    
    # Test configuration
    TEST_INDEX_PREFIX = "test-armax-logs"
    MAX_WAIT_SECONDS = 60
    POLL_INTERVAL = 5


# =============================================================================
# Log Generation (Inline - no external dependencies needed)
# =============================================================================

def generate_test_logs(
    count: int = 48, 
    anomaly_indices: Optional[List[int]] = None,
    base_value: float = 1000.0,
    anomaly_multiplier: float = 5.0,
) -> List[Dict[str, Any]]:
    """Generate test log documents with anomalies.
    
    Args:
        count: Number of hourly documents
        anomaly_indices: Which indices should be anomalies
        base_value: Base request count
        anomaly_multiplier: How much to multiply for anomaly
        
    Returns:
        List of log documents
    """
    import random
    random.seed(42)
    
    anomaly_indices = set(anomaly_indices or [])
    base_time = datetime.now(timezone.utc) - timedelta(hours=count)
    
    documents = []
    
    for i in range(count):
        ts = base_time + timedelta(hours=i)
        
        # Normal values with some noise
        request_count = base_value + random.randint(-100, 100)
        error_count = 10 + random.randint(-5, 5)
        
        # Inject anomaly - big spike
        if i in anomaly_indices:
            request_count = base_value * anomaly_multiplier
            error_count = 100
        
        doc = {
            "@timestamp": ts.isoformat(),
            "request_count": int(request_count),
            "error_count": error_count,
            "avg_response_time": 50.0 + random.uniform(-10, 10),
        }
        documents.append(doc)
    
    return documents


def inject_logs_to_elasticsearch(
    documents: List[Dict[str, Any]], 
    index_name: str
) -> Dict[str, Any]:
    """Inject logs into Elasticsearch dataset.
    
    Args:
        documents: List of log documents
        index_name: Target index name
        
    Returns:
        Injection result
    """
    from elasticsearch import Elasticsearch
    from elasticsearch.helpers import bulk
    
    es = Elasticsearch(hosts=[DockerConfig.ES_DATASET_HOST])
    
    # Create index with mapping
    mapping = {
        "mappings": {
            "properties": {
                "@timestamp": {"type": "date"},
                "request_count": {"type": "integer"},
                "error_count": {"type": "integer"},
                "avg_response_time": {"type": "float"},
            }
        }
    }
    
    if es.indices.exists(index=index_name):
        es.indices.delete(index=index_name)
    
    es.indices.create(index=index_name, body=mapping)
    
    # Bulk insert
    actions = [
        {
            "_index": index_name,
            "_source": doc
        }
        for doc in documents
    ]
    
    success, failed = bulk(es, actions, raise_on_error=False)
    
    # Refresh to make docs searchable
    es.indices.refresh(index=index_name)
    
    return {
        "success": success,
        "failed": len(failed) if isinstance(failed, list) else failed,
        "index": index_name,
    }


# =============================================================================
# KB Configuration
# =============================================================================

def create_armax_config(
    index_name: str,
    start_time: str,
    end_time: str,
) -> str:
    """Create ARMAX KB configuration in MongoDB.
    
    Args:
        index_name: Elasticsearch index with test data
        start_time: Training start time (ISO format)
        end_time: Training end time (ISO format)
        
    Returns:
        Configuration ID
    """
    from pymongo import MongoClient
    
    client = MongoClient(DockerConfig.MONGO_HOST)
    db = client[DockerConfig.MONGO_DATABASE]
    collection = db["train_config"]
    
    config_name = f"armax-e2e-{uuid.uuid4().hex[:8]}"
    
    sql_query = f"""
    SELECT 
        "@timestamp" as es_timestamp,
        request_count,
        error_count,
        avg_response_time
    FROM "{index_name}"
    WHERE "@timestamp" >= '$from' AND "@timestamp" < '$to'
    ORDER BY "@timestamp"
    """
    
    config = {
        "name": config_name,
        "description": "ARMAX E2E Docker test",
        "change_flag": 0,
        "elasticsearch_sql_query": sql_query,
        "query_mode": {
            "type": "aggregated",
            "timestamp_field": "es_timestamp"
        },
        "bucket_profile_id": None,
        "algorithm": {
            "name": "armax",
            "parameters": [
                {
                    "dimension": "request_count",
                    "is_active": True,
                    "metadata": None
                }
            ]
        },
        "scheduling": {
            "training_config": {
                "type": "static",
                "from": start_time,
                "to": end_time,
                "is_active": True,
            },
            "detection_config": {
                "frequency": "*/1 * * * *",
                "detection_window": 3600,
                "is_active": True,
                "from": start_time,
            }
        }
    }
    
    result = collection.insert_one(config)
    config_id = str(result.inserted_id)
    
    print(f"  Created KB config: {config_name}")
    print(f"  Config ID: {config_id}")
    client.close()
    
    return config_id


def cleanup_config(config_id: str, index_name: str):
    """Clean up test resources."""
    try:
        from pymongo import MongoClient
        from bson import ObjectId
        from elasticsearch import Elasticsearch
        
        # Delete from MongoDB
        client = MongoClient(DockerConfig.MONGO_HOST)
        db = client[DockerConfig.MONGO_DATABASE]
        db["train_config"].delete_one({"_id": ObjectId(config_id)})
        db["series"].delete_many({"config_id": ObjectId(config_id)})
        db["series_result"].delete_many({"config_id": ObjectId(config_id)})
        client.close()
        
        # Delete Elasticsearch index
        es = Elasticsearch(hosts=[DockerConfig.ES_DATASET_HOST])
        if es.indices.exists(index=index_name):
            es.indices.delete(index=index_name)
            
        print(f"  Cleaned up config and index")
        
    except Exception as e:
        print(f"  Cleanup warning: {e}")


# =============================================================================
# Connection Tests
# =============================================================================

def check_elasticsearch_dataset_connection():
    """Test connection to Elasticsearch dataset."""
    from elasticsearch import Elasticsearch
    
    es = Elasticsearch(hosts=[DockerConfig.ES_DATASET_HOST])
    assert es.ping(), "Cannot connect to elasticsearch-dataset"
    print("  [OK] Elasticsearch dataset connected")


def check_elasticsearch_anomalies_connection():
    """Test connection to Elasticsearch anomalies."""
    from elasticsearch import Elasticsearch
    
    es = Elasticsearch(hosts=[DockerConfig.ES_ANOMALIES_HOST])
    assert es.ping(), "Cannot connect to elasticsearch-anomalies"
    print("  [OK] Elasticsearch anomalies connected")


def check_mongodb_connection():
    """Test connection to MongoDB with replica set."""
    from pymongo import MongoClient
    
    client = MongoClient(DockerConfig.MONGO_HOST, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    client.close()
    print("  [OK] MongoDB connected")


# =============================================================================
# ARMAX Algorithm Tests
# =============================================================================

def check_armax_algorithm_available():
    """Test that ARMAX algorithm is registered."""
    from algorithm_registry import get_algorithm, is_algorithm_supported
    
    assert is_algorithm_supported("armax"), "ARMAX not registered"
    
    algo = get_algorithm("armax")
    assert algo is not None
    assert algo.name == "armax"
    print("  [OK] ARMAX algorithm registered")


def check_armax_training():
    """Test ARMAX training with generated data."""
    from ARMAX.algorithm import ARMAXAlgorithm
    
    algo = ARMAXAlgorithm()
    
    # Generate training data
    training_data = []
    base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    
    for i in range(30):
        ts = base_time + timedelta(hours=i)
        training_data.append({
            "timestamp": ts.isoformat(),
            "value": 100.0 + (i % 24) * 2 + (i * 0.1),
        })
    
    result = algo.train(training_data)
    
    assert result.sufficient_data, f"Training failed: insufficient data"
    assert result.data_points == 30
    assert "model_type" in result.baseline
    
    print(f"  [OK] ARMAX training: {result.data_points} points")
    return result.baseline


def check_armax_detection(baseline: Dict[str, Any]):
    """Test ARMAX detection with normal and anomaly values."""
    from ARMAX.algorithm import ARMAXAlgorithm
    
    algo = ARMAXAlgorithm()
    
    # Build history
    base_time = datetime(2025, 1, 2, tzinfo=timezone.utc)
    history = []
    for i in range(10):
        ts = base_time + timedelta(hours=i)
        history.append({
            "timestamp": ts.isoformat(),
            "value": 100.0 + (i % 24) * 2,
        })
    
    # Test normal value
    normal_result = algo.detect(
        value=110.0,
        baseline=baseline,
        history=history,
    )
    
    # Test anomaly value (10x normal)
    anomaly_result = algo.detect(
        value=1000.0,
        baseline=baseline,
        history=history,
    )
    
    # Get prediction errors from algorithm_details
    normal_error = abs(normal_result.algorithm_details.get("prediction_error", 0))
    anomaly_error = abs(anomaly_result.algorithm_details.get("prediction_error", 0))
    
    # Anomaly should have higher prediction error
    assert anomaly_error > normal_error, \
        f"Anomaly error ({anomaly_error}) should be > normal ({normal_error})"
    
    print(f"  [OK] Normal: error={normal_error:.2f}, is_anomaly={normal_result.is_anomaly}")
    print(f"  [OK] Anomaly: error={anomaly_error:.2f}, is_anomaly={anomaly_result.is_anomaly}")


# =============================================================================
# Full Pipeline Test
# =============================================================================

def check_full_pipeline():
    """Test full pipeline: generate logs, inject, create config."""
    print("\n" + "-" * 60)
    print("FULL PIPELINE TEST")
    print("-" * 60)
    
    index_name = f"{DockerConfig.TEST_INDEX_PREFIX}-{uuid.uuid4().hex[:8]}"
    config_id = None
    
    try:
        # Step 1: Generate test logs with anomalies
        print("\n[1] Generating test logs...")
        anomaly_at = [24, 36]  # Anomalies at hour 24 and 36
        documents = generate_test_logs(count=48, anomaly_indices=anomaly_at)
        print(f"  Generated {len(documents)} documents")
        print(f"  Anomalies at indices: {anomaly_at}")
        
        # Step 2: Inject to Elasticsearch
        print("\n[2] Injecting to Elasticsearch...")
        result = inject_logs_to_elasticsearch(documents, index_name)
        assert result["success"] > 0, "Failed to inject documents"
        print(f"  Injected {result['success']} documents to '{index_name}'")
        
        # Step 3: Verify data in Elasticsearch
        print("\n[3] Verifying Elasticsearch data...")
        from elasticsearch import Elasticsearch
        es = Elasticsearch(hosts=[DockerConfig.ES_DATASET_HOST])
        count = es.count(index=index_name)["count"]
        assert count == len(documents), f"Expected {len(documents)}, got {count}"
        print(f"  Verified {count} documents in index")
        
        # Step 4: Create KB configuration
        print("\n[4] Creating KB configuration...")
        start_time = documents[0]["@timestamp"]
        end_time = documents[-1]["@timestamp"]
        config_id = create_armax_config(index_name, start_time, end_time)
        
        # Step 5: Verify config in MongoDB
        print("\n[5] Verifying MongoDB config...")
        from pymongo import MongoClient
        from bson import ObjectId
        
        client = MongoClient(DockerConfig.MONGO_HOST)
        db = client[DockerConfig.MONGO_DATABASE]
        saved_config = db["train_config"].find_one({"_id": ObjectId(config_id)})
        assert saved_config is not None, "Config not saved"
        assert saved_config["algorithm"]["name"] == "armax"
        client.close()
        print(f"  Config verified: {saved_config['name']}")
        
        print("\n" + "=" * 60)
        print("PIPELINE TEST PASSED!")
        print("=" * 60)
        print("\nNext steps (monitor separately):")
        print("  1. Extractor (etl-app) will detect the new config")
        print("  2. It will run the SQL query and create series data")
        print("  3. Dispatcher will train ARMAX on the series")
        print("  4. Dispatcher will run detection and find anomalies")
        print("  5. Anomalies will appear in elasticsearch-anomalies")
        print("\nMonitor with:")
        print("  docker logs -f etl-app")
        print("  docker logs -f da-dispatcher")
        
        return True
        
    except Exception as e:
        print(f"\n[FAIL] Pipeline error: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        print("\n[6] Cleanup...")
        if config_id:
            cleanup_config(config_id, index_name)


# =============================================================================
# Main Runner
# =============================================================================

def run_all_tests():
    """Run all Docker E2E tests."""
    print("=" * 70)
    print("ARMAX E2E DOCKER TESTS")
    print("=" * 70)
    print(f"Container working directory: {os.getcwd()}")
    print(f"ES Dataset: {DockerConfig.ES_DATASET_HOST}")
    print(f"ES Anomalies: {DockerConfig.ES_ANOMALIES_HOST}")
    print(f"MongoDB: mongodb:27017 (replica set: rs0)")
    
    passed = 0
    failed = 0
    
    try:
        # Connection tests
        print("\n" + "-" * 60)
        print("CONNECTION TESTS")
        print("-" * 60)
        
        check_elasticsearch_dataset_connection()
        check_elasticsearch_anomalies_connection()
        check_mongodb_connection()
        passed += 3
        
        # Algorithm tests
        print("\n" + "-" * 60)
        print("ARMAX ALGORITHM TESTS")
        print("-" * 60)
        
        check_armax_algorithm_available()
        baseline = check_armax_training()
        check_armax_detection(baseline)
        passed += 3
        
        # Full pipeline test
        if check_full_pipeline():
            passed += 1
        else:
            failed += 1
        
    except AssertionError as e:
        print(f"\n[FAIL] Assertion: {e}")
        failed += 1
    except Exception as e:
        print(f"\n[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
        failed += 1
    
    # Summary
    print("\n" + "=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 70)
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
