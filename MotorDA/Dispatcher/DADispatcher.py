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
from MotorDA.Dispatcher.algorithm_interface import (
    get_algorithm, 
    list_algorithms,
    resolve_algorithm_mode  # Phase 4: Mode resolution
)

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
def get_cached_training_result(kb_id: str, result_hash: str) -> Optional[dict]:
    """
    Load training result from MongoDB with LRU caching.
    
    Args:
        kb_id: The KB configuration ID
        result_hash: Hash of the result for cache invalidation
        
    Returns:
        Training result dict or None
    """
    collection = get_collection(TRAINED_MODELS_COLLECTION)
    result = collection.find_one({"kb_id": ObjectId(kb_id)})
    if result:
        # Convert ObjectId to string for JSON serialization
        result["_id"] = str(result["_id"])
        result["kb_id"] = str(result["kb_id"])
    return result


def get_training_result(kb_id: str) -> Optional[dict]:
    """
    Get trained model, using cache when possible.
    
    Args:
        kb_id: The KB configuration ID
        
    Returns:
        Trained model dict or None
    """
    collection = get_collection(TRAINED_MODELS_COLLECTION)
    result = collection.find_one({"kb_id": ObjectId(kb_id)})
    
    if not result:
        return None
    
    # Create hash for cache key (using updated_at or _id)
    result_hash = str(result.get("updated_at", result["_id"]))
    
    return get_cached_training_result(kb_id, result_hash)


def invalidate_training_cache(kb_id: str):
    """Invalidate cache for a specific KB configuration."""
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
        existing_model: Optional[dict] = None
    ) -> dict:
        """
        Execute the algorithm for training.
        
        Args:
            observed_values: List of observation dicts with dimensions
            bucket_key: Optional bucket key for bucket-aware training
            existing_model: Optional existing model for incremental training
            
        Returns:
            Training result dict
        """
        algorithm = get_algorithm(self.name)
        return algorithm.train(
            observed_values=observed_values,
            parameters=self.parameters,
            bucket_key=bucket_key,
            existing_model=existing_model
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
    bucket_profile: Optional[dict] = None,
    timestamp_field: str = "@timestamp"
) -> dict:
    """
    Run training for any algorithm using the registry.
    
    This is the ONLY training entry point. Uses TrainingOrchestrator for
    bucket-aware training when a bucket profile is provided.
    
    Resolves algorithm mode (single vs multi-dimensional) and passes to orchestrator.
    
    Args:
        config: KB configuration dict
        observed_values: List of observation dicts
        bucket_profile: Optional bucket profile for time-aware bucketing
        timestamp_field: Field name containing timestamps in observations
        
    Returns:
        Training result dict
    """
    kb_id = str(config.get("_id", config.get("kb_id", "unknown")))
    
    # Extract algorithm info - support both old and new config formats
    algorithms = config.get("algorithms", [])
    if not algorithms:
        raise ValueError(f"No algorithms defined in config {kb_id}")
    
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
    
    # ─────────────────────────────────────────────────────────────────────────────
    # Phase 4: Resolve algorithm mode before creating orchestrator
    # ─────────────────────────────────────────────────────────────────────────────
    is_multi_dimensional = resolve_algorithm_mode(alg_name, alg_params)
    
    logger.info(f"[TRAINING] Starting training for KB {kb_id}")
    logger.info(f"[TRAINING] Algorithm: {alg_name}, Mode: {'multi-dimensional' if is_multi_dimensional else 'single-dimensional'}")
    logger.info(f"[TRAINING] Observations: {len(observed_values)}")
    logger.info(f"[TRAINING] Parameters: {alg_params}")
    logger.info(f"[TRAINING] Bucket profile passed: {bucket_profile is not None}")
    logger.info(f"[TRAINING] Timestamp field: {timestamp_field}")
    if bucket_profile:
        logger.info(f"[TRAINING] Bucket profile _id: {bucket_profile.get('_id')}")
    
    # Use TrainingOrchestrator for bucket-aware training
    orchestrator = TrainingOrchestrator(
        algorithm_name=alg_name,
        parameters=alg_params,
        bucket_profile=bucket_profile,
        is_multi_dimensional=is_multi_dimensional  # Phase 4: Pass mode to orchestrator
    )
    
    # Use the timestamp_field passed from caller (from KB config query_mode)
    result = orchestrator.train(
        observed_values=observed_values,
        timestamp_field=timestamp_field
    )
    
    logger.info(f"[TRAINING] Completed for KB {kb_id}")
    logger.info(f"[TRAINING] Buckets trained: {list(result.get('buckets', {}).keys())}")
    
    return result


