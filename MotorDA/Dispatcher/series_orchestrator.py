"""Series Training Orchestrator - Trains SERIES algorithms without bucket splitting.

SERIES algorithms (ARMA, ARMAX, LSTM) require continuous time series data.
Unlike POINT algorithms, they CANNOT have their training data split by bucket.

Instead, bucket information is passed as features (BucketMode.FEATURE).

Usage:
    from MotorDA.Dispatcher.series_orchestrator import SeriesTrainingOrchestrator
    
    orchestrator = SeriesTrainingOrchestrator.create(
        bucket_profile_id="business_hours_v1",
        mongo_client=mongo_client,
    )
    
    result = orchestrator.train_dimension(
        kb_id="...",
        dimension="status_5xx",
        algorithm_name="arma",
        df_train=df,
    )
"""

from __future__ import annotations

import pandas as pd
from datetime import datetime, timezone as tz
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from pymongo import MongoClient

# Import algorithm registry
try:
    from MotorDA.algorithm_registry import get_algorithm, is_algorithm_supported
    from MotorDA.base_algorithm import DetectionMode, BucketMode, TrainingResult
    from MotorDA.Dispatcher.bucket_resolver import BucketResolver
except ImportError:
    from algorithm_registry import get_algorithm, is_algorithm_supported
    from base_algorithm import DetectionMode, BucketMode, TrainingResult
    from Dispatcher.bucket_resolver import BucketResolver


