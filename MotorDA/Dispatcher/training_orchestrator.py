"""Training Orchestrator - Algorithm-Agnostic Training and Detection.

This module provides bucket-aware training and detection orchestration.
It is completely algorithm-agnostic and uses the algorithm registry for all operations.

Design:
- TrainingOrchestrator: Groups data by bucket, trains baselines per bucket
- DetectionOrchestrator: Resolves bucket for each observation, uses correct baseline

NO LEGACY CODE - All algorithm dispatch goes through algorithm_interface.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone as tz
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

# Algorithm registry - the ONLY way to access algorithms
from Dispatcher.algorithm_interface import get_algorithm

# Bucket resolver for time-context bucketing
from Dispatcher.bucket_resolver import BucketResolver

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def parse_timestamp(ts_value: Any) -> Optional[datetime]:
    """Parse a timestamp from various formats.
    
    Args:
        ts_value: Timestamp as string, datetime, or epoch
        
    Returns:
        datetime object or None if parsing fails
    """
    if ts_value is None:
        return None
    
    if isinstance(ts_value, datetime):
        return ts_value
    
    if isinstance(ts_value, (int, float)):
        # Assume epoch milliseconds if > 1e12
        if ts_value > 1e12:
            ts_value = ts_value / 1000
        return datetime.fromtimestamp(ts_value, tz=tz.utc)
    
    if isinstance(ts_value, str):
        # Try various formats
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(ts_value, fmt).replace(tzinfo=tz.utc)
            except ValueError:
                continue
    
    return None


@dataclass
class TrainingOrchestrator:
    """Orchestrates training with bucket-aware data grouping.
    
    This orchestrator:
    1. Groups observations by bucket key using BucketResolver
    2. Delegates training to the algorithm via registry
    3. Returns bucket-keyed training results
    
    Completely algorithm-agnostic - uses algorithm registry.
    """
    
    algorithm_name: str
    parameters: List[Dict[str, Any]]
    bucket_profile: Optional[Dict[str, Any]] = None
    bucket_resolver: Optional[BucketResolver] = field(default=None, init=False)
    
    def __post_init__(self):
        """Initialize bucket resolver if profile provided."""
        if self.bucket_profile:
            try:
                self.bucket_resolver = BucketResolver.from_dict(self.bucket_profile)
                logger.info(f"[ORCHESTRATOR] Loaded bucket profile: {self.bucket_profile.get('profile_id')}")
            except Exception as e:
                logger.warning(f"[ORCHESTRATOR] Failed to create bucket resolver: {e}")
                self.bucket_resolver = None
    
    def resolve_bucket_key(self, ts: datetime) -> str:
        """Resolve a timestamp to its bucket key.
        
        Args:
            ts: Timestamp (should be UTC)
        
        Returns:
            Bucket key string (e.g., "workday_14" or "global_default")
        """
        if self.bucket_resolver is None:
            return "global_default"
        return self.bucket_resolver.resolve(ts)
    
    def group_by_bucket(
        self,
        observed_values: List[Dict[str, Any]],
        timestamp_field: str = "@timestamp"
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group observations by their resolved bucket keys.
        
        Args:
            observed_values: List of observation dicts
            timestamp_field: Name of timestamp field
        
        Returns:
            Dict mapping bucket_key -> list of observations
        """
        if not observed_values:
            return {}
        
        groups: Dict[str, List[Dict[str, Any]]] = {}
        
        for obs in observed_values:
            ts_val = obs.get(timestamp_field)
            ts = parse_timestamp(ts_val)
            
            if ts is None:
                bucket_key = "global_default"
            else:
                bucket_key = self.resolve_bucket_key(ts)
            
            if bucket_key not in groups:
                groups[bucket_key] = []
            groups[bucket_key].append(obs)
        
        return groups
    
    def train(
        self,
        observed_values: List[Dict[str, Any]],
        timestamp_field: str = "@timestamp",
        percentile: float = 99.5
    ) -> Dict[str, Any]:
        """Train baselines for all buckets.
        
        This is the main training entry point. It:
        1. Groups observations by bucket key
        2. Trains a baseline per bucket using the algorithm
        3. Creates global fallback from all data
        4. Returns bucket-keyed training result
        
        Args:
            observed_values: List of observation dicts
            timestamp_field: Timestamp field name
            percentile: Percentile for threshold calculation
        
        Returns:
            Training result dict:
            {
                "algorithm": "zscore",
                "bucket_profile_id": "...",
                "buckets": {
                    "workday_14": {dimension: baseline_dict, ...},
                    ...
                },
                "global_fallback": {dimension: baseline_dict, ...}
            }
        """
        algorithm = get_algorithm(self.algorithm_name)
        
        logger.info(f"[ORCHESTRATOR] Training with algorithm '{self.algorithm_name}'")
        logger.info(f"[ORCHESTRATOR] Observations: {len(observed_values)}")
        
        # Group by bucket
        groups = self.group_by_bucket(observed_values, timestamp_field)
        logger.info(f"[ORCHESTRATOR] Buckets: {list(groups.keys())}")
        
        # Train global fallback from ALL data
        global_fallback = algorithm.train_multi_dimension(
            observed_values=observed_values,
            parameters=self.parameters,
            percentile=percentile
        )
        logger.info(f"[ORCHESTRATOR] Global fallback trained with dimensions: {list(global_fallback.keys())}")
        
        # Train per-bucket baselines
        buckets = {}
        for bucket_key, bucket_obs in groups.items():
            logger.info(f"[ORCHESTRATOR] Training bucket '{bucket_key}' with {len(bucket_obs)} observations")
            
            if len(bucket_obs) < 3:  # Minimum for meaningful stats
                logger.warning(f"[ORCHESTRATOR] Bucket '{bucket_key}' has insufficient data, using global fallback")
                buckets[bucket_key] = {
                    "baselines": global_fallback,
                    "n_observations": len(bucket_obs),
                    "sufficient_data": False
                }
            else:
                bucket_baseline = algorithm.train_multi_dimension(
                    observed_values=bucket_obs,
                    parameters=self.parameters,
                    percentile=percentile
                )
                buckets[bucket_key] = {
                    "baselines": bucket_baseline,
                    "n_observations": len(bucket_obs),
                    "sufficient_data": True
                }
        
        result = {
            "algorithm": self.algorithm_name,
            "bucket_profile_id": self.bucket_profile.get("profile_id") if self.bucket_profile else None,
            "buckets": buckets,
            "global_fallback": global_fallback,
            "n_total_observations": len(observed_values),
            "parameters": self.parameters
        }
        
        logger.info(f"[ORCHESTRATOR] Training complete. Buckets: {len(buckets)}")
        return result


