"""
DADispatcher.py - Algorithm-Agnostic Anomaly Detection Dispatcher

This module provides the main dispatcher for anomaly detection. It is completely
algorithm-agnostic and uses the algorithm registry for all algorithm operations.

NO LEGACY CODE - All algorithm dispatch goes through the registry.
"""

import json
import logging
import os
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Optional

import requests
from bson import ObjectId
from pymongo import MongoClient
from pymongo.collection import Collection

# Import algorithms package to trigger registration
from MotorDA.Dispatcher import algorithms  # noqa: F401

# Algorithm registry - the ONLY way to access algorithms
from MotorDA.Dispatcher.algorithm_interface import get_algorithm, list_algorithms

# Orchestrators for bucket-aware training and detection
from MotorDA.Dispatcher.training_orchestrator import TrainingOrchestrator, DetectionOrchestrator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# MongoDB Configuration
# =============================================================================

MONGO_URI = os.environ.get(
    "MONGO_URI",
    "mongodb://admin:1q2w3E*@mongodb:27017/?authSource=admin&replicaSet=rs0"
)
MONGO_DB = os.environ.get("MONGO_DB", "anomaly_detection")
KB_DB = os.environ.get("KB_DB", "knowledge_base")  # KB configs database

# Collection names
SERIES_COLLECTION = "series"
TRAINED_MODELS_COLLECTION = "trained_models"  # Per spec §3.4
TRAINING_CONFIG_COLLECTION = "training_config"
KB_CONFIGS_COLLECTION = "kb_configs"  # In knowledge_base DB
BUCKET_PROFILES_COLLECTION = "bucket_profiles"


def get_mongo_client() -> MongoClient:
    """Get MongoDB client with connection pooling."""
    return MongoClient(MONGO_URI)


def get_database():
    """Get the anomaly detection database."""
    client = get_mongo_client()
    return client[MONGO_DB]


def get_kb_database():
    """Get the knowledge_base database for KB configs."""
    client = get_mongo_client()
    return client[KB_DB]


def get_collection(name: str) -> Collection:
    """Get a specific collection from anomaly_detection DB."""
    db = get_database()
    return db[name]


def get_kb_collection() -> Collection:
    """Get the kb_configs collection from knowledge_base DB."""
    db = get_kb_database()
    return db[KB_CONFIGS_COLLECTION]


# =============================================================================
# LRU Cached Training Result Loader
# =============================================================================

@lru_cache(maxsize=128)
def get_cached_training_result(config_id: str, result_hash: str) -> Optional[dict]:
    """
    Load training result from MongoDB with LRU caching.
    
    Args:
        config_id: The configuration ID
        result_hash: Hash of the result for cache invalidation
        
    Returns:
        Training result dict or None
    """
    collection = get_collection(TRAINED_MODELS_COLLECTION)
    result = collection.find_one({"config_id": ObjectId(config_id)})
    if result:
        # Convert ObjectId to string for JSON serialization
        result["_id"] = str(result["_id"])
        result["config_id"] = str(result["config_id"])
    return result


def get_training_result(config_id: str) -> Optional[dict]:
    """
    Get trained model, using cache when possible.
    
    Args:
        config_id: The configuration ID
        
    Returns:
        Trained model dict or None
    """
    collection = get_collection(TRAINED_MODELS_COLLECTION)
    result = collection.find_one({"config_id": ObjectId(config_id)})
    
    if not result:
        return None
    
    # Create hash for cache key (using updated_at or _id)
    result_hash = str(result.get("updated_at", result["_id"]))
    
    return get_cached_training_result(config_id, result_hash)


def invalidate_training_cache(config_id: str):
    """Invalidate cache for a specific config."""
    get_cached_training_result.cache_clear()


# =============================================================================
# Algorithm Class - Generic Algorithm Executor
# =============================================================================

