#TODO: rename file to orchestrator.py

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
from MotorDA.Dispatcher.algorithm_interface import get_algorithm

# Bucket resolver for time-context bucketing
from MotorDA.Dispatcher.bucket_resolver import BucketResolver

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
    
    Supports both single-dimensional and multi-dimensional algorithms:
    - Single-dimensional: Loops over parameters, calls train() per dimension
    - Multi-dimensional: Calls train_multi_dimension() with all parameters
    
    Completely algorithm-agnostic - uses algorithm registry.
    """
    
    algorithm_name: str
    parameters: List[Dict[str, Any]]
    bucket_profile: Optional[Dict[str, Any]] = None
    is_multi_dimensional: bool = False  # Phase 3: Algorithm mode flag
    bucket_resolver: Optional[BucketResolver] = field(default=None, init=False)
    _algorithm_instance: Any = field(default=None, init=False)  # Cached algorithm
    
    def __post_init__(self):
        """Initialize bucket resolver if profile provided."""
        if self.bucket_profile:
            try:
                self.bucket_resolver = BucketResolver.from_dict(self.bucket_profile)
                profile_id = self.bucket_profile.get('profile_id') or self.bucket_profile.get('_id')
                logger.info(f"[ORCHESTRATOR] Loaded bucket profile: {profile_id}")
                logger.info(f"[ORCHESTRATOR] Bucket resolver created: {self.bucket_resolver is not None}")
            except Exception as e:
                logger.warning(f"[ORCHESTRATOR] Failed to create bucket resolver: {e}")
                import traceback
                traceback.print_exc()
                self.bucket_resolver = None
        else:
            logger.info("[ORCHESTRATOR] No bucket profile provided")
        
        # Cache algorithm instance
        self._algorithm_instance = get_algorithm(self.algorithm_name)
    
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
    
    def _resolve_min_training_samples(self, parameter: Dict[str, Any]) -> int:
        """Resolve minimum training samples for a parameter.
        
        Two-tier override pattern:
        1. Check parameter metadata for user override
        2. Fall back to algorithm's default property
        
        Args:
            parameter: Algorithm parameter dict with optional metadata
        
        Returns:
            Minimum training samples required
        """
        # Check metadata override first
        for meta in parameter.get("metadata", []):
            if meta.get("key") == "min_training_samples":
                try:
                    return int(meta.get("value"))
                except (ValueError, TypeError):
                    pass
        
        # Fall back to algorithm property
        return self._algorithm_instance.min_training_samples
    
    def _train_single_dimensional(
        self,
        observations: List[Dict[str, Any]],
        parameter: Dict[str, Any],
        bucket_context: str
    ) -> Optional[Dict[str, Any]]:
        """Train a single dimension (for single-dimensional algorithms).
        
        Extracts values for the dimension, validates sample count,
        and calls algorithm.train() with the parameter.
        
        Args:
            observations: List of observation dicts for this bucket
            parameter: Algorithm parameter dict with 'dimension' key
            bucket_context: Bucket key for logging context
        
        Returns:
            Baseline dict or None if insufficient data
        """
        dimension = parameter.get("dimension")
        if not dimension:
            return None
        
        # Extract values for this dimension
        values = []
        for obs in observations:
            val = obs.get(dimension)
            if val is not None:
                try:
                    values.append(float(val))
                except (ValueError, TypeError):
                    pass
        
        # Check minimum samples
        min_samples = self._resolve_min_training_samples(parameter)
        if len(values) < min_samples:
            logger.warning(
                f"[ORCHESTRATOR] Insufficient data for dimension '{dimension}' "
                f"in bucket '{bucket_context}': {len(values)} < {min_samples}"
            )
            return None
        
        # Train using single-dimensional interface
        baseline = self._algorithm_instance.train(values, parameter=parameter)
        baseline["bucket_context"] = bucket_context  # Always tag
        baseline["n_observations"] = len(values)
        
        logger.info(
            f"[ORCHESTRATOR] Trained dimension '{dimension}' in bucket '{bucket_context}' "
            f"with {len(values)} values"
        )
        
        return baseline
    

    #TODO: change observed_value to dimnesions
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
        failed_parse_count = 0
        
        
        for i, obs in enumerate(observed_values):
            # Try the specified timestamp field first, then fallback to common fields
            ts_val = obs.get(timestamp_field)
            if ts_val is None:
                # Fallback: series collection always stores as "timestamp"
                ts_val = obs.get("timestamp")
            if ts_val is None:
                # Also try @timestamp
                ts_val = obs.get("@timestamp")
            
            ts = parse_timestamp(ts_val)
            
            if i < 3:  # Debug first few observations
                logger.info(f"[ORCHESTRATOR] Obs {i}: ts_field='{timestamp_field}', ts_val={ts_val}, parsed_ts={ts}")
            
            if ts is None:
                bucket_key = "global_default"
                failed_parse_count += 1
            else:
                bucket_key = self.resolve_bucket_key(ts)
            
            if bucket_key not in groups:
                groups[bucket_key] = []
            groups[bucket_key].append(obs)
        
        if failed_parse_count > 0:
            logger.warning(f"[ORCHESTRATOR] {failed_parse_count}/{len(observed_values)} observations failed timestamp parsing")
        
        return groups
    
    #TODO: get percentile from kb metadata
    #TODO: change observed_values to dimensions
    def train(
        self,
        observed_values: List[Dict[str, Any]],
        timestamp_field: str = "@timestamp",
        percentile: float = 99.5
    ) -> Dict[str, Any]:
        """Train baselines for all buckets.
        
        This is the main training entry point. It:
        1. Checks algorithm's supports_bucketing property
        2. Groups observations by bucket key (if bucketing supported)
        3. Trains baselines using appropriate method based on is_multi_dimensional
        4. Creates global fallback from all data
        5. Returns bucket-keyed training result with bucket_context tags
        
        Args:
            observed_values: List of observation dicts
            timestamp_field: Timestamp field name
            percentile: Percentile for threshold calculation
        
        Returns:
            Training result dict:
            {
                "algorithm": "zscore",
                "is_multi_dimensional": false,
                "bucket_profile_id": "...",
                "buckets": {
                    "workday_14": {dimension: baseline_dict, ...},
                    ...
                },
                "global_fallback": {dimension: baseline_dict, ...}
            }
        """
        algorithm = self._algorithm_instance
        
        logger.info(f"[ORCHESTRATOR] Training with algorithm '{self.algorithm_name}'")
        logger.info(f"[ORCHESTRATOR] Algorithm mode: {'multi-dimensional' if self.is_multi_dimensional else 'single-dimensional'}")
        logger.info(f"[ORCHESTRATOR] Supports bucketing: {algorithm.supports_bucketing}")
        logger.info(f"[ORCHESTRATOR] Observations: {len(observed_values)}")
        
        # ─────────────────────────────────────────────────────────────────────────
        # Check supports_bucketing - if False, treat all data as single bucket
        # ─────────────────────────────────────────────────────────────────────────
        if algorithm.supports_bucketing:
            groups = self.group_by_bucket(observed_values, timestamp_field)
            logger.info(f"[ORCHESTRATOR] Buckets: {list(groups.keys())}")
        else:
            # No bucketing: all data in one group
            groups = {"global_default": observed_values}
            logger.info("[ORCHESTRATOR] Algorithm does not support bucketing, using single group")
        
        # ─────────────────────────────────────────────────────────────────────────
        # Train global fallback from ALL data (always as backup)
        # ─────────────────────────────────────────────────────────────────────────
        global_fallback = self._train_bucket(
            observed_values,
            bucket_context="global_fallback",
            percentile=percentile
        )
        logger.info(f"[ORCHESTRATOR] Global fallback trained with dimensions: {list(global_fallback.keys())}")
        
        # ─────────────────────────────────────────────────────────────────────────
        # Train per-bucket baselines
        # ─────────────────────────────────────────────────────────────────────────
        buckets = {}
        for bucket_key, bucket_obs in groups.items():
            logger.info(f"[ORCHESTRATOR] Training bucket '{bucket_key}' with {len(bucket_obs)} observations")
            
            bucket_baseline = self._train_bucket(
                bucket_obs,
                bucket_context=bucket_key,
                percentile=percentile
            )
            
            # Determine if bucket has sufficient data
            has_sufficient = any(
                b is not None for b in bucket_baseline.values()
            ) if bucket_baseline else False
            
            if not has_sufficient:
                logger.warning(f"[ORCHESTRATOR] Bucket '{bucket_key}' has insufficient data, using global fallback")
                buckets[bucket_key] = {
                    "baselines": global_fallback,
                    "n_observations": len(bucket_obs),
                    "sufficient_data": False,
                    "bucket_context": bucket_key
                }
            else:
                buckets[bucket_key] = {
                    "baselines": bucket_baseline,
                    "n_observations": len(bucket_obs),
                    "sufficient_data": True,
                    "bucket_context": bucket_key
                }
        
        result = {
            "algorithm": self.algorithm_name,
            "is_multi_dimensional": self.is_multi_dimensional,
            "bucket_profile_id": self.bucket_profile.get("profile_id") if self.bucket_profile else None,
            "buckets": buckets,
            "global_fallback": global_fallback,
            "n_total_observations": len(observed_values),
            "parameters": self.parameters
        }
        
        logger.info(f"[ORCHESTRATOR] Training complete. Buckets: {len(buckets)}")
        return result
    
    def _train_bucket(
        self,
        observations: List[Dict[str, Any]],
        bucket_context: str,
        percentile: float
    ) -> Dict[str, Any]:
        """Train a single bucket using appropriate algorithm method.
        
        Routes to single-dimensional or multi-dimensional training
        based on is_multi_dimensional flag.
        
        Args:
            observations: List of observations for this bucket
            bucket_context: Bucket key for tagging
            percentile: Percentile for threshold calculation
        
        Returns:
            Dict mapping dimension -> baseline_dict
        """
        if self.is_multi_dimensional:
            # Multi-dimensional: delegate to algorithm's batch method
            baseline = self._algorithm_instance.train_multi_dimension(
                observations=observations,
                parameters=self.parameters,
                percentile=percentile
            )
            # Tag all baselines with bucket_context
            for dim, dim_baseline in baseline.items():
                if isinstance(dim_baseline, dict):
                    dim_baseline["bucket_context"] = bucket_context
            return baseline
        else:
            # Single-dimensional: loop over parameters
            result = {}
            for param in self.parameters:
                dimension = param.get("dimension")
                if not dimension:
                    continue
                
                baseline = self._train_single_dimensional(
                    observations,
                    parameter=param,
                    bucket_context=bucket_context
                )
                if baseline is not None:
                    result[dimension] = baseline
            
            return result


@dataclass
class DetectionOrchestrator:
    """Orchestrates detection with bucket-aware baseline lookup.
    
    This orchestrator:
    1. Resolves observation timestamp to bucket key
    2. Gets the correct baseline for that bucket
    3. Delegates detection to the algorithm
    
    Supports both single-dimensional and multi-dimensional algorithms:
    - Single-dimensional: Loops over parameters, calls detect() per dimension
    - Multi-dimensional: Calls detect_multi_dimension() with all parameters
    
    Completely algorithm-agnostic - uses algorithm registry.
    """
    
    algorithm_name: str
    parameters: List[Dict[str, Any]]
    training_result: Dict[str, Any]
    bucket_profile: Optional[Dict[str, Any]] = None
    is_multi_dimensional: bool = False  # Phase 3: Algorithm mode flag
    bucket_resolver: Optional[BucketResolver] = field(default=None, init=False)
    _algorithm_instance: Any = field(default=None, init=False)  # Cached algorithm
    
    def __post_init__(self):
        """Initialize bucket resolver if profile provided."""
        if self.bucket_profile:
            try:
                self.bucket_resolver = BucketResolver.from_dict(self.bucket_profile)
            except Exception as e:
                logger.warning(f"[DETECTION] Failed to create bucket resolver: {e}")
                self.bucket_resolver = None
        
        # Cache algorithm instance
        self._algorithm_instance = get_algorithm(self.algorithm_name)
    
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
    
    def _detect_single_dimensional(
        self,
        observation: Dict[str, Any],
        baselines: Dict[str, Dict[str, Any]],
        bucket_key: str
    ) -> Dict[str, Any]:
        """Detect anomalies using single-dimensional algorithm.
        
        Loops over parameters and calls detect() for each dimension.
        
        Args:
            observation: Observation dict with dimension values
            baselines: Per-dimension baselines from training
            bucket_key: Bucket context for logging
        
        Returns:
            Detection result with is_anomaly, dimension_results
        """
        dimension_results = {}
        is_any_anomaly = False
        
        for param in self.parameters:
            dimension = param.get("dimension")
            if not dimension:
                continue
            
            baseline = baselines.get(dimension)
            if not baseline:
                logger.warning(f"[DETECTION] No baseline for dimension '{dimension}'")
                continue
            
            value = observation.get(dimension)
            if value is None:
                continue
            
            try:
                value = float(value)
            except (ValueError, TypeError):
                continue
            
            # Call single-dimensional detect with parameter
            result = self._algorithm_instance.detect(value, baseline, parameter=param)
            result["bucket_context"] = bucket_key
            dimension_results[dimension] = result
            
            if result.get("is_anomaly", False):
                is_any_anomaly = True
        
        return {
            "is_anomaly": is_any_anomaly,
            "dimensions": dimension_results,
            "observation": observation
        }
    
    def detect(
        self,
        observation: Dict[str, Any],
        timestamp_field: str = "@timestamp"
    ) -> Dict[str, Any]:
        """Detect if an observation is anomalous.
        
        Routes to single-dimensional or multi-dimensional detection
        based on is_multi_dimensional flag.
        
        Args:
            observation: Observation dict with dimensions and timestamp
            timestamp_field: Timestamp field name from query_mode
        
        Returns:
            Detection result dict with is_anomaly, dimension_results
        """
        # Get timestamp - try configured field first, then common fallbacks
        # This handles the case where query uses "bucket" but series stores as "timestamp"
        ts_val = observation.get(timestamp_field)
        if ts_val is None:
            # Fallback to common timestamp field names
            for fallback_field in ["timestamp", "@timestamp", "bucket", "time"]:
                ts_val = observation.get(fallback_field)
                if ts_val is not None:
                    break
        
        ts = parse_timestamp(ts_val)
        
        if ts is None:
            bucket_key = "global_default"
            logger.warning(f"[DETECTION] Timestamp is None for observation: {observation}")
        else:
            bucket_key = self.resolve_bucket_key(ts)
        
        # Get baseline for this bucket
        baselines = self.get_baseline_for_bucket(bucket_key)
        
        # Route based on algorithm mode
        if self.is_multi_dimensional:
            # Multi-dimensional: delegate to algorithm's batch method
            result = self._algorithm_instance.detect_multi_dimension(
                observation=observation,
                baselines=baselines,
                parameters=self.parameters
            )
        else:
            # Single-dimensional: loop over parameters
            result = self._detect_single_dimensional(
                observation,
                baselines,
                bucket_key
            )
        
        # Add metadata
        result["bucket_key"] = bucket_key
        result["timestamp"] = ts.isoformat() if ts else None
        
        return result
    
    #TODO: remove unused (only used for testing hehe)
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
