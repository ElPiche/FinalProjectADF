"""ZScore Anomaly Detection Algorithm Package.

This package provides a PURE statistical Z-Score algorithm.
NO bucket logic - bucketing is the Dispatcher's responsibility.

Usage:
    # Using the BaseAlgorithm interface (recommended)
    from MotorDA.ZScore.algorithm import ZScoreAlgorithm
    
    algo = ZScoreAlgorithm()
    result = algo.train(data_points)
    detection = algo.detect(value, result.baseline)
    
    # Using the pure functions (for orchestrator)
    from MotorDA.ZScore import zscore_algorithm as zscore
    
    # Train on values
    baseline = zscore.train(values, percentile=99.5)
    
    # Detect anomalies
    result = zscore.detect(value, baseline)
    if result.is_anomaly:
        print(f"Anomaly detected! z-score: {result.z_score}")
"""

# Support both import styles
try:
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
    from MotorDA.ZScore.algorithm import ZScoreAlgorithm
except ImportError:
    from ZScore.zscore_algorithm import (
        train,
        detect,
        detect_batch,
        train_from_dict,
        detect_from_dict,
        create_global_fallback,
        ZScoreBaseline,
        AnomalyResult,
    )
    from ZScore.algorithm import ZScoreAlgorithm

__all__ = [
    # Pure functions
    "train",
    "detect",
    "detect_batch",
    "train_from_dict",
    "detect_from_dict",
    "create_global_fallback",
    "ZScoreBaseline",
    "AnomalyResult",
    # BaseAlgorithm class
    "ZScoreAlgorithm",
]