class Algorithm:
    """
    Generic algorithm executor using the algorithm registry.
    
    This class provides a unified interface for executing any registered algorithm.
    NO switch statements - all dispatch goes through the registry.
    """
    
    def __init__(self, name: str, parameters: list[dict]):
        """
        Initialize algorithm executor.
        
        Args:
            name: Algorithm name (must be in registry)
            parameters: Algorithm-specific parameters
        """
        self.name = name.lower()
        self.parameters = parameters
        
        # Validate algorithm exists in registry
        algorithm = get_algorithm(self.name)
        if algorithm is None:
            available = list_algorithms()
            raise ValueError(
                f"Unknown algorithm: {self.name}. "
                f"Available algorithms: {available}"
            )
    
    def execute(
        self,
        observed_values: list[dict],
        bucket_key: Optional[str] = None,
        existing_baseline: Optional[dict] = None
    ) -> dict:
        """
        Execute the algorithm for training.
        
        Args:
            observed_values: List of observation dicts with dimensions
            bucket_key: Optional bucket key for bucket-aware training
            existing_baseline: Optional existing baseline for incremental training
            
        Returns:
            Training result dict
        """
        algorithm = get_algorithm(self.name)
        return algorithm.train(
            observed_values=observed_values,
            parameters=self.parameters,
            bucket_key=bucket_key,
            existing_baseline=existing_baseline
        )
    
    def detect(
        self,
        observation: dict,
        training_result: dict,
        bucket_key: Optional[str] = None
    ) -> dict:
        """
        Execute the algorithm for detection.
        
        Args:
            observation: Single observation dict with dimensions
            training_result: Training result from execute()
            bucket_key: Optional bucket key for bucket-aware detection
            
        Returns:
            Detection result with is_anomaly flag
        """
        algorithm = get_algorithm(self.name)
        return algorithm.detect(
            observation=observation,
            training_result=training_result,
            parameters=self.parameters,
            bucket_key=bucket_key
        )


# =============================================================================
# Training Functions
# =============================================================================

def run_training(
    config: dict,
    observed_values: list[dict],
    bucket_profile: Optional[dict] = None
) -> dict:
    """
    Run training for any algorithm using the registry.
    
    This is the ONLY training entry point. Uses TrainingOrchestrator for
    bucket-aware training when a bucket profile is provided.
    
    Args:
        config: KB configuration dict
        observed_values: List of observation dicts
        bucket_profile: Optional bucket profile for time-aware bucketing
        
    Returns:
        Training result dict
    """
    config_id = str(config.get("_id", config.get("config_id", "unknown")))
    
    # Extract algorithm info - support both old and new config formats
    algorithms = config.get("algorithms", [])
    if not algorithms:
        raise ValueError(f"No algorithms defined in config {config_id}")
    
    alg_config = algorithms[0]  # Currently support single algorithm
    
    # Support both formats: "name" (new) and "alg_name" (old)
    alg_name = alg_config.get("name") or alg_config.get("alg_name", "zscore")
    alg_name = alg_name.lower()
    
    # Support both formats for parameters:
    # New format: {"parameters": {"observed_values": [{"dimension": "x"}]}}
    # Old format: {"alg_parameters": [{"dimension": "x"}]}
    if "parameters" in alg_config:
        params = alg_config["parameters"]
        alg_params = params.get("observed_values", [])
    else:
        alg_params = alg_config.get("alg_parameters", [])
    
    logger.info(f"[TRAINING] Starting training for config {config_id}")
    logger.info(f"[TRAINING] Algorithm: {alg_name}, Observations: {len(observed_values)}")
    logger.info(f"[TRAINING] Parameters: {alg_params}")
    
    # Use TrainingOrchestrator for bucket-aware training
    orchestrator = TrainingOrchestrator(
        algorithm_name=alg_name,
        parameters=alg_params,
        bucket_profile=bucket_profile
    )
    
    # Extract timestamp field from query_mode
    query_mode = config.get("query_mode", {})
    timestamp_field = query_mode.get("timestamp_field", "@timestamp")
    
    result = orchestrator.train(
        observed_values=observed_values,
        timestamp_field=timestamp_field
    )
    
    logger.info(f"[TRAINING] Completed for config {config_id}")
    logger.info(f"[TRAINING] Buckets trained: {list(result.get('buckets', {}).keys())}")
    
    return result


