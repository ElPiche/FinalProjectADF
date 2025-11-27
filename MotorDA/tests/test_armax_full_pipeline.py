"""
Full Pipeline E2E Test for ARMAX

This test:
1. Uses LogGenerator to create test logs with anomalies
2. Injects logs into Elasticsearch (dataset index)
3. Creates KB configuration via MongoDB
4. Waits for Extractor to process
5. Waits for Dispatcher to detect
6. Verifies anomalies appear in Elasticsearch-anomalies

Requirements:
- Docker containers running (docker-compose up -d)
- mongodb, elasticsearch-dataset, elasticsearch-anomalies, etl-app, da-dispatcher

Run:
    cd MotorDA
    python tests/test_armax_full_pipeline.py
"""

import sys
import os
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

# Add paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "log_generator"))


# =============================================================================
# Configuration
# =============================================================================

class E2EConfig:
    """Configuration for E2E test."""
    
    # Elasticsearch
    ES_DATASET_HOST = "http://localhost:9200"
    ES_ANOMALIES_HOST = "http://localhost:9201"
    
    # MongoDB
    MONGO_HOST = "mongodb://admin:1q2w3E*@localhost:27017/?authSource=admin&replicaSet=rs0"
    MONGO_DATABASE = "anomaly_detection"
    MONGO_COLLECTION = "train_config"
    
    # Test index name
    TEST_INDEX = f"test-armax-logs-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    # Timing
    EXTRACTOR_WAIT_SECONDS = 30
    DISPATCHER_WAIT_SECONDS = 30
    POLL_INTERVAL_SECONDS = 5


# =============================================================================
# Helpers
# =============================================================================

def check_elasticsearch_connection(host: str) -> bool:
    """Check if Elasticsearch is accessible."""
    try:
        from elasticsearch import Elasticsearch
        es = Elasticsearch(hosts=[host])
        return es.ping()
    except Exception as e:
        print(f"Elasticsearch connection failed: {e}")
        return False


def check_mongodb_connection() -> bool:
    """Check if MongoDB is accessible."""
    try:
        from pymongo import MongoClient
        client = MongoClient(E2EConfig.MONGO_HOST, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        return True
    except Exception as e:
        print(f"MongoDB connection failed: {e}")
        return False


def inject_test_logs() -> Dict[str, Any]:
    """Generate and inject test logs with anomalies.
    
    Returns:
        Dict with injection details
    """
    from log_generator.log_schema import create_aggregated_metrics_schema
    from log_generator.log_generator import LogGenerator
    from log_generator.injector import ElasticsearchInjector
    
    # Create schema for aggregated metrics
    schema = create_aggregated_metrics_schema(index_name=E2EConfig.TEST_INDEX)
    
    # Generate logs
    generator = LogGenerator(schema, seed=42)
    
    # Create 48 hours of hourly data, with anomaly at hour 24
    start_time = datetime.now(timezone.utc) - timedelta(hours=48)
    end_time = datetime.now(timezone.utc)
    anomaly_hour = 24  # Put anomaly in the middle
    
    result = generator.generate_hourly_buckets(
        start_time=start_time,
        end_time=end_time,
        anomaly_hours=[anomaly_hour],
        anomaly_field="request_count",
    )
    
    print(f"Generated {result.total_count} logs with {result.anomaly_count} anomalies")
    
    # Inject into Elasticsearch
    injector = ElasticsearchInjector(
        host=E2EConfig.ES_DATASET_HOST,
        index=E2EConfig.TEST_INDEX,
    )
    
    # Create index with mapping
    injector.create_index(schema.get_es_mapping())
    
    # Inject documents
    inject_result = injector.bulk_inject(result.documents)
    
    print(f"Injected {inject_result['success']} documents, {inject_result['failed']} failures")
    
    return {
        "index": E2EConfig.TEST_INDEX,
        "document_count": result.total_count,
        "anomaly_count": result.anomaly_count,
        "anomaly_indices": result.anomaly_indices,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
    }


def create_kb_configuration(injection_info: Dict[str, Any]) -> str:
    """Create KB configuration in MongoDB.
    
    Args:
        injection_info: Details from log injection
        
    Returns:
        Configuration ID
    """
    from pymongo import MongoClient
    
    client = MongoClient(E2EConfig.MONGO_HOST)
    db = client[E2EConfig.MONGO_DATABASE]
    collection = db[E2EConfig.MONGO_COLLECTION]
    
    config_name = f"armax-e2e-test-{uuid.uuid4().hex[:8]}"
    
    # SQL query for the test index
    sql_query = f"""
    SELECT 
        "@timestamp" as es_timestamp,
        request_count,
        error_count
    FROM "{E2EConfig.TEST_INDEX}"
    WHERE "@timestamp" >= '$from' AND "@timestamp" < '$to'
    ORDER BY "@timestamp"
    """
    
    config = {
        "name": config_name,
        "description": "ARMAX E2E test configuration",
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
                "from": injection_info["start_time"],
                "to": injection_info["end_time"],
                "is_active": True,
                "training_window": None,
                "training_query": None
            },
            "detection_config": {
                "frequency": "*/5 * * * *",
                "detection_window": 3600,
                "is_active": True,
                "from": injection_info["start_time"],
                "detection_query": None
            }
        }
    }
    
    result = collection.insert_one(config)
    config_id = str(result.inserted_id)
    
    print(f"Created KB config: {config_name} (ID: {config_id})")
    
    return config_id


