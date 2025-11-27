"""ARMAX Algorithm - BaseAlgorithm Implementation.

This module wraps the ARMAX statistical functions into a BaseAlgorithm
compliant class for use with the algorithm registry.

ARMAX is a SERIES mode algorithm:
- Requires history at detection time
- Uses bucket features (BucketMode.FEATURE)
- Trained on continuous time series (not split by bucket)

Usage:
    from MotorDA.ARMAX.algorithm import ARMAXAlgorithm
    
    algo = ARMAXAlgorithm()
    result = algo.train(data)
    detection = algo.detect(value, result.baseline, history=history)
"""

from typing import Any, Dict, List, Optional

# Support both import styles
try:
    from MotorDA.base_algorithm import (
        BaseAlgorithm,
        DetectionMode,
        BucketMode,
        TrainingResult,
        DetectionResult,
    )
    from MotorDA.ARMAX import armax_core
except ImportError:
    from base_algorithm import (
        BaseAlgorithm,
        DetectionMode,
        BucketMode,
        TrainingResult,
        DetectionResult,
    )
    from ARMAX import armax_core


class ARMAXAlgorithm(BaseAlgorithm):
    """ARMAX based anomaly detection algorithm.
    
    This is a SERIES algorithm using FEATURE bucket mode:
    - Detection requires historical values (window)
    - Bucket features are input to the model, not data splitters
    - Single model trained on continuous time series
    
    Parameters (from KB config metadata):
    - order: Tuple (p, d, q) for ARMAX order (default: (2, 0, 2))
    - threshold_multiplier: How many residual stds for anomaly (default: 3.0)
    - exog_features: Features to use (default: ["hour", "is_workday"])
    
    Training produces:
    - AR coefficients for autoregressive component
    - MA coefficients for moving average component
    - Exogenous coefficients for time features
    - Residual std for threshold calculation
    
    Detection:
    - Predicts next value from history + features
    - Compares prediction error to threshold
    - Large errors indicate anomalies
    """
    
    name = "armax"
    display_name = "ARMAX"
    detection_mode = DetectionMode.SERIES
    bucket_mode = BucketMode.FEATURE
    
    @property
    def required_history_length(self) -> int:
        """ARMAX needs history for AR component.
        
        Default is 10 - allows for p=2 with some buffer.
        """
        return 10
    
    @property
    def minimum_training_points(self) -> int:
        """ARMAX needs more data for reliable parameter estimation."""
        return 20
    
    def train(
        self,
        data: List[Dict[str, Any]],
        bucket_key: Optional[str] = None,
        bucket_features: Optional[Dict[str, float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TrainingResult:
        """Train ARMAX model on time series data.
        
        Unlike POINT algorithms, data should be continuous (not split by bucket).
        Bucket features can be in the data points for training.
        
        Args:
            data: List of {"timestamp": ..., "value": ..., "hour": ..., "is_workday": ...}
            bucket_key: Not used (FEATURE mode)
            bucket_features: Not used (features are in data)
            metadata: Optional {"order": [2,0,2], "threshold_multiplier": 3.0}
        
        Returns:
            TrainingResult with ARMAX model parameters
        """
        metadata = metadata or {}
        
        # Extract parameters
        order_raw = metadata.get("order", [2, 0, 2])
        if isinstance(order_raw, list):
            order = tuple(order_raw)
        else:
            order = (2, 0, 2)
        
        threshold_multiplier = float(metadata.get("threshold_multiplier", 3.0))
        exog_features = metadata.get("exog_features", ["hour", "is_workday"])
        
        if not data:
            return TrainingResult(
                baseline={
                    "model_type": "armax",
                    "order": list(order),
                    "data_points": 0,
                    "training_mean": 0.0,
                    "training_std": 1.0,
                    "residual_std": 1.0,
                    "threshold_multiplier": threshold_multiplier,
                    "anomaly_threshold": threshold_multiplier,
                },
                data_points=0,
                sufficient_data=False,
            )
        
        # Train ARMAX model
        model = armax_core.train_armax(
            data=data,
            order=order,
            exog_features=exog_features,
            threshold_multiplier=threshold_multiplier,
            min_training_points=self.minimum_training_points,
        )
        
        # Convert to baseline dict
        baseline = model.to_dict()
        baseline["model_type"] = "armax"
        
        return TrainingResult(
            baseline=baseline,
            data_points=model.data_points,
            sufficient_data=model.data_points >= self.minimum_training_points,
        )
    
    def detect(
        self,
        value: float,
        baseline: Dict[str, Any],
        history: Optional[List[Dict[str, Any]]] = None,
        bucket_features: Optional[Dict[str, float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DetectionResult:
        """Detect if a value is anomalous using ARMAX model.
        
        Args:
            value: The current value to check
            baseline: Trained model parameters from train()
            history: Required - list of recent values (oldest to newest)
            bucket_features: Current time features {"hour": 14, "is_workday": 1}
            metadata: Not used
        
        Returns:
            DetectionResult with prediction error and is_anomaly
        """
        # Convert baseline to model
        model = armax_core.ARMAXModel.from_dict(baseline)
        
        # Check history
        if history is None or len(history) < self.required_history_length:
            return DetectionResult(
                is_anomaly=False,
                algorithm_details={
                    "error": f"Insufficient history: {len(history or [])} < {self.required_history_length}",
                    "predicted_value": model.training_mean,
                    "actual_value": value,
                    "prediction_error": 0,
                    "threshold": 0,
                },
            )
        
        # Run detection
        result = armax_core.detect_armax(
            model=model,
            actual_value=value,
            history=history,
            current_exog=bucket_features,
        )
        
        return DetectionResult(
            is_anomaly=result.is_anomaly,
            algorithm_details={
                "predicted_value": result.predicted_value,
                "actual_value": result.actual_value,
                "prediction_error": result.prediction_error,
                "threshold": result.threshold,
                "model_order": list(model.order),
            },
            confidence=result.confidence,
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
        predicted = details.get("predicted_value", 0)
        error = details.get("prediction_error", 0)
        threshold = details.get("threshold", 0)
        
        bucket_context = ""
        if bucket_key:
            if bucket_key.startswith("workday_"):
                hour = bucket_key.split("_")[1] if "_" in bucket_key else "unknown"
                bucket_context = f" during workday hour {hour}"
            elif bucket_key.startswith("weekend"):
                bucket_context = " during weekend"
            else:
                bucket_context = f" in context '{bucket_key}'"
        
        return (
            f"ARMAX prediction error {error:.2f} exceeds threshold {threshold:.2f}"
            f" (predicted: {predicted:.2f}, actual: {value:.2f}){bucket_context}"
        )
    
    def validate_config(self, metadata: Dict[str, Any]) -> List[str]:
        """Validate algorithm configuration.
        
        Args:
            metadata: Algorithm parameters from KB config
        
        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        
        order = metadata.get("order")
        if order is not None:
            if not isinstance(order, (list, tuple)):
                errors.append(f"order must be a list/tuple [p, d, q], got {type(order).__name__}")
            elif len(order) != 3:
                errors.append(f"order must have 3 elements [p, d, q], got {len(order)}")
            else:
                try:
                    p, d, q = [int(x) for x in order]
                    if p < 0 or d < 0 or q < 0:
                        errors.append("order values must be non-negative integers")
                    if p > 5 or q > 5:
                        errors.append("order p and q should be <= 5 for stability")
                except (TypeError, ValueError):
                    errors.append("order values must be integers")
        
        threshold = metadata.get("threshold_multiplier")
        if threshold is not None:
            try:
                t = float(threshold)
                if t <= 0:
                    errors.append(f"threshold_multiplier must be positive, got {t}")
            except (TypeError, ValueError):
                errors.append(f"threshold_multiplier must be a number")
        
        exog = metadata.get("exog_features")
        if exog is not None:
            if not isinstance(exog, list):
                errors.append(f"exog_features must be a list, got {type(exog).__name__}")
            elif not all(isinstance(f, str) for f in exog):
                errors.append("exog_features must contain strings")
        
        return errors


# Singleton instance for registry
armax_algorithm_instance = ARMAXAlgorithm()