def save_training_result(config_id: str, result: dict) -> str:
    """
    Save trained model to MongoDB.
    
    Args:
        config_id: Configuration ID
        result: Trained model dict
        
    Returns:
        Inserted document ID as string
    """
    collection = get_collection(TRAINED_MODELS_COLLECTION)
    
    # Add metadata
    result["config_id"] = ObjectId(config_id)
    result["created_at"] = datetime.now(timezone.utc)
    result["updated_at"] = datetime.now(timezone.utc)
    
    # Upsert to allow retraining
    existing = collection.find_one({"config_id": ObjectId(config_id)})
    if existing:
        collection.update_one(
            {"config_id": ObjectId(config_id)},
            {"$set": result}
        )
        invalidate_training_cache(config_id)
        return str(existing["_id"])
    else:
        inserted = collection.insert_one(result)
        return str(inserted.inserted_id)


# =============================================================================
# Detection Functions
# =============================================================================

def detect_anomaly(serie_to_detect: dict) -> Optional[dict]:
    """
    Detect anomalies for a single series using the algorithm registry.
    
    This is the ONLY detection entry point. Uses DetectionOrchestrator for
    bucket-aware detection.
    
    Args:
        serie_to_detect: Series document from MongoDB with:
            - config_id: Reference to KB config
            - observed_values: List of observations to analyze
            
    Returns:
        Detection result dict or None if no anomalies
    """
    config_id = str(serie_to_detect.get("config_id", "unknown"))
    
    logger.info(f"[DETECTION] Starting detection for config {config_id}")
    
    # Get training result
    training_result = get_training_result(config_id)
    if not training_result:
        logger.error(f"[DETECTION] No training result found for config {config_id}")
        return None
    
    # Get KB config from knowledge_base.kb_configs - the authoritative source
    try:
        kb_config = get_kb_collection().find_one({"_id": ObjectId(config_id)})
    except Exception:
        kb_config = None
    
    if not kb_config:
        # Fallback to training_config (old style)
        kb_config = get_collection(TRAINING_CONFIG_COLLECTION).find_one(
            {"kb_id": config_id}
        )
    
    if not kb_config:
        logger.error(f"[DETECTION] No KB config found for {config_id}")
        return None
    
    # Extract algorithm info - handle both schemas
    # New schema: kb_config.algorithm.name, kb_config.algorithm.parameters
    # Old schema: kb_config.algorithms[0].name, kb_config.algorithms[0].parameters.observed_values
    alg_config = kb_config.get("algorithm")  # New schema
    if not alg_config:
        # Old schema with algorithms list
        algorithms = kb_config.get("algorithms", [])
        if algorithms:
            alg_config = algorithms[0]
    
    if not alg_config:
        logger.error(f"[DETECTION] No algorithm in config {config_id}")
        return None
    
    # Get algorithm name
    alg_name = alg_config.get("name") or alg_config.get("alg_name", "zscore")
    alg_name = alg_name.lower()
    
    # Get algorithm parameters (dimensions)
    # New schema: algorithm.parameters is a list of {dimension, is_active}
    # Old schema: algorithms[0].parameters.observed_values
    if isinstance(alg_config.get("parameters"), list):
        alg_params = alg_config["parameters"]
    elif isinstance(alg_config.get("parameters"), dict):
        alg_params = alg_config["parameters"].get("observed_values", [])
    else:
        alg_params = alg_config.get("alg_parameters", [])
    
    logger.info(f"[DETECTION] Using algorithm: {alg_name}")
    
    # Get bucket profile if configured
    bucket_profile = None
    bucket_profile_id = kb_config.get("bucket_profile_id")
    if bucket_profile_id:
        bucket_profile = get_collection(BUCKET_PROFILES_COLLECTION).find_one(
            {"profile_id": bucket_profile_id}
        )
        if bucket_profile:
            logger.info(f"[DETECTION] Using bucket profile: {bucket_profile_id}")
    
    # Create detection orchestrator
    orchestrator = DetectionOrchestrator(
        algorithm_name=alg_name,
        parameters=alg_params,
        bucket_profile=bucket_profile,
        training_result=training_result
    )
    
    # Extract timestamp field
    query_mode = kb_config.get("query_mode", {})
    timestamp_field = query_mode.get("timestamp_field", "@timestamp")
    
    # Get observations to analyze
    observed_values = serie_to_detect.get("observed_values", [])
    if not observed_values:
        logger.warning(f"[DETECTION] No observations in series for {config_id}")
        return None
    
    logger.info(f"[DETECTION] Analyzing {len(observed_values)} observations")
    
    # Detect anomalies
    anomalies = []
    for obs in observed_values:
        result = orchestrator.detect(
            observation=obs,
            timestamp_field=timestamp_field
        )
        if result.get("is_anomaly", False):
            anomalies.append({
                "observation": obs,
                "detection_result": result
            })
    
    logger.info(f"[DETECTION] Found {len(anomalies)} anomalies")
    
    if not anomalies:
        return None
    
    # Build result
    detection_result = {
        "config_id": config_id,
        "config_name": kb_config.get("name", "unknown"),
        "algorithm": alg_name,
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
        "source_index": kb_config.get("source_index", "unknown")
    }
    
    # Post to insights API
    post_anomaly_to_insights(detection_result, kb_config)
    
    return detection_result