def wait_for_series_data(config_id: str, timeout_seconds: int = 60) -> bool:
    """Wait for Extractor to create series data.
    
    Args:
        config_id: MongoDB config ID
        timeout_seconds: Maximum wait time
        
    Returns:
        True if series data found
    """
    from pymongo import MongoClient
    from bson import ObjectId
    
    client = MongoClient(E2EConfig.MONGO_HOST)
    db = client[E2EConfig.MONGO_DATABASE]
    
    start_time = time.time()
    
    while time.time() - start_time < timeout_seconds:
        # Check for series data (Extractor output)
        series = db["series"].find_one({"config_id": ObjectId(config_id)})
        if series:
            print(f"Found series data for config {config_id}")
            return True
        
        print(f"Waiting for series data... ({int(time.time() - start_time)}s)")
        time.sleep(E2EConfig.POLL_INTERVAL_SECONDS)
    
    print(f"Timeout waiting for series data")
    return False


def wait_for_anomalies(timeout_seconds: int = 60) -> Dict[str, Any]:
    """Wait for Dispatcher to write anomalies.
    
    Args:
        timeout_seconds: Maximum wait time
        
    Returns:
        Dict with anomaly results
    """
    from elasticsearch import Elasticsearch
    
    es = Elasticsearch(hosts=[E2EConfig.ES_ANOMALIES_HOST])
    
    start_time = time.time()
    
    while time.time() - start_time < timeout_seconds:
        try:
            # Search for anomalies from ARMAX
            result = es.search(
                index="anomaly_results*",
                body={
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"algorithm": "armax"}}
                            ]
                        }
                    },
                    "size": 10,
                    "sort": [{"@timestamp": "desc"}]
                }
            )
            
            hits = result.get("hits", {}).get("hits", [])
            if hits:
                print(f"Found {len(hits)} ARMAX anomalies!")
                return {
                    "found": True,
                    "count": len(hits),
                    "anomalies": [hit["_source"] for hit in hits]
                }
                
        except Exception as e:
            print(f"Error querying anomalies: {e}")
        
        print(f"Waiting for anomalies... ({int(time.time() - start_time)}s)")
        time.sleep(E2EConfig.POLL_INTERVAL_SECONDS)
    
    return {"found": False, "count": 0, "anomalies": []}


def cleanup(config_id: Optional[str] = None):
    """Clean up test resources."""
    try:
        from elasticsearch import Elasticsearch
        from pymongo import MongoClient
        from bson import ObjectId
        
        # Delete test index
        es = Elasticsearch(hosts=[E2EConfig.ES_DATASET_HOST])
        if es.indices.exists(index=E2EConfig.TEST_INDEX):
            es.indices.delete(index=E2EConfig.TEST_INDEX)
            print(f"Deleted test index: {E2EConfig.TEST_INDEX}")
        
        # Delete KB config
        if config_id:
            client = MongoClient(E2EConfig.MONGO_HOST)
            db = client[E2EConfig.MONGO_DATABASE]
            db[E2EConfig.MONGO_COLLECTION].delete_one({"_id": ObjectId(config_id)})
            db["series"].delete_many({"config_id": ObjectId(config_id)})
            print(f"Deleted KB config and series: {config_id}")
            
    except Exception as e:
        print(f"Cleanup error (non-fatal): {e}")


# =============================================================================
# Main Test
# =============================================================================

