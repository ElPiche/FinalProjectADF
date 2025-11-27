"""Training Orchestrator - Integrates BucketResolver with Algorithm Registry.

This module is the Dispatcher's responsibility for:
1. Fetching bucket profile from MongoDB
2. Resolving timestamps to bucket keys using BucketResolver
3. Grouping training data by bucket key
4. Training algorithm baselines per bucket via the registry
5. Storing results in the new schema format

The algorithms are PURE statistics - no bucket awareness.
Bucketing is handled ENTIRELY here.
"""

from __future__ import annotations

import pandas as pd
from datetime import datetime, timezone as tz
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from pymongo import MongoClient

# Import algorithm registry - central place for all algorithms
from MotorDA.algorithm_registry import get_algorithm, is_algorithm_supported
from MotorDA.base_algorithm import DetectionMode, BucketMode

# Import BucketResolver - handles ALL bucketing
from MotorDA.Dispatcher.bucket_resolver import BucketResolver, BucketProfile

# Legacy import for backward compatibility (will be removed in future)
from MotorDA.ZScore import zscore_algorithm as zscore


@dataclass
class TrainingOrchestrator:
    """Orchestrates training with bucket-aware data grouping."""
    
    bucket_resolver: Optional[BucketResolver]
    bucket_profile_id: Optional[str]
    
    @classmethod
    def create(cls, bucket_profile_id: Optional[str], mongo_client: MongoClient, db_name: str = "anomaly_detection") -> "TrainingOrchestrator":
        """Factory method to create orchestrator with bucket profile from MongoDB.
        
        Args:
            bucket_profile_id: ID of bucket profile, or None for global_default
            mongo_client: MongoDB client
            db_name: Database name
        
        Returns:
            TrainingOrchestrator instance
        """
        if bucket_profile_id is None:
            # No bucket profile - use global_default for all data
            return cls(bucket_resolver=None, bucket_profile_id=None)
        
        # Fetch bucket profile from MongoDB (bucket_profile_id is stored as _id)
        collection = mongo_client[db_name]["bucket_profiles"]
        profile_doc = collection.find_one({"_id": bucket_profile_id})
        
        if profile_doc is None:
            print(f"\033[93m[ORCHESTRATOR] Bucket profile '{bucket_profile_id}' not found, using global_default\033[0m")
            return cls(bucket_resolver=None, bucket_profile_id=None)
        
        # Create resolver from profile
        try:
            resolver = BucketResolver.from_dict(profile_doc)
            print(f"\033[92m[ORCHESTRATOR] Loaded bucket profile '{bucket_profile_id}'\033[0m")
            return cls(bucket_resolver=resolver, bucket_profile_id=bucket_profile_id)
        except Exception as e:
            print(f"\033[91m[ORCHESTRATOR] Failed to create resolver: {e}, using global_default\033[0m")
            return cls(bucket_resolver=None, bucket_profile_id=None)
    
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
    
    def group_by_bucket(self, df: pd.DataFrame, timestamp_col: str = "timestamp") -> Dict[str, pd.DataFrame]:
        """Group DataFrame rows by their resolved bucket keys.
        
        Args:
            df: DataFrame with timestamp column
            timestamp_col: Name of timestamp column
        
        Returns:
            Dict mapping bucket_key -> DataFrame subset
        """
        if df.empty:
            return {}
        
        df = df.copy()
        df[timestamp_col] = pd.to_datetime(df[timestamp_col])
        
        # Resolve bucket key for each row
        df["_bucket_key"] = df[timestamp_col].apply(
            lambda ts: self.resolve_bucket_key(ts.to_pydatetime())
        )
        
        # Group by bucket key
        result = {}
        for bucket_key, group in df.groupby("_bucket_key"):
            group_copy = group.drop(columns=["_bucket_key"])
            result[str(bucket_key)] = group_copy
        
        return result
    
    def train_dimension(
        self,
        kb_id: str,
        dimension: str,
        df_train: pd.DataFrame,
        value_col: str = "value",
        timestamp_col: str = "timestamp",
        percentile: float = 99.5,
        min_points: int = 3,
    ) -> Dict[str, Any]:
        """Train ZScore baselines for a single dimension, grouped by bucket.
        
        This is the main training method. It:
        1. Groups data by bucket key using BucketResolver
        2. Trains a pure ZScore baseline per bucket
        3. Creates global fallback for buckets with insufficient data
        4. Returns result in new schema format
        
        Args:
            kb_id: Knowledge Base configuration ID
            dimension: The metric dimension being trained
            df_train: Training DataFrame
            value_col: Column containing metric values
            timestamp_col: Column containing timestamps
            percentile: Percentile for threshold (default 99.5)
            min_points: Minimum points for valid bucket baseline
        
        Returns:
            Training result dict in new schema format:
            {
                "kb_id": "...",
                "dimension": "...",
                "bucket_profile_id": "business_hours_v1" or null,
                "buckets": {
                    "workday_14": {"mean": ..., "std": ..., "threshold": ..., ...},
                    "weekend_09": {...},
                    ...
                },
                "global_fallback": {"mean": ..., "std": ..., ...}
            }
        """
        # Default to zscore for backward compatibility
        return self.train_dimension_with_algorithm(
            kb_id=kb_id,
            dimension=dimension,
            algorithm_name="zscore",
            df_train=df_train,
            value_col=value_col,
            timestamp_col=timestamp_col,
            metadata={"percentile": percentile, "min_points": min_points},
        )
    
    def train_dimension_with_algorithm(
        self,
        kb_id: str,
        dimension: str,
        algorithm_name: str,
        df_train: pd.DataFrame,
        value_col: str = "value",
        timestamp_col: str = "timestamp",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Train any POINT algorithm for a dimension, grouped by bucket.
        
        This is the NEW main training method using the algorithm registry.
        It supports any POINT algorithm with SEGMENT bucket mode.
        
        Args:
            kb_id: Knowledge Base configuration ID
            dimension: The metric dimension being trained
            algorithm_name: Name of algorithm in registry (e.g., "zscore", "iqr")
            df_train: Training DataFrame
            value_col: Column containing metric values
            timestamp_col: Column containing timestamps
            metadata: Algorithm-specific parameters (e.g., {"percentile": 99.5})
        
        Returns:
            Training result dict in new schema format
        """
        metadata = metadata or {}
        min_points = int(metadata.get("min_points", 3))
        
        # Get algorithm from registry
        algorithm = get_algorithm(algorithm_name)
        if algorithm is None:
            raise ValueError(f"Unknown algorithm: '{algorithm_name}'. Use is_algorithm_supported() to check.")
        
        # Validate algorithm is POINT mode
        if algorithm.detection_mode != DetectionMode.POINT:
            raise ValueError(
                f"Algorithm '{algorithm_name}' is {algorithm.detection_mode.value} mode, "
                f"but only POINT mode algorithms are currently supported."
            )
        
        if df_train.empty:
            return {
                "kb_id": kb_id,
                "dimension": dimension,
                "algorithm": algorithm_name,
                "bucket_profile_id": self.bucket_profile_id,
                "buckets": {},
                "global_fallback": None,
            }
        
        # Create global fallback from ALL training data (algorithm-aware)
        all_data = [
            {"value": v, "timestamp": t}
            for v, t in zip(
                df_train[value_col].astype(float).tolist(),
                df_train[timestamp_col].tolist()
            )
        ]
        global_result = algorithm.train(all_data, bucket_key="global_fallback", metadata=metadata)
        global_fallback = global_result.to_dict()
        
        # Group training data by bucket key
        grouped = self.group_by_bucket(df_train, timestamp_col)
        
        print(f"\033[92m[ORCHESTRATOR] Training dimension '{dimension}' with algorithm '{algorithm_name}' and {len(grouped)} buckets\033[0m")
        
        # Train algorithm baseline for each bucket
        buckets: Dict[str, Dict[str, Any]] = {}
        
        for bucket_key, bucket_df in grouped.items():
            # Convert DataFrame to list of dicts for algorithm interface
            bucket_data = [
                {"value": v, "timestamp": t}
                for v, t in zip(
                    bucket_df[value_col].astype(float).tolist(),
                    bucket_df[timestamp_col].tolist()
                )
            ]
            n_points = len(bucket_data)
            
            if n_points < min_points:
                # Use global fallback for insufficient data
                print(f"\033[93m[ORCHESTRATOR] Bucket '{bucket_key}' has {n_points} points < {min_points}, using global fallback\033[0m")
                buckets[bucket_key] = {
                    **global_fallback,
                    "sufficient_data": False,
                }
            else:
                # Train bucket-specific baseline
                print(f"\033[92m[ORCHESTRATOR] Bucket '{bucket_key}' training with {n_points} data points\033[0m")
                result = algorithm.train(bucket_data, bucket_key=bucket_key, metadata=metadata)
                buckets[bucket_key] = {
                    **result.to_dict(),
                    "sufficient_data": result.sufficient_data,
                }
        
        return {
            "kb_id": kb_id,
            "dimension": dimension,
            "algorithm": algorithm_name,
            "bucket_profile_id": self.bucket_profile_id,
            "buckets": buckets,
            "global_fallback": global_fallback,
        }


@dataclass
class DetectionOrchestrator:
    """Orchestrates detection with bucket-aware baseline lookup."""
    
    bucket_resolver: Optional[BucketResolver]
    baselines: Dict[str, Dict[str, Any]]  # dimension -> training result
    
    @classmethod
    def create(
        cls,
        bucket_profile_id: Optional[str],
        baselines: Dict[str, Dict[str, Any]],
        mongo_client: MongoClient,
        db_name: str = "anomaly_detection",
    ) -> "DetectionOrchestrator":
        """Factory method to create detection orchestrator.
        
        Args:
            bucket_profile_id: ID of bucket profile, or None
            baselines: Dict of dimension -> training result
            mongo_client: MongoDB client
            db_name: Database name
        
        Returns:
            DetectionOrchestrator instance
        """
        if bucket_profile_id is None:
            return cls(bucket_resolver=None, baselines=baselines)
        
        # Fetch bucket profile (bucket_profile_id is stored as _id)
        collection = mongo_client[db_name]["bucket_profiles"]
        profile_doc = collection.find_one({"_id": bucket_profile_id})
        
        if profile_doc is None:
            print(f"\033[93m[DETECTION] Bucket profile '{bucket_profile_id}' not found\033[0m")
            return cls(bucket_resolver=None, baselines=baselines)
        
        try:
            resolver = BucketResolver.from_dict(profile_doc)
            return cls(bucket_resolver=resolver, baselines=baselines)
        except Exception as e:
            print(f"\033[91m[DETECTION] Failed to create resolver: {e}\033[0m")
            return cls(bucket_resolver=None, baselines=baselines)
    
    def detect(
        self,
        dimension: str,
        timestamp: datetime,
        value: float,
    ) -> Dict[str, Any]:
        """Detect if a single value is anomalous.
        
        Args:
            dimension: The metric dimension
            timestamp: Timestamp of the value
            value: The metric value
        
        Returns:
            Detection result dict with bucket_key, z_score, is_anomaly
        """
        # Resolve bucket key
        if self.bucket_resolver is not None:
            bucket_key = self.bucket_resolver.resolve(timestamp)
        else:
            bucket_key = "global_default"
        
        # Get baseline for this dimension
        if dimension not in self.baselines:
            return {
                "timestamp": timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp),
                "dimension": dimension,
                "value": value,
                "bucket_key": bucket_key,
                "error": f"No baseline for dimension '{dimension}'",
                "is_anomaly": False,
            }
        
        baseline_result = self.baselines[dimension]
        buckets = baseline_result.get("buckets", {})
        global_fallback = baseline_result.get("global_fallback")
        
        # Find the right bucket baseline
        if bucket_key in buckets:
            bucket_stats = buckets[bucket_key]
        elif global_fallback:
            print(f"\033[93m[DETECTION] Bucket '{bucket_key}' not found, using global fallback\033[0m")
            bucket_stats = global_fallback
        elif buckets:
            # Use first available bucket as last resort
            first_key = next(iter(buckets))
            bucket_stats = buckets[first_key]
            print(f"\033[93m[DETECTION] Using bucket '{first_key}' as fallback\033[0m")
        else:
            return {
                "timestamp": timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp),
                "dimension": dimension,
                "value": value,
                "bucket_key": bucket_key,
                "error": "No buckets available",
                "is_anomaly": False,
            }
        
        # Get algorithm name from training result, default to zscore
        algorithm_name = baseline_result.get("algorithm", "zscore")
        algorithm = get_algorithm(algorithm_name)
        
        if algorithm is None:
            # Fall back to legacy zscore detection
            print(f"\033[93m[DETECTION] Algorithm '{algorithm_name}' not in registry, using legacy zscore\033[0m")
            baseline = zscore.ZScoreBaseline.from_dict(bucket_stats)
            result = zscore.detect(value, baseline)
            return {
                "timestamp": timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp),
                "dimension": dimension,
                "bucket_key": bucket_key,
                **result.to_dict(),
            }
        
        # Use algorithm from registry
        detection_result = algorithm.detect(value, bucket_stats)
        
        return {
            "timestamp": timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp),
            "dimension": dimension,
            "algorithm": algorithm_name,
            "bucket_key": bucket_key,
            **detection_result.to_dict(),
        }
    
    def detect_batch(
        self,
        dimension: str,
        df: pd.DataFrame,
        value_col: str = "value",
        timestamp_col: str = "timestamp",
    ) -> List[Dict[str, Any]]:
        """Detect anomalies for a batch of values.
        
        Args:
            dimension: The metric dimension
            df: DataFrame with timestamp and value columns
            value_col: Value column name
            timestamp_col: Timestamp column name
        
        Returns:
            List of detection results
        """
        if df.empty:
            return []
        
        results = []
        df = df.copy()
        df[timestamp_col] = pd.to_datetime(df[timestamp_col])
        
        for _, row in df.iterrows():
            ts = row[timestamp_col].to_pydatetime()
            val = float(row[value_col])
            result = self.detect(dimension, ts, val)
            results.append(result)
        
        return results


# === BACKWARD COMPATIBILITY ================================================
# These functions match the old interface for gradual migration

def run_zscore_training_bucketed(
    kb_id: str,
    dimension: str,
    df_train: pd.DataFrame,
    value_col: str,
    bucket_profile_id: Optional[str],
    mongo_client: MongoClient,
    percentile: float = 99.5,
) -> Dict[str, Any]:
    """Backward-compatible training function.
    
    Matches the signature expected by the Dispatcher.
    """
    orchestrator = TrainingOrchestrator.create(
        bucket_profile_id=bucket_profile_id,
        mongo_client=mongo_client,
    )
    
    return orchestrator.train_dimension(
        kb_id=kb_id,
        dimension=dimension,
        df_train=df_train,
        value_col=value_col,
        percentile=percentile,
    )