def post_anomaly_to_insights(detection_result: dict, kb_config: dict):
    """
    Post each anomaly to the Insights API in DocumentDto format.
    
    The insights API handles:
    1. Storing anomalies in Elasticsearch
    2. Sending email notifications (based on 'email' field in document)
    
    Args:
        detection_result: Detection result dict with anomalies list
        kb_config: KB configuration dict (for email settings)
    """
    insights_base_url = os.environ.get(
        "INSIGHTS_URL",
        "http://anomalies-insights:8081"
    )
    
    config_id = detection_result.get("config_id", "unknown")
    config_name = detection_result.get("config_name", "unknown")
    algorithm = detection_result.get("algorithm", "unknown")
    source_index = detection_result.get("source_index", "unknown")
    detected_at = detection_result.get("detected_at", datetime.now(timezone.utc).isoformat())
    
    # Get email recipients from anomaly_config
    anomaly_config = kb_config.get("anomaly_config") or {}
    user_emails = anomaly_config.get("user_emails", [])
    email_str = ",".join(user_emails) if user_emails else ""
    
    # Post each anomaly as a separate DocumentDto
    anomalies = detection_result.get("anomalies", [])
    posted_count = 0
    
    def serialize_for_json(obj):
        """Convert datetime and other non-JSON objects to strings."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, dict):
            return {k: serialize_for_json(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [serialize_for_json(v) for v in obj]
        return obj
    
    for anomaly in anomalies:
        observation = anomaly.get("observation", {})
        detection_details = anomaly.get("detection_result", {})
        
        # Get dimension results for algorithm_details
        # The algorithm returns 'dimensions' key, not 'dimension_results'
        dimension_results = detection_details.get("dimensions", {}) or detection_details.get("dimension_results", {})
        
        # Find the first anomalous dimension to use as primary metric
        primary_metric = None
        primary_value = None
        for dim_name, dim_result in dimension_results.items():
            if dim_result.get("is_anomaly", False):
                primary_metric = dim_name
                primary_value = dim_result.get("value")
                break
        
        if not primary_metric:
            # Fallback to first dimension
            for dim_name, dim_result in dimension_results.items():
                primary_metric = dim_name
                primary_value = dim_result.get("value")
                break
        
        # Get timestamp - could be 'bucket' or 'timestamp' depending on query_mode
        ts = observation.get("bucket") or observation.get("timestamp") or detection_details.get("timestamp") or detected_at
        # Ensure timestamp is string
        if isinstance(ts, datetime):
            ts = ts.isoformat()
        
        # Build DocumentDto matching Java DTO
        doc = {
            "algorithm": algorithm,
            "metric": primary_metric or "unknown",
            "text": f"Anomaly detected in {config_name}",
            "timestamp": ts,
            "value": primary_value if primary_value is not None else 0.0,  # Ensure not null
            "created_at": detected_at,
            "email": email_str,  # Insights API will send emails based on this
            "kbName": config_name,
            "bucket_key": detection_details.get("bucket_key"),
            "bucket_profile_id": kb_config.get("bucket_profile_id"),
            "algorithm_details": serialize_for_json(dimension_results)  # Serialized for JSON
        }
        
        # Post to insights API: /api/insights/dashboard/{kbId}/anomalies
        url = f"{insights_base_url}/api/insights/dashboard/{config_id}/anomalies"
        
        try:
            response = requests.post(url, json=doc, timeout=30)
            if response.status_code in (200, 201):
                posted_count += 1
                logger.info(f"[INSIGHTS] Posted anomaly for {primary_metric}={primary_value}")
            else:
                logger.warning(
                    f"[INSIGHTS] API returned {response.status_code}: {response.text}"
                )
        except requests.RequestException as e:
            logger.error(f"[INSIGHTS] Failed to post anomaly: {e}")
    
    if posted_count > 0:
        logger.info(f"[INSIGHTS] Posted {posted_count}/{len(anomalies)} anomalies to insights API")
        if email_str:
            logger.info(f"[INSIGHTS] Email notifications will be sent to: {email_str}")


# =============================================================================


# =============================================================================
# Change Stream Watchers
# =============================================================================

def load_training_series(config_id: str) -> list[dict]:
    """
    Load all training series for a config from MongoDB.
    
    The extractor stores series as individual documents with:
    - value: numeric value
    - timestamp: ISO timestamp
    - metadata.kbId: config ID
    - metadata.dim: dimension name
    - metadata.mode: 0 for training
    
    This function aggregates them into the format expected by training.
    
    Args:
        config_id: KB configuration ID
        
    Returns:
        List of observation dicts with dimensions as keys
    """
    collection = get_collection(SERIES_COLLECTION)
    
    # Get all series for this config (mode=0 is training)
    cursor = collection.find({
        "metadata.kbId": config_id,
        "metadata.mode": 0
    })
    
    # Aggregate by timestamp
    observations = {}
    for doc in cursor:
        ts = doc.get("timestamp")
        if ts is None:
            continue
        
        ts_key = ts.isoformat() if hasattr(ts, 'isoformat') else str(ts)
        
        if ts_key not in observations:
            observations[ts_key] = {"timestamp": ts}
        
        dim = doc.get("metadata", {}).get("dim", "value")
        observations[ts_key][dim] = doc.get("value")
    
    result = list(observations.values())
    logger.info(f"[TRAINING] Loaded {len(result)} observations for config {config_id}")
    return result


def watch_training_changes():
    """
    Watch for training_config documents with is_trained=false.
    
    Watches the training_config collection for inserts/updates where
    is_trained is false, indicating training needs to run.
    """
    logger.info("[WATCHER] Starting training change stream watcher")
    
    collection = get_collection(TRAINING_CONFIG_COLLECTION)
    
    # Watch for inserts and updates where is_trained becomes false
    pipeline = [
        {"$match": {
            "$or": [
                {"operationType": "insert"},
                {"operationType": "update"}
            ]
        }}
    ]
    
    try:
        with collection.watch(pipeline, full_document="updateLookup") as stream:
            for change in stream:
                try:
                    document = change.get("fullDocument", {})
                    
                    # Check if this is an untrained config
                    if document.get("is_trained", True):
                        continue  # Already trained, skip
                    
                    config_id = document.get("kb_id", "")
                    if not config_id:
                        config_id = str(document.get("_id", ""))
                    
                    if not config_id:
                        continue
                    
                    logger.info(f"[WATCHER] Training triggered for config {config_id}")
                    
                    # Load training series from the series collection
                    observed_values = load_training_series(config_id)
                    
                    if not observed_values:
                        logger.warning(f"[WATCHER] No training data for config {config_id}")
                        continue
                    
                    # Get bucket profile if configured
                    bucket_profile = None
                    # Note: bucket_profile_id would be in kb_configs, not training_config
                    # For now we skip bucket profiles in training_config
                    
                    # Run training using the training_config as our config
                    result = run_training(document, observed_values, bucket_profile)
                    
                    # Save result
                    result_id = save_training_result(config_id, result)
                    logger.info(f"[WATCHER] Saved training result: {result_id}")
                    
                    # Mark as trained
                    collection.update_one(
                        {"_id": document["_id"]},
                        {"$set": {"is_trained": True}}
                    )
                    logger.info(f"[WATCHER] Marked config {config_id} as trained")
                    
                except Exception as e:
                    logger.error(f"[WATCHER] Error processing training change: {e}")
                    import traceback
                    traceback.print_exc()
                    
    except Exception as e:
        logger.error(f"[WATCHER] Training change stream error: {e}")
        raise


def load_detection_observations(kb_id: str) -> list:
    """
    Load recent detection series from MongoDB and aggregate into observations.
    
    The extractor inserts individual series documents per dimension:
    {value: 123, timestamp: "...", metadata: {kbId: "...", dim: "...", mode: 1}}
    
    This function aggregates them into observation dicts:
    {timestamp: "...", dimension1: val1, dimension2: val2, ...}
    
    Args:
        kb_id: The KB configuration ID
        
    Returns:
        List of observation dicts
    """
    collection = get_collection(SERIES_COLLECTION)
    
    # Find all detection series for this kbId (mode=1)
    cursor = collection.find({
        "metadata.kbId": kb_id,
        "metadata.mode": 1
    }).sort("timestamp", 1)
    
    # Aggregate by timestamp
    observations_by_ts = {}
    for doc in cursor:
        ts = doc.get("timestamp")
        dim = doc.get("metadata", {}).get("dim")
        value = doc.get("value")
        
        if ts not in observations_by_ts:
            observations_by_ts[ts] = {"bucket": ts}
        
        if dim:
            observations_by_ts[ts][dim] = value
    
    return list(observations_by_ts.values())


def watch_detection_changes():
    """
    Watch for new detection series in MongoDB and trigger detection.
    
    Watches the 'series' collection for detection-type inserts (mode=1) and runs
    detection using the algorithm registry. Debounces to collect all dimensions
    before triggering detection.
    """
    import time
    
    logger.info("[WATCHER] Starting detection change stream watcher")
    
    collection = get_collection(SERIES_COLLECTION)
    
    # Watch for detection series (metadata.mode: 1 = DETECTION)
    pipeline = [
        {"$match": {
            "operationType": "insert",
            "fullDocument.metadata.mode": 1  # DETECTION mode
        }}
    ]
    
    # Track recently processed kbIds to debounce
    processed = {}
    DEBOUNCE_SECONDS = 5  # Wait for all dimensions to arrive
    
    try:
        with collection.watch(pipeline) as stream:
            for change in stream:
                try:
                    document = change.get("fullDocument", {})
                    metadata = document.get("metadata", {})
                    kb_id = metadata.get("kbId", "")
                    
                    if not kb_id:
                        continue
                    
                    # Debounce: skip if recently processed
                    now = time.time()
                    if kb_id in processed:
                        if now - processed[kb_id] < DEBOUNCE_SECONDS:
                            continue
                    
                    # Wait a moment for all dimensions to arrive
                    time.sleep(1)
                    
                    logger.info(f"[WATCHER] Detection triggered for kb {kb_id}")
                    processed[kb_id] = now
                    
                    # Load all detection observations for this kb
                    observations = load_detection_observations(kb_id)
                    
                    if not observations:
                        logger.warning(f"[WATCHER] No detection observations for kb {kb_id}")
                        continue
                    
                    logger.info(f"[WATCHER] Loaded {len(observations)} observations for kb {kb_id}")
                    
                    # Build series document for detect_anomaly
                    serie_to_detect = {
                        "config_id": kb_id,
                        "observed_values": observations
                    }
                    
                    # Run detection
                    result = detect_anomaly(serie_to_detect)
                    
                    if result:
                        logger.info(
                            f"[WATCHER] Detected {result['anomaly_count']} anomalies "
                            f"for kb {kb_id}"
                        )
                    else:
                        logger.info(f"[WATCHER] No anomalies for kb {kb_id}")
                    
                except Exception as e:
                    logger.error(f"[WATCHER] Error processing detection change: {e}")
                    import traceback
                    traceback.print_exc()
                    
    except Exception as e:
        logger.error(f"[WATCHER] Detection change stream error: {e}")
        raise


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Main entry point for the dispatcher."""
    import threading
    
    logger.info("=" * 60)
    logger.info("[DISPATCHER] Starting Algorithm-Agnostic DA Dispatcher")
    logger.info(f"[DISPATCHER] Available algorithms: {list_algorithms()}")
    logger.info("=" * 60)
    
    # Start watchers in separate threads
    training_thread = threading.Thread(
        target=watch_training_changes,
        name="TrainingWatcher",
        daemon=True
    )
    
    detection_thread = threading.Thread(
        target=watch_detection_changes,
        name="DetectionWatcher",
        daemon=True
    )
    
    training_thread.start()
    detection_thread.start()
    
    logger.info("[DISPATCHER] Watchers started, waiting for changes...")
    
    # Keep main thread alive
    try:
        training_thread.join()
        detection_thread.join()
    except KeyboardInterrupt:
        logger.info("[DISPATCHER] Shutting down...")


if __name__ == "__main__":
    main()