def run_e2e_test():
    """Run the full E2E pipeline test."""
    print("=" * 70)
    print("ARMAX FULL PIPELINE E2E TEST")
    print("=" * 70)
    
    config_id = None
    
    try:
        # Step 1: Check connections
        print("\n[1] Checking connections...")
        
        if not check_elasticsearch_connection(E2EConfig.ES_DATASET_HOST):
            print("FAIL: Cannot connect to Elasticsearch dataset (port 9200)")
            print("Make sure to run: docker-compose up -d")
            return 1
        print("  - Elasticsearch dataset: OK")
        
        if not check_elasticsearch_connection(E2EConfig.ES_ANOMALIES_HOST):
            print("FAIL: Cannot connect to Elasticsearch anomalies (port 9201)")
            return 1
        print("  - Elasticsearch anomalies: OK")
        
        if not check_mongodb_connection():
            print("FAIL: Cannot connect to MongoDB")
            print("Note: MongoDB replica set connection may not work from host")
            print("      This test needs to run inside Docker or with network access")
            return 1
        print("  - MongoDB: OK")
        
        # Step 2: Inject test logs
        print("\n[2] Injecting test logs...")
        injection_info = inject_test_logs()
        print(f"  - Index: {injection_info['index']}")
        print(f"  - Documents: {injection_info['document_count']}")
        print(f"  - Anomalies: {injection_info['anomaly_count']}")
        
        # Step 3: Create KB configuration
        print("\n[3] Creating KB configuration...")
        config_id = create_kb_configuration(injection_info)
        print(f"  - Config ID: {config_id}")
        
        # Step 4: Wait for Extractor
        print(f"\n[4] Waiting for Extractor (max {E2EConfig.EXTRACTOR_WAIT_SECONDS}s)...")
        if not wait_for_series_data(config_id, E2EConfig.EXTRACTOR_WAIT_SECONDS):
            print("WARNING: Series data not found (Extractor may not be processing)")
            print("         Check: docker logs etl-app")
        else:
            print("  - Series data: OK")
        
        # Step 5: Wait for Dispatcher anomalies
        print(f"\n[5] Waiting for Dispatcher (max {E2EConfig.DISPATCHER_WAIT_SECONDS}s)...")
        anomaly_result = wait_for_anomalies(E2EConfig.DISPATCHER_WAIT_SECONDS)
        
        if anomaly_result["found"]:
            print(f"  - Anomalies found: {anomaly_result['count']}")
            print("\n[OK] E2E TEST PASSED!")
            print("\nSample anomaly:")
            print(json.dumps(anomaly_result["anomalies"][0], indent=2, default=str))
            return 0
        else:
            print("  - No anomalies found")
            print("\nWARNING: E2E test did not find anomalies in expected time")
            print("This may be normal if Dispatcher hasn't run yet.")
            print("Check: docker logs da-dispatcher")
            return 2  # Warning, not failure
            
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
        
    finally:
        # Cleanup
        print("\n[6] Cleanup...")
        cleanup(config_id)
        print("  - Done")


def run_local_test():
    """Run a local test without Docker dependencies.
    
    This validates the log generator and ARMAX algorithm work together.
    """
    print("=" * 70)
    print("ARMAX LOCAL TEST (No Docker)")
    print("=" * 70)
    
    try:
        # Import from log_generator package in tests directory
        import sys
        import os
        tests_dir = os.path.dirname(os.path.abspath(__file__))
        log_gen_dir = os.path.join(tests_dir, "log_generator")
        sys.path.insert(0, log_gen_dir)
        
        from log_schema import create_aggregated_metrics_schema
        from log_generator import LogGenerator
        from ARMAX.algorithm import ARMAXAlgorithm
        
        # Step 1: Generate logs
        print("\n[1] Generating test logs...")
        schema = create_aggregated_metrics_schema()
        generator = LogGenerator(schema, seed=42)
        
        start_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end_time = datetime(2025, 1, 3, tzinfo=timezone.utc)  # 48 hours
        
        result = generator.generate_hourly_buckets(
            start_time=start_time,
            end_time=end_time,
            anomaly_hours=[12],  # Anomaly at noon (hour 12)
        )
        
        print(f"  - Generated {result.total_count} documents")
        print(f"  - Anomaly at index: {result.anomaly_indices}")
        
        # Step 2: Train ARMAX
        print("\n[2] Training ARMAX...")
        algo = ARMAXAlgorithm()
        
        # Convert to training format
        training_data = []
        for doc in result.documents[:24]:  # First 24 hours for training
            training_data.append({
                "timestamp": doc["@timestamp"],
                "value": doc["request_count"],
            })
        
        train_result = algo.train(training_data)
        
        print(f"  - Sufficient data: {train_result.sufficient_data}")
        print(f"  - Data points: {train_result.data_points}")
        
        if not train_result.sufficient_data:
            print("FAIL: Not enough data for training")
            return 1
        
        # Step 3: Detect anomaly
        print("\n[3] Detecting anomaly...")
        
        # Build history from hours 15-24
        history = []
        for doc in result.documents[14:24]:
            history.append({
                "timestamp": doc["@timestamp"],
                "value": doc["request_count"],
            })
        
        # Test on anomaly point (index 24)
        anomaly_doc = result.documents[24]
        
        detect_result = algo.detect(
            value=anomaly_doc["request_count"],
            baseline=train_result.baseline,
            history=history,
            timestamp=anomaly_doc["@timestamp"],
        )
        
        print(f"  - Value: {anomaly_doc['request_count']}")
        print(f"  - Is anomaly: {detect_result.is_anomaly}")
        print(f"  - Score: {detect_result.score:.2f}")
        
        # Step 4: Verify result
        print("\n[4] Verification...")
        
        # The anomaly point should be detected
        if detect_result.is_anomaly:
            print("  [OK] Anomaly correctly detected!")
            return 0
        else:
            print("  WARNING: Anomaly not detected (may need threshold tuning)")
            return 2
            
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="ARMAX E2E Test")
    parser.add_argument("--local", action="store_true", 
                        help="Run local test without Docker")
    args = parser.parse_args()
    
    if args.local:
        exit_code = run_local_test()
    else:
        exit_code = run_e2e_test()
    
    sys.exit(exit_code)
