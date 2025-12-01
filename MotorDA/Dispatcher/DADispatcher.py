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

# Algorithm registry - the ONLY way to access algorithms
from Dispatcher.algorithm_interface import get_algorithm, list_algorithms

# Orchestrators for bucket-aware training and detection
from Dispatcher.training_orchestrator import TrainingOrchestrator, DetectionOrchestrator

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

# Collection names
SERIES_COLLECTION = "series"
SERIES_RESULT_COLLECTION = "series_result"
TRAINING_CONFIG_COLLECTION = "training_config"
KB_CONFIG_COLLECTION = "training_config"  # KB configs are stored here
BUCKET_PROFILES_COLLECTION = "bucket_profiles"


def get_mongo_client() -> MongoClient:
    """Get MongoDB client with connection pooling."""
    return MongoClient(MONGO_URI)


def get_database():
    """Get the anomaly detection database."""
    client = get_mongo_client()
    return client[MONGO_DB]


def get_collection(name: str) -> Collection:
    """Get a specific collection."""
    db = get_database()
    return db[name]


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
    collection = get_collection(SERIES_RESULT_COLLECTION)
    result = collection.find_one({"config_id": ObjectId(config_id)})
    if result:
        # Convert ObjectId to string for JSON serialization
        result["_id"] = str(result["_id"])
        result["config_id"] = str(result["config_id"])
    return result


def get_training_result(config_id: str) -> Optional[dict]:
    """
    Get training result, using cache when possible.
    
    Args:
        config_id: The configuration ID
        
    Returns:
        Training result dict or None
    """
    collection = get_collection(SERIES_RESULT_COLLECTION)
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
    Save training result to MongoDB.
    
    Args:
        config_id: Configuration ID
        result: Training result dict
        
    Returns:
        Inserted document ID as string
    """
    collection = get_collection(SERIES_RESULT_COLLECTION)
    
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
    
    # Get KB config for algorithm info - lookup by kb_id field, not _id
    kb_config = get_collection(KB_CONFIG_COLLECTION).find_one(
        {"kb_id": config_id}
    )
    if not kb_config:
        # Try by _id as fallback
        try:
            kb_config = get_collection(KB_CONFIG_COLLECTION).find_one(
                {"_id": ObjectId(config_id)}
            )
        except Exception:
            pass
    
    if not kb_config:
        logger.error(f"[DETECTION] No KB config found for {config_id}")
        return None
    
    # Extract algorithm info - support both old and new config formats
    algorithms = kb_config.get("algorithms", [])
    if not algorithms:
        logger.error(f"[DETECTION] No algorithms in config {config_id}")
        return None
    
    alg_config = algorithms[0]
    
    # Support both formats: "name" (new) and "alg_name" (old)
    alg_name = alg_config.get("name") or alg_config.get("alg_name", "zscore")
    alg_name = alg_name.lower()
    
    # Support both formats for parameters
    if "parameters" in alg_config:
        params = alg_config["parameters"]
        alg_params = params.get("observed_values", [])
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
    Post anomaly detection result to the Insights API.
    
    Also handles email notifications if configured.
    
    Args:
        detection_result: Detection result dict
        kb_config: KB configuration dict (for email settings)
    """
    insights_url = os.environ.get(
        "INSIGHTS_URL",
        "http://anomalies-insights:8087/api/anomalies"
    )
    
    try:
        response = requests.post(
            insights_url,
            json=detection_result,
            timeout=30
        )
        if response.status_code in (200, 201):
            logger.info(f"[DETECTION] Posted anomaly to insights API")
        else:
            logger.warning(
                f"[DETECTION] Insights API returned {response.status_code}: "
                f"{response.text}"
            )
    except requests.RequestException as e:
        logger.error(f"[DETECTION] Failed to post to insights API: {e}")
    
    # Handle email notifications
    anomaly_config = kb_config.get("anomaly_config", {})
    user_emails = anomaly_config.get("user_emails", [])
    
    if user_emails:
        send_email_notifications(detection_result, user_emails)