def save_training_result(kb_id: str, result: dict) -> str:
    """
    Save trained model to MongoDB.
    
    Args:
        kb_id: KB configuration ID
        result: Trained model dict
        
    Returns:
        Inserted document ID as string
    """
    collection = get_collection(TRAINED_MODELS_COLLECTION)
    
    # Add metadata
    result["kb_id"] = ObjectId(kb_id)
    result["created_at"] = datetime.now(timezone.utc)
    result["updated_at"] = datetime.now(timezone.utc)
    
    # Upsert to allow retraining
    existing = collection.find_one({"kb_id": ObjectId(kb_id)})
    if existing:
        collection.update_one(
            {"kb_id": ObjectId(kb_id)},
            {"$set": result}
        )
        invalidate_training_cache(kb_id)
        return str(existing["_id"])
    else:
        inserted = collection.insert_one(result)
        return str(inserted.inserted_id)


def cleanup_training_series(kb_id: str) -> int:
    """
    Delete training series data after successful training.
    
    Training series (mode=0) are temporary - once the model is trained,
    the raw series data is no longer needed. This prevents stale data
    accumulation when training ranges change.
    
    Args:
        kb_id: KB configuration ID
        
    Returns:
        Number of documents deleted
    """
    collection = get_collection(SERIES_COLLECTION)
    
    result = collection.delete_many({
        "metadata.kbId": kb_id,
        "metadata.mode": 0  # Training mode only
    })
    
    deleted_count = result.deleted_count
    if deleted_count > 0:
        logger.info(f"[CLEANUP] Deleted {deleted_count} training series for KB {kb_id}")
    
    return deleted_count


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
            - kb_id: Reference to KB config
            - observed_values: List of observations to analyze
            
    Returns:
        Detection result dict or None if no anomalies
    """
    kb_id = str(serie_to_detect.get("kb_id", serie_to_detect.get("config_id", "unknown")))
    
    logger.info(f"[DETECTION] Starting detection for KB {kb_id}")
    
    # Get training result
    training_result = get_training_result(kb_id)
    if not training_result:
        logger.error(f"[DETECTION] No training result found for KB {kb_id}")
        return None
    
    # Get KB config from knowledge_base.kb_configs - the authoritative source
    try:
        kb_config = get_kb_collection().find_one({"_id": ObjectId(kb_id)})
    except Exception:
        kb_config = None
    
    #TODO: FIX remove fallback to old training_config
    if not kb_config:
        # Fallback to training_config (old style)
        kb_config = get_collection(TRAINING_CONFIG_COLLECTION).find_one(
            {"kb_id": kb_id}
        )
    
    if not kb_config:
        logger.error(f"[DETECTION] No KB config found for {kb_id}")
        return None
    
    # Extract algorithm info - handle both schemas
    # New schema: kb_config.algorithm.name, kb_config.algorithm.parameters
    # Old schema: kb_config.algorithms[0].name, kb_config.algorithms[0].parameters.observed_values
    alg_config = kb_config.get("algorithm")  # New schema
    
    #TODO: FIX remove fallback to old schema
    if not alg_config:
        # Old schema with algorithms list
        algorithms = kb_config.get("algorithms", [])
        if algorithms:
            alg_config = algorithms[0]
    
    if not alg_config:
        logger.error(f"[DETECTION] No algorithm in KB {kb_id}")
        return None
    

    # Get algorithm name
    # TODO: Remove fallback to ZScore
    alg_name = alg_config.get("name") or alg_config.get("alg_name", "zscore")
    alg_name = alg_name.lower()
    
    # Get algorithm parameters (dimensions)
    # New schema: algorithm.parameters is a list of {dimension, is_active}
    # Old schema: algorithms[0].parameters.observed_values

    # TODO: Remove ifs only alg_params = alg_config["parameters"] remains.
    if isinstance(alg_config.get("parameters"), list):
        alg_params = alg_config["parameters"]
    elif isinstance(alg_config.get("parameters"), dict):
        alg_params = alg_config["parameters"].get("observed_values", [])
    else:
        alg_params = alg_config.get("alg_parameters", [])
    
    logger.info(f"[DETECTION] Using algorithm: {alg_name}")
    
    # ─────────────────────────────────────────────────────────────────────────────
    # Phase 4: Resolve algorithm mode before creating orchestrator
    # ─────────────────────────────────────────────────────────────────────────────
    is_multi_dimensional = resolve_algorithm_mode(alg_name, alg_params)
    logger.info(f"[DETECTION] Algorithm mode: {'multi-dimensional' if is_multi_dimensional else 'single-dimensional'}")
    
    # Get bucket profile if configured
    bucket_profile = None
    bucket_profile_id = kb_config.get("bucket_profile_id")
    if bucket_profile_id:
        bucket_profile = get_collection(BUCKET_PROFILES_COLLECTION).find_one(
            {"profile_id": bucket_profile_id}
        )
        if bucket_profile:
            logger.info(f"[DETECTION] Using bucket profile: {bucket_profile_id}")
        else:
            logger.warning(f"[DETECTION] Bucket profile not found: {bucket_profile_id}")
    
    # Create detection orchestrator with algorithm mode
    orchestrator = DetectionOrchestrator(
        algorithm_name=alg_name,
        parameters=alg_params,
        bucket_profile=bucket_profile,
        training_result=training_result,
        is_multi_dimensional=is_multi_dimensional  # Phase 4: Pass mode to orchestrator
    )
    
    # Extract timestamp field
    query_mode = kb_config.get("query_mode", {})
    timestamp_field = query_mode.get("timestamp_field", "@timestamp")
    
    # Get observations to analyze
    #TODO: change to dimensions it is confusing. 
    observed_values = serie_to_detect.get("observed_values", [])
    if not observed_values:
        logger.warning(f"[DETECTION] No observations in series for KB {kb_id}")
        return None
    
    logger.info(f"[DETECTION] Analyzing {len(observed_values)} observations")
    
    # Detect anomalies
    #TODO: change to dimensions and we don't have multiple dimensions in one kb. 
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
        "kb_id": kb_id,
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
    
    kb_id = detection_result.get("kb_id", "unknown")
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
        # Single-dim algorithms return 'dimensions' or 'dimension_results'
        # Multi-dim algorithms return 'dimension_contributions'
        dimension_results = (
            detection_details.get("dimensions", {}) or 
            detection_details.get("dimension_results", {}) or
            detection_details.get("dimension_contributions", {})
        )
        
        # For multi-dim, check anomalous_dimensions list
        anomalous_dims = detection_details.get("anomalous_dimensions", [])
        
        # Find the first anomalous dimension to use as primary metric
        primary_metric = None
        primary_value = None
        
        # Try from anomalous_dimensions list first (multi-dim)
        if anomalous_dims and dimension_results:
            primary_metric = anomalous_dims[0]
            dim_data = dimension_results.get(primary_metric, {})
            primary_value = dim_data.get("value")
        
        # Fallback: look for is_anomaly flag in dimension_results
        if not primary_metric:
            for dim_name, dim_result in dimension_results.items():
                if dim_result.get("is_anomaly", False):
                    primary_metric = dim_name
                    primary_value = dim_result.get("value")
                    break
        
        # Fallback: use first dimension
        if not primary_metric:
            for dim_name, dim_result in dimension_results.items():
                primary_metric = dim_name
                primary_value = dim_result.get("value")
                break
        
        # Multi-dim fallback: use distance as value if no dimension found
        if not primary_metric and detection_details.get("distance") is not None:
            # Use dimensions list if available, otherwise fall back to "multi_dimensional"
            dimensions = detection_details.get("dimensions", [])
            primary_metric = ",".join(dimensions) if dimensions else "multi_dimensional"
            primary_value = detection_details.get("distance")
        
        # Get timestamp - could be 'bucket' or 'timestamp' depending on query_mode
        ts = observation.get("bucket") or observation.get("timestamp") or detection_details.get("timestamp") or detected_at
        # Ensure timestamp is string
        if isinstance(ts, datetime):
            ts = ts.isoformat()
        #TODO: remove hardcoded fields for dashboard, must be defined by each algorithm from line 551 to 580

        # Extract top-level score for Kibana dashboard compatibility
        # The dashboard expects flat fields like algorithm_details.z_score
        primary_details = dimension_results.get(primary_metric, {}) if primary_metric else {}
        flat_z_score = primary_details.get("z_score")
        flat_iqr_score = primary_details.get("iqr_score")
        flat_lower_bound = primary_details.get("lower_bound")
        flat_upper_bound = primary_details.get("upper_bound")
        flat_mean = primary_details.get("mean")
        flat_std = primary_details.get("std")
        flat_threshold = primary_details.get("threshold")
        
        # Build algorithm_details with both nested (per-dimension) and flat (for Kibana) fields
        algorithm_details_with_flat = serialize_for_json(dimension_results)
        # Add flat fields for Kibana dashboard visualization
        if flat_z_score is not None:
            algorithm_details_with_flat["z_score"] = flat_z_score
        if flat_iqr_score is not None:
            algorithm_details_with_flat["iqr_score"] = flat_iqr_score
        if flat_lower_bound is not None:
            algorithm_details_with_flat["lower_bound"] = flat_lower_bound
        if flat_upper_bound is not None:
            algorithm_details_with_flat["upper_bound"] = flat_upper_bound
        if flat_mean is not None:
            algorithm_details_with_flat["mean"] = flat_mean
        if flat_std is not None:
            algorithm_details_with_flat["std"] = flat_std
        if flat_threshold is not None:
            algorithm_details_with_flat["threshold"] = flat_threshold
        # End of TODO

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
            "algorithm_details": algorithm_details_with_flat  # Now includes flat fields for Kibana
        }
        
        # Post to insights API: /api/insights/dashboard/{kbId}/anomalies
        url = f"{insights_base_url}/api/insights/dashboard/{kb_id}/anomalies"
        
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

def load_training_series(kb_id: str) -> list[dict]:
    """
    Load all training series for a config from MongoDB.
    
    The extractor stores series as individual documents with:
    - value: numeric value
    - timestamp: ISO timestamp
    - metadata.kbId: KB configuration ID
    - metadata.dim: dimension name
    - metadata.mode: 0 for training
    
    This function aggregates them into the format expected by training.
    
    Args:
        kb_id: KB configuration ID
        
    Returns:
        List of observation dicts with dimensions as keys
    """
    collection = get_collection(SERIES_COLLECTION)
    
    # Get all series for this config (mode=0 is training)
    cursor = collection.find({
        "metadata.kbId": kb_id,
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
    logger.info(f"[TRAINING] Loaded {len(result)} observations for KB {kb_id}")
    return result


def watch_training_changes():
    """
    Watch for training_config documents with is_trained=false.
    
    Watches the training_config collection for inserts/updates where
    is_trained is false, indicating training needs to run.
    """
    logger.info("[WATCHER] Starting training change stream watcher")
    
    collection = get_collection(TRAINING_CONFIG_COLLECTION)
    
    # Watch for inserts, updates, AND replaces where is_trained becomes false
    # NOTE: Spring Data MongoDB's save() with existing _id triggers a REPLACE, not UPDATE
    pipeline = [
        {"$match": {
            "$or": [
                {"operationType": "insert"},
                {"operationType": "update"},
                {"operationType": "replace"}
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
                    
                    kb_id = document.get("kb_id", "")
                    if not kb_id:
                        kb_id = str(document.get("_id", ""))
                    
                    if not kb_id:
                        continue
                    
                    logger.info(f"[WATCHER] Training triggered for KB {kb_id}")
                    
                    # Load training series from the series collection
                    
                    #TODO: change to dimensions
                    observed_values = load_training_series(kb_id)
                    
                    if not observed_values:
                        logger.warning(f"[WATCHER] No training data for KB {kb_id}")
                        continue
                    
                    # Get bucket profile and query_mode from KB config (same MongoDB, O(1) lookup by _id)
                    bucket_profile = None
                    timestamp_field = "@timestamp"  # Default
                    try:
                        kb_config = get_kb_collection().find_one({"_id": ObjectId(kb_id)})
                        if kb_config:
                            # Get timestamp_field from query_mode
                            query_mode = kb_config.get("query_mode", {})
                            timestamp_field = query_mode.get("timestamp_field", "@timestamp")
                            logger.info(f"[WATCHER] KB config timestamp_field: {timestamp_field}")
                            
                            # Get bucket profile from knowledge_base DB (same as KB configs)
                            bucket_profile_id = kb_config.get("bucket_profile_id")
                            logger.info(f"[WATCHER] KB config bucket_profile_id: {bucket_profile_id}")
                            if bucket_profile_id:
                                bucket_profile = get_kb_database()[BUCKET_PROFILES_COLLECTION].find_one(
                                    {"$or": [{"profile_id": bucket_profile_id}, {"_id": bucket_profile_id}]}
                                )
                                logger.info(f"[WATCHER] Bucket profile lookup result: {bucket_profile is not None}")
                                if bucket_profile:
                                    logger.info(f"[WATCHER] Using bucket profile: {bucket_profile_id}")
                        else:
                            logger.warning(f"[WATCHER] KB config not found for {kb_id}")
                    except Exception as e:
                        logger.warning(f"[WATCHER] Failed to load bucket profile: {e}")
                        import traceback
                        traceback.print_exc()
                    
                    # Run training using the training_config as our config
                    result = run_training(document, observed_values, bucket_profile, timestamp_field)
                    
                    # Save result
                    result_id = save_training_result(kb_id, result)
                    logger.info(f"[WATCHER] Saved training result: {result_id}")
                    
                    # Cleanup training series - no longer needed after successful training
                    cleanup_training_series(kb_id)
                    
                    # Mark as trained
                    collection.update_one(
                        {"_id": document["_id"]},
                        {"$set": {"is_trained": True}}
                    )
                    logger.info(f"[WATCHER] Marked KB {kb_id} as trained")
                    
                except Exception as e:
                    logger.error(f"[WATCHER] Error processing training change: {e}")
                    import traceback
                    traceback.print_exc()
                    
    except Exception as e:
        logger.error(f"[WATCHER] Training change stream error: {e}")
        raise

#TODO: unused
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


def _detect_single_series(serie_data: dict) -> Optional[dict]:
    """
    Process a single series document for detection in a worker process.
    
    This function is designed to run in a ProcessPoolExecutor worker.
    It creates its own database connections since they can't be pickled.
    
    Args:
        serie_data: Dict with kb_id and observation data (pickle-safe)
        
    Returns:
        Detection result or None
    """
    # Re-import in worker process (ProcessPoolExecutor spawns new processes)
    import logging
    from datetime import datetime, timezone
    
    worker_logger = logging.getLogger(__name__)
    
    try:
        kb_id = serie_data.get("kb_id", "")
        observation = serie_data.get("observation", {})
        
        if not kb_id:
            return None
        
        # Create series for detection
        serie_to_detect = {
            "kb_id": kb_id,
            "observed_values": [observation]
        }
        
        result = detect_anomaly(serie_to_detect)
        return result
        
    except Exception as e:
        worker_logger.error(f"[WORKER] Detection error: {e}")
        import traceback
        traceback.print_exc()
        return None


def watch_detection_changes(workers):
    """
    Watch for new detection series in MongoDB and trigger detection.
    
    Watches the 'series' collection for detection-type inserts (mode=1) and submits
    each document to the ProcessPoolExecutor for parallel detection.
    
    Args:
        workers: ProcessPoolExecutor for parallel detection
    """
    logger.info("[WATCHER] Starting detection change stream watcher")
    
    collection = get_collection(SERIES_COLLECTION)
    
    # Watch for detection series (metadata.mode: 1 = DETECTION)
    pipeline = [
        {"$match": {
            "operationType": "insert",
            "fullDocument.metadata.mode": 1  # DETECTION mode
        }}
    ]
    
    try:
        with collection.watch(pipeline) as stream:
            for change in stream:
                try:
                    serie_doc = change.get("fullDocument")
                    
                    if not serie_doc:
                        continue
                    
                    metadata = serie_doc.get("metadata", {})
                    kb_id = metadata.get("kbId", "")
                    dim = metadata.get("dim", "unknown")
                    value = serie_doc.get("value")
                    ts = serie_doc.get("timestamp")
                    
                    if not kb_id:
                        continue
                    
                    # Build pickle-safe data for worker process
                    observation = {"bucket": ts, dim: value}
                    serie_data = {
                        "kb_id": kb_id,
                        "observation": observation
                    }
                    
                    logger.debug(f"[WATCHER] Submitting detection for kb={kb_id} dim={dim}")
                    
                    # Submit to process pool for parallel execution
                    workers.submit(_detect_single_series, serie_data)
                    
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
    """Main entry point for the dispatcher.
    
    Uses two architectures:
    1. Training: Single watcher for training_config changes (legacy, works well)
    2. Detection: Per-KB Worker architecture via DispatcherManager (Phase 6)
    
    The DispatcherManager spawns one KBWorker per active KB config,
    each with a filtered change stream for isolated detection processing.
    """
    import threading
    import os
    
    # Import the Per-KB Worker architecture
    from MotorDA.Dispatcher.kb_worker import DispatcherManager
    
    logger.info("=" * 60)
    logger.info("[DISPATCHER] Starting Algorithm-Agnostic DA Dispatcher")
    logger.info(f"[DISPATCHER] Available algorithms: {list_algorithms()}")
    logger.info("[DISPATCHER] Using Per-KB Worker Architecture for Detection")
    logger.info("=" * 60)
    
    # Callback for anomaly detection results
    def on_anomaly_detected(detection_result: dict):
        """Handle detected anomalies from KBWorkers."""
        kb_id = detection_result.get("kb_id", "unknown")
        kb_name = detection_result.get("kb_name", "unknown")
        
        logger.info(f"[DISPATCHER] Anomaly from KBWorker: kb={kb_name}")
        
        # Get full KB config for posting to insights
        try:
            kb_config = get_kb_collection().find_one({"_id": ObjectId(kb_id)})
            if kb_config:
                # Build detection result in expected format
                full_result = {
                    "kb_id": kb_id,
                    "config_name": kb_name,
                    "algorithm": detection_result.get("algorithm", "unknown"),
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                    "anomaly_count": 1,
                    "anomalies": [{
                        "observation": detection_result.get("observation", {}),
                        "detection_result": detection_result
                    }],
                    "source_index": kb_config.get("source_index", "unknown")
                }
                
                # Post to insights API
                post_anomaly_to_insights(full_result, kb_config)
        except Exception as e:
            logger.error(f"[DISPATCHER] Error posting anomaly: {e}")
    
    # Create DispatcherManager for Per-KB Worker architecture
    dispatcher_manager = DispatcherManager(
        mongo_uri=MONGO_URI,
        anomaly_db_name=MONGO_DB,
        kb_db_name=KB_DB,
        on_anomaly_callback=on_anomaly_detected
    )
    
    # Start training watcher (legacy, single thread)
    training_thread = threading.Thread(
        target=watch_training_changes,
        name="TrainingWatcher",
        daemon=True
    )
    training_thread.start()
    
    # Start DispatcherManager (spawns KBWorkers for detection)
    dispatcher_manager.start()
    
    logger.info("[DISPATCHER] Training watcher and DispatcherManager started")
    logger.info("[DISPATCHER] Waiting for changes...")
    
    # Keep main thread alive
    try:
        training_thread.join()
    except KeyboardInterrupt:
        logger.info("[DISPATCHER] Shutting down...")
        dispatcher_manager.stop()


if __name__ == "__main__":
    main()