@dataclass  
class SeriesTrainingOrchestrator:
    """Orchestrates training for SERIES algorithms.
    
    Key differences from TrainingOrchestrator (for POINT algorithms):
    1. Data is NOT split by bucket
    2. Bucket features are added as columns to the data
    3. Training produces a single model (not per-bucket baselines)
    """
    
    bucket_resolver: Optional[BucketResolver]
    bucket_profile_id: Optional[str]
    
    @classmethod
    def create(
        cls, 
        bucket_profile_id: Optional[str], 
        mongo_client: MongoClient, 
        db_name: str = "anomaly_detection"
    ) -> "SeriesTrainingOrchestrator":
        """Factory method to create orchestrator.
        
        Args:
            bucket_profile_id: ID of bucket profile for feature extraction
            mongo_client: MongoDB client
            db_name: Database name
        
        Returns:
            SeriesTrainingOrchestrator instance
        """
        if bucket_profile_id is None:
            return cls(bucket_resolver=None, bucket_profile_id=None)
        
        # Fetch bucket profile from MongoDB
        collection = mongo_client[db_name]["bucket_profiles"]
        profile_doc = collection.find_one({"_id": bucket_profile_id})
        
        if profile_doc is None:
            print(f"\033[93m[SERIES_ORCHESTRATOR] Bucket profile '{bucket_profile_id}' not found\033[0m")
            return cls(bucket_resolver=None, bucket_profile_id=None)
        
        try:
            resolver = BucketResolver.from_dict(profile_doc)
            print(f"\033[92m[SERIES_ORCHESTRATOR] Loaded bucket profile '{bucket_profile_id}'\033[0m")
            return cls(bucket_resolver=resolver, bucket_profile_id=bucket_profile_id)
        except Exception as e:
            print(f"\033[91m[SERIES_ORCHESTRATOR] Failed to create resolver: {e}\033[0m")
            return cls(bucket_resolver=None, bucket_profile_id=None)
    
    def add_bucket_features(
        self, 
        df: pd.DataFrame, 
        timestamp_col: str = "timestamp"
    ) -> pd.DataFrame:
        """Add bucket-derived features to the DataFrame.
        
        For SERIES algorithms with BucketMode.FEATURE, bucket information
        is passed as input features rather than used to split data.
        
        Features added:
        - bucket_key: The resolved bucket key (string)
        - is_workday: 1 if workday, 0 otherwise
        - hour: Hour of day (0-23)
        - day_of_week: Day of week (0=Monday, 6=Sunday)
        
        Args:
            df: DataFrame with timestamp column
            timestamp_col: Name of timestamp column
        
        Returns:
            DataFrame with bucket feature columns added
        """
        if df.empty:
            return df
        
        df = df.copy()
        df[timestamp_col] = pd.to_datetime(df[timestamp_col])
        
        # Add time-based features
        df["hour"] = df[timestamp_col].dt.hour
        df["day_of_week"] = df[timestamp_col].dt.dayofweek
        df["is_workday"] = (df["day_of_week"] < 5).astype(int)
        
        # Add bucket key if resolver available
        if self.bucket_resolver is not None:
            df["bucket_key"] = df[timestamp_col].apply(
                lambda ts: self.bucket_resolver.resolve(ts.to_pydatetime())
            )
        else:
            df["bucket_key"] = "global_default"
        
        return df
    
    def get_bucket_features_for_timestamp(self, ts: datetime) -> Dict[str, float]:
        """Get bucket features for a single timestamp.
        
        Used at detection time to get current bucket context.
        
        Args:
            ts: Timestamp to get features for
        
        Returns:
            Dict of feature_name -> feature_value
        """
        features = {
            "hour": float(ts.hour),
            "day_of_week": float(ts.weekday()),
            "is_workday": 1.0 if ts.weekday() < 5 else 0.0,
        }
        
        if self.bucket_resolver is not None:
            bucket_key = self.bucket_resolver.resolve(ts)
            # Encode bucket key as numeric features if needed
            features["bucket_key"] = bucket_key
        else:
            features["bucket_key"] = "global_default"
        
        return features
    
    def train_dimension(
        self,
        kb_id: str,
        dimension: str,
        algorithm_name: str,
        df_train: pd.DataFrame,
        value_col: str = "value",
        timestamp_col: str = "timestamp",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Train a SERIES algorithm on continuous time series data.
        
        Unlike POINT algorithms, data is NOT split by bucket.
        Bucket features are added as columns for the algorithm to use.
        
        Args:
            kb_id: Knowledge Base configuration ID
            dimension: The metric dimension being trained
            algorithm_name: Name of SERIES algorithm in registry
            df_train: Training DataFrame (will NOT be split)
            value_col: Column containing metric values
            timestamp_col: Column containing timestamps
            metadata: Algorithm-specific parameters
        
        Returns:
            Training result dict with single model/baseline
        """
        metadata = metadata or {}
        
        # Get algorithm from registry
        algorithm = get_algorithm(algorithm_name)
        if algorithm is None:
            raise ValueError(f"Unknown algorithm: '{algorithm_name}'")
        
        # Validate it's a SERIES algorithm
        if algorithm.detection_mode != DetectionMode.SERIES:
            raise ValueError(
                f"Algorithm '{algorithm_name}' is {algorithm.detection_mode.value} mode, "
                f"not SERIES. Use TrainingOrchestrator for POINT algorithms."
            )
        
        if df_train.empty:
            return {
                "kb_id": kb_id,
                "dimension": dimension,
                "algorithm": algorithm_name,
                "detection_mode": "series",
                "bucket_profile_id": self.bucket_profile_id,
                "baseline": {},
                "data_points": 0,
                "sufficient_data": False,
            }
        
        # Add bucket features (don't split!)
        df_with_features = self.add_bucket_features(df_train, timestamp_col)
        
        # Sort by timestamp (important for time series)
        df_with_features = df_with_features.sort_values(timestamp_col)
        
        print(f"\033[92m[SERIES_ORCHESTRATOR] Training '{algorithm_name}' on {len(df_with_features)} continuous data points\033[0m")
        
        # Convert to list of dicts for algorithm interface
        data = []
        for _, row in df_with_features.iterrows():
            entry = {
                "timestamp": row[timestamp_col],
                "value": float(row[value_col]),
                "hour": row["hour"],
                "day_of_week": row["day_of_week"],
                "is_workday": row["is_workday"],
                "bucket_key": row["bucket_key"],
            }
            data.append(entry)
        
        # Get bucket features (for FEATURE mode)
        bucket_features = None
        if algorithm.bucket_mode == BucketMode.FEATURE:
            # Pass aggregate features
            bucket_features = {
                "has_bucket_profile": 1.0 if self.bucket_profile_id else 0.0,
            }
        
        # Train the algorithm (single training, no splitting)
        try:
            result = algorithm.train(
                data=data,
                bucket_key=None,  # No bucket key for SERIES
                bucket_features=bucket_features,
                metadata=metadata,
            )
        except NotImplementedError:
            # Algorithm not fully implemented yet
            print(f"\033[93m[SERIES_ORCHESTRATOR] Algorithm '{algorithm_name}' train() not implemented\033[0m")
            result = TrainingResult(
                baseline={"status": "not_implemented"},
                data_points=len(data),
                sufficient_data=False,
            )
        
        return {
            "kb_id": kb_id,
            "dimension": dimension,
            "algorithm": algorithm_name,
            "detection_mode": "series",
            "bucket_profile_id": self.bucket_profile_id,
            "required_history_length": algorithm.required_history_length,
            **result.to_dict(),
        }


@dataclass
class SeriesDetectionOrchestrator:
    """Orchestrates detection for SERIES algorithms.
    
    Key differences from DetectionOrchestrator:
    1. Fetches history via HistoryProvider
    2. Adds bucket features to current detection context
    3. Single baseline lookup (not per-bucket)
    """
    
    bucket_resolver: Optional[BucketResolver]
    baseline: Dict[str, Any]  # Single baseline for the dimension
    
    @classmethod
    def create(
        cls,
        bucket_profile_id: Optional[str],
        baseline: Dict[str, Any],
        mongo_client: MongoClient,
        db_name: str = "anomaly_detection",
    ) -> "SeriesDetectionOrchestrator":
        """Factory method to create detection orchestrator.
        
        Args:
            bucket_profile_id: ID of bucket profile for feature extraction
            baseline: Training result containing model/baseline
            mongo_client: MongoDB client
            db_name: Database name
        
        Returns:
            SeriesDetectionOrchestrator instance
        """
        if bucket_profile_id is None:
            return cls(bucket_resolver=None, baseline=baseline)
        
        collection = mongo_client[db_name]["bucket_profiles"]
        profile_doc = collection.find_one({"_id": bucket_profile_id})
        
        if profile_doc is None:
            return cls(bucket_resolver=None, baseline=baseline)
        
        try:
            resolver = BucketResolver.from_dict(profile_doc)
            return cls(bucket_resolver=resolver, baseline=baseline)
        except Exception:
            return cls(bucket_resolver=None, baseline=baseline)
    
    def get_bucket_features(self, timestamp: datetime) -> Dict[str, float]:
        """Get bucket features for current timestamp."""
        features = {
            "hour": float(timestamp.hour),
            "day_of_week": float(timestamp.weekday()),
            "is_workday": 1.0 if timestamp.weekday() < 5 else 0.0,
        }
        
        if self.bucket_resolver is not None:
            features["bucket_key"] = self.bucket_resolver.resolve(timestamp)
        else:
            features["bucket_key"] = "global_default"
        
        return features
    
    def detect(
        self,
        value: float,
        timestamp: datetime,
        history: List[Dict[str, Any]],
        algorithm_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Detect if a value is anomalous using SERIES algorithm.
        
        Args:
            value: Current value to check
            timestamp: Timestamp of current value
            history: List of recent values (from HistoryProvider)
            algorithm_name: Name of algorithm to use
            metadata: Algorithm-specific parameters
        
        Returns:
            Detection result dict
        """
        algorithm = get_algorithm(algorithm_name)
        if algorithm is None:
            return {
                "timestamp": timestamp.isoformat(),
                "value": value,
                "error": f"Unknown algorithm: '{algorithm_name}'",
                "is_anomaly": False,
            }
        
        # Get bucket features for current timestamp
        bucket_features = self.get_bucket_features(timestamp)
        bucket_key = bucket_features.pop("bucket_key", "global_default")
        
        # Check if we have enough history
        required = algorithm.required_history_length
        if len(history) < required:
            return {
                "timestamp": timestamp.isoformat(),
                "value": value,
                "bucket_key": bucket_key,
                "error": f"Insufficient history: {len(history)} < {required} required",
                "is_anomaly": False,
            }
        
        # Run detection
        try:
            result = algorithm.detect(
                value=value,
                baseline=self.baseline,
                history=history,
                bucket_features=bucket_features,
                metadata=metadata,
            )
            
            return {
                "timestamp": timestamp.isoformat(),
                "value": value,
                "algorithm": algorithm_name,
                "bucket_key": bucket_key,
                **result.to_dict(),
            }
        except NotImplementedError:
            return {
                "timestamp": timestamp.isoformat(),
                "value": value,
                "algorithm": algorithm_name,
                "bucket_key": bucket_key,
                "error": f"Algorithm '{algorithm_name}' detect() not implemented",
                "is_anomaly": False,
            }
