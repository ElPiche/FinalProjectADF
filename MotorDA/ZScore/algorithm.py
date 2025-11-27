"""Z-Score Algorithm - BaseAlgorithm Implementation.

This module wraps the pure Z-Score statistical functions into a BaseAlgorithm
compliant class for use with the algorithm registry.

The actual statistics are still in zscore_algorithm.py - this class just
provides the standard interface.

Usage:
    from MotorDA.ZScore.algorithm import ZScoreAlgorithm
    
    algo = ZScoreAlgorithm()
    result = algo.train(data)
    detection = algo.detect(value, result.baseline)
"""

from typing import Any, Dict, List, Optional

# Support both import styles (from MotorDA or from within MotorDA)
try:
    from MotorDA.base_algorithm import (
        BaseAlgorithm,
        DetectionMode,
        BucketMode,
        TrainingResult,
        DetectionResult,
    )
    from MotorDA.ZScore import zscore_algorithm as zscore
except ImportError:
    from base_algorithm import (
        BaseAlgorithm,
        DetectionMode,
        BucketMode,
        TrainingResult,
        DetectionResult,
    )
    from ZScore import zscore_algorithm as zscore


class ZScoreAlgorithm(BaseAlgorithm):
    """Z-Score based anomaly detection algorithm.
    
    This is a POINT algorithm using SEGMENT bucket mode:
    - Each value is evaluated independently
    - Separate baselines are trained per bucket
    
    Parameters (from KB config metadata):
    - percentile: Threshold percentile (default 99.5)
    - min_points: Minimum training points for valid baseline (default 3)
    
    Training produces:
    - mean: Average value
    - std: Standard deviation
    - threshold: Z-score threshold for anomaly detection
    
    Detection calculates:
    - z_score: How many standard deviations from mean
    - is_anomaly: True if |z_score| > threshold
    """
    
    name = "zscore"
    display_name = "Z-Score"
    detection_mode = DetectionMode.POINT
    bucket_mode = BucketMode.SEGMENT
    
    @property
    def minimum_training_points(self) -> int:
        """Z-Score needs at least 3 points for meaningful statistics."""
        return 3
    
    def train(
        self,
        data: List[Dict[str, Any]],
        bucket_key: Optional[str] = None,
        bucket_features: Optional[Dict[str, float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TrainingResult:
        """Train Z-Score baseline from data points.
        
        Args:
            data: List of {"timestamp": ..., "value": ...} dicts
            bucket_key: Bucket identifier (for logging)
            bucket_features: Not used (SEGMENT mode)
            metadata: Optional {"percentile": 99.5, "min_points": 3}
        
        Returns:
            TrainingResult with mean, std, threshold
        """
        # Extract parameters
        metadata = metadata or {}
        percentile = float(metadata.get("percentile", 99.5))
        min_points = int(metadata.get("min_points", self.minimum_training_points))
        
        # Extract values from data
        values = [float(d.get("value", 0)) for d in data if d.get("value") is not None]
        
        if not values:
            # Return empty baseline
            return TrainingResult(
                baseline={
                    "mean": 0.0,
                    "std": 1.0,
                    "threshold": 3.0,
                    "percentile": percentile,
                },
                data_points=0,
                sufficient_data=False,
                metadata={"bucket_key": bucket_key} if bucket_key else None,
            )
        
        # Use pure zscore module for statistics
        baseline = zscore.train(values, percentile, min_points)
        
        return TrainingResult(
            baseline=baseline.to_dict(),
            data_points=baseline.data_points,
            sufficient_data=baseline.data_points >= min_points,
            metadata={"bucket_key": bucket_key} if bucket_key else None,
        )
    
    def detect(
        self,
        value: float,
        baseline: Dict[str, Any],
        history: Optional[List[Dict[str, Any]]] = None,
        bucket_features: Optional[Dict[str, float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DetectionResult:
        """Detect if a value is anomalous based on trained baseline.
        
        Args:
            value: The value to check
            baseline: Trained baseline with mean, std, threshold
            history: Not used (POINT mode)
            bucket_features: Not used (SEGMENT mode)
            metadata: Not used
        
        Returns:
            DetectionResult with z_score and is_anomaly
        """
        # Convert baseline dict to ZScoreBaseline
        zscore_baseline = zscore.ZScoreBaseline.from_dict(baseline)
        
        # Use pure zscore module for detection
        result = zscore.detect(value, zscore_baseline)
        
        return DetectionResult(
            is_anomaly=result.is_anomaly,
            algorithm_details={
                "z_score": result.z_score,
                "threshold": result.threshold,
                "mean": result.mean,
                "std": result.std,
                "deviation_from_mean": value - result.mean,
            },
        )
    
    def format_anomaly_text(
        self,
        value: float,
        details: Dict[str, Any],
        bucket_key: Optional[str] = None,
    ) -> str:
        """Generate human-readable anomaly description.
        
        Args:
            value: The anomalous value
            details: Algorithm details from detect()
            bucket_key: Optional bucket context
        
        Returns:
            Human-readable description
        """
        z_score = details.get("z_score", 0)
        threshold = details.get("threshold", 0)
        
        bucket_context = ""
        if bucket_key:
            # Parse bucket key for friendly description
            if bucket_key.startswith("workday_"):
                hour = bucket_key.split("_")[1] if "_" in bucket_key else "unknown"
                bucket_context = f" during workday hour {hour}"
            elif bucket_key.startswith("weekend"):
                bucket_context = " during weekend"
            elif bucket_key.startswith("holiday"):
                bucket_context = f" on {bucket_key.replace('_', ' ')}"
            elif bucket_key == "global_default" or bucket_key == "global_fallback":
                bucket_context = ""
            else:
                bucket_context = f" in bucket '{bucket_key}'"
        
        return (
            f"Z-score {abs(z_score):.2f} exceeds threshold {threshold:.2f}"
            f"{bucket_context}"
        )
    
    def validate_config(self, metadata: Dict[str, Any]) -> List[str]:
        """Validate algorithm configuration.
        
        Args:
            metadata: Algorithm parameters from KB config
        
        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        
        percentile = metadata.get("percentile")
        if percentile is not None:
            try:
                p = float(percentile)
                if p <= 0 or p >= 100:
                    errors.append(f"percentile must be between 0 and 100, got {p}")
            except (TypeError, ValueError):
                errors.append(f"percentile must be a number, got {type(percentile).__name__}")
        
        min_points = metadata.get("min_points")
        if min_points is not None:
            try:
                mp = int(min_points)
                if mp < 1:
                    errors.append(f"min_points must be >= 1, got {mp}")
            except (TypeError, ValueError):
                errors.append(f"min_points must be an integer, got {type(min_points).__name__}")
        
        return errors


# Singleton instance for registry
zscore_algorithm_instance = ZScoreAlgorithm()
