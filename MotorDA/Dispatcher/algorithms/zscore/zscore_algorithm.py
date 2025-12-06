"""Pure Z-Score Statistical Anomaly Detection Algorithm.

This module implements a STANDALONE Z-Score algorithm with NO bucket logic.
Bucketing is the Dispatcher's responsibility - this algorithm only does statistics.

Interface:
    - train(values, percentile) -> model dict
    - detect(value, model) -> anomaly result
"""

from __future__ import annotations

import numpy as np
from typing import Dict, Any, List, Optional
from dataclasses import dataclass


@dataclass
class ZScoreModel:
    """Statistical model for Z-Score detection."""
    mean: float
    std: float
    threshold: float
    data_points: int
    percentile: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "mean": self.mean,
            "std": self.std,
            "threshold": self.threshold,
            "data_points": self.data_points,
            "percentile": self.percentile,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ZScoreModel":
        return cls(
            mean=d["mean"],
            std=d["std"],
            threshold=d["threshold"],
            data_points=d.get("data_points", 0),
            percentile=d.get("percentile", 99.5),
        )


@dataclass
class AnomalyResult:
    """Result of anomaly detection for a single value."""
    value: float
    z_score: float
    is_anomaly: bool
    mean: float
    std: float
    threshold: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "z_score": self.z_score,
            "is_anomaly": self.is_anomaly,
            "mean": self.mean,
            "std": self.std,
            "threshold": self.threshold,
        }


def train(
    values: List[float],
    percentile: float = 99.5,
    min_points: int = 3,
) -> ZScoreModel:
    """Train a Z-Score model from a list of values.
    
    This is a PURE statistical function. No timestamps, no buckets.
    
    Args:
        values: List of numeric values to train on
        percentile: Percentile for threshold calculation (default 99.5)
        min_points: Minimum points required for valid statistics (default 3)
    
    Returns:
        ZScoreModel with mean, std, threshold
    
    Raises:
        ValueError: If values is empty
    """
    if not values:
        raise ValueError("Cannot train on empty values")
    
    arr = np.array(values, dtype=float)
    n_points = len(arr)
    
    mean = float(np.mean(arr))
    std = float(np.std(arr))
    
    # Prevent division by zero
    if std == 0 or np.isnan(std):
        std = 1e-6
    
    # Calculate z-scores and threshold
    z_scores = np.abs((arr - mean) / std)
    threshold = float(np.percentile(z_scores, percentile)) if n_points >= min_points else 3.0
    
    return ZScoreModel(
        mean=mean,
        std=std,
        threshold=threshold,
        data_points=n_points,
        percentile=percentile,
    )


def detect(
    value: float,
    model: ZScoreModel,
) -> AnomalyResult:
    """Detect if a single value is anomalous based on trained model.
    
    This is a PURE statistical function. No timestamps, no buckets.
    
    Args:
        value: The value to check
        model: Trained ZScoreModel
    
    Returns:
        AnomalyResult with z_score and is_anomaly flag
    """
    z_score = (value - model.mean) / model.std
    is_anomaly = abs(z_score) > model.threshold
    
    return AnomalyResult(
        value=value,
        z_score=z_score,
        is_anomaly=is_anomaly,
        mean=model.mean,
        std=model.std,
        threshold=model.threshold,
    )


def detect_batch(
    values: List[float],
    model: ZScoreModel,
) -> List[AnomalyResult]:
    """Detect anomalies for a batch of values.
    
    Args:
        values: List of values to check
        model: Trained ZScoreModel
    
    Returns:
        List of AnomalyResult objects
    """
    return [detect(v, model) for v in values]


# === CONVENIENCE FUNCTIONS ===================================================

def train_from_dict(
    values: List[float],
    percentile: float = 99.5,
    min_points: int = 3,
) -> Dict[str, Any]:
    """Train and return result as dict (for MongoDB storage)."""
    model = train(values, percentile, min_points)
    return model.to_dict()


def detect_from_dict(
    value: float,
    model_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """Detect using dict model (from MongoDB)."""
    model = ZScoreModel.from_dict(model_dict)
    result = detect(value, model)
    return result.to_dict()


# === GLOBAL FALLBACK =========================================================

def create_global_fallback(
    all_values: List[float],
    percentile: float = 99.5,
) -> ZScoreModel:
    """Create a global fallback model from all training data.
    
    Use this when a specific bucket has insufficient data.
    
    Args:
        all_values: All training values across all buckets
        percentile: Threshold percentile
    
    Returns:
        ZScoreModel to use as fallback
    """
    if not all_values:
        # Return a permissive fallback
        return ZScoreModel(
            mean=0.0,
            std=1.0,
            threshold=3.0,
            data_points=0,
            percentile=percentile,
        )
    return train(all_values, percentile)