@dataclass
class DetectionOrchestrator:
    """Orchestrates detection with bucket-aware baseline lookup.
    
    This orchestrator:
    1. Resolves observation timestamp to bucket key
    2. Gets the correct baseline for that bucket
    3. Delegates detection to the algorithm
    
    Completely algorithm-agnostic - uses algorithm registry.
    """
    
    algorithm_name: str
    parameters: List[Dict[str, Any]]
    training_result: Dict[str, Any]
    bucket_profile: Optional[Dict[str, Any]] = None
    bucket_resolver: Optional[BucketResolver] = field(default=None, init=False)
    
    def __post_init__(self):
        """Initialize bucket resolver if profile provided."""
        if self.bucket_profile:
            try:
                self.bucket_resolver = BucketResolver.from_dict(self.bucket_profile)
            except Exception as e:
                logger.warning(f"[DETECTION] Failed to create bucket resolver: {e}")
                self.bucket_resolver = None
    
    def resolve_bucket_key(self, ts: datetime) -> str:
        """Resolve a timestamp to its bucket key."""
        if self.bucket_resolver is None:
            return "global_default"
        return self.bucket_resolver.resolve(ts)
    
    def get_baseline_for_bucket(self, bucket_key: str) -> Dict[str, Dict[str, Any]]:
        """Get the baseline dict for a specific bucket.
        
        Falls back to global_fallback if bucket not found.
        
        Args:
            bucket_key: The bucket key
            
        Returns:
            Dict of dimension -> baseline_dict
        """
        buckets = self.training_result.get("buckets", {})
        global_fallback = self.training_result.get("global_fallback", {})
        
        if bucket_key in buckets:
            bucket_data = buckets[bucket_key]
            return bucket_data.get("baselines", bucket_data)
        
        # Fallback to global
        logger.info(f"[DETECTION] Bucket '{bucket_key}' not found, using global fallback")
        return global_fallback
    
    def detect(
        self,
        observation: Dict[str, Any],
        timestamp_field: str = "@timestamp"
    ) -> Dict[str, Any]:
        """Detect if an observation is anomalous.
        
        Args:
            observation: Observation dict with dimensions and timestamp
            timestamp_field: Timestamp field name
        
        Returns:
            Detection result dict with is_anomaly, dimension_results
        """
        algorithm = get_algorithm(self.algorithm_name)
        
        # Get timestamp and resolve bucket
        ts_val = observation.get(timestamp_field)
        ts = parse_timestamp(ts_val)
        
        if ts is None:
            bucket_key = "global_default"
        else:
            bucket_key = self.resolve_bucket_key(ts)
        
        # Get baseline for this bucket
        baselines = self.get_baseline_for_bucket(bucket_key)
        
        # Detect using algorithm
        result = algorithm.detect_multi_dimension(
            observation=observation,
            baselines=baselines,
            parameters=self.parameters
        )
        
        # Add metadata
        result["bucket_key"] = bucket_key
        result["timestamp"] = ts.isoformat() if ts else None
        
        return result
    
    def detect_batch(
        self,
        observations: List[Dict[str, Any]],
        timestamp_field: str = "@timestamp"
    ) -> List[Dict[str, Any]]:
        """Detect anomalies for multiple observations.
        
        Args:
            observations: List of observation dicts
            timestamp_field: Timestamp field name
        
        Returns:
            List of detection results
        """
        return [self.detect(obs, timestamp_field) for obs in observations]