def send_email_notifications(detection_result: dict, emails: list[str]):
    """
    Send email notifications for detected anomalies.
    
    Args:
        detection_result: Detection result dict
        emails: List of email addresses to notify
    """
    # Email service configuration
    email_service_url = os.environ.get("EMAIL_SERVICE_URL")
    
    if not email_service_url:
        logger.info(
            f"[EMAIL] Would notify {len(emails)} recipients about "
            f"{detection_result['anomaly_count']} anomalies "
            f"(EMAIL_SERVICE_URL not configured)"
        )
        return
    
    try:
        payload = {
            "recipients": emails,
            "subject": f"Anomaly Alert: {detection_result['config_name']}",
            "body": {
                "config_name": detection_result["config_name"],
                "anomaly_count": detection_result["anomaly_count"],
                "detected_at": detection_result["detected_at"],
                "algorithm": detection_result["algorithm"],
                "source_index": detection_result["source_index"]
            }
        }
        
        response = requests.post(
            email_service_url,
            json=payload,
            timeout=30
        )
        
        if response.status_code in (200, 201):
            logger.info(f"[EMAIL] Notified {len(emails)} recipients")
        else:
            logger.warning(f"[EMAIL] Service returned {response.status_code}")
            
    except requests.RequestException as e:
        logger.error(f"[EMAIL] Failed to send notifications: {e}")


# =============================================================================
# Change Stream Watchers
# =============================================================================

def watch_training_changes():
    """
    Watch for new training series in MongoDB and trigger training.
    
    Watches the 'series' collection for inserts and runs training
    for each new series using the algorithm registry.
    """
    logger.info("[WATCHER] Starting training change stream watcher")
    
    collection = get_collection(SERIES_COLLECTION)
    
    pipeline = [
        {"$match": {"operationType": "insert"}}
    ]
    
    try:
        with collection.watch(pipeline) as stream:
            for change in stream:
                try:
                    document = change.get("fullDocument", {})
                    config_id = str(document.get("config_id", ""))
                    
                    if not config_id:
                        continue
                    
                    logger.info(f"[WATCHER] New training series for config {config_id}")
                    
                    # Get KB config - lookup by kb_id field, not _id
                    kb_config = get_collection(KB_CONFIG_COLLECTION).find_one(
                        {"kb_id": config_id}
                    )
                    
                    if not kb_config:
                        # Try by _id as fallback
                        try:
                            kb_config = get_collection(KB_CONFIG_COLLECTION).find_one(
                                {"_id": ObjectId(config_id)}
                            )
                        except Exception:
                            pass
                    
                    if not kb_config:
                        logger.error(f"[WATCHER] KB config not found: {config_id}")
                        continue
                    
                    # Get bucket profile if configured
                    bucket_profile = None
                    bucket_profile_id = kb_config.get("bucket_profile_id")
                    if bucket_profile_id:
                        bucket_profile = get_collection(
                            BUCKET_PROFILES_COLLECTION
                        ).find_one({"profile_id": bucket_profile_id})
                    
                    # Run training
                    observed_values = document.get("observed_values", [])
                    result = run_training(kb_config, observed_values, bucket_profile)
                    
                    # Save result
                    result_id = save_training_result(config_id, result)
                    logger.info(f"[WATCHER] Saved training result: {result_id}")
                    
                except Exception as e:
                    logger.error(f"[WATCHER] Error processing training change: {e}")
                    
    except Exception as e:
        logger.error(f"[WATCHER] Training change stream error: {e}")
        raise


def watch_detection_changes():
    """
    Watch for new detection series in MongoDB and trigger detection.
    
    Watches the 'series' collection for detection-type inserts and runs
    detection using the algorithm registry.
    """
    logger.info("[WATCHER] Starting detection change stream watcher")
    
    collection = get_collection(SERIES_COLLECTION)
    
    # Watch for detection series (type: "detection")
    pipeline = [
        {"$match": {
            "operationType": "insert",
            "fullDocument.type": "detection"
        }}
    ]
    
    try:
        with collection.watch(pipeline) as stream:
            for change in stream:
                try:
                    document = change.get("fullDocument", {})
                    config_id = str(document.get("config_id", ""))
                    
                    if not config_id:
                        continue
                    
                    logger.info(f"[WATCHER] New detection series for config {config_id}")
                    
                    # Run detection using the generic detect_anomaly function
                    result = detect_anomaly(document)
                    
                    if result:
                        logger.info(
                            f"[WATCHER] Detected {result['anomaly_count']} anomalies "
                            f"for config {config_id}"
                        )
                    else:
                        logger.info(f"[WATCHER] No anomalies for config {config_id}")
                    
                except Exception as e:
                    logger.error(f"[WATCHER] Error processing detection change: {e}")
                    
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
