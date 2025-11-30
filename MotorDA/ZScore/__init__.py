"""ZScore Anomaly Detection Algorithm Package.

This package provides a PURE statistical Z-Score algorithm.
NO bucket logic - bucketing is the Dispatcher's responsibility.

Usage:
    from MotorDA.ZScore import zscore_algorithm as zscore
    
    # Train on values
    baseline = zscore.train(values, percentile=99.5)
    
    # Detect anomalies
    result = zscore.detect(value, baseline)
    if result.is_anomaly:
        print(f"Anomaly detected! z-score: {result.z_score}")
"""

from MotorDA.ZScore.zscore_algorithm import (
    train,
    detect,
    detect_batch,
    train_from_dict,
    detect_from_dict,
    create_global_fallback,
    ZScoreBaseline,
    AnomalyResult,
)

__all__ = [
    "train",
    "detect",
    "detect_batch",
    "train_from_dict",
    "detect_from_dict",
    "create_global_fallback",
    "ZScoreBaseline",
    "AnomalyResult",
]
