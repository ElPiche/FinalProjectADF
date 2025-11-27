"""Base Algorithm Classes for Anomaly Detection Framework.

This module defines the abstract base class and enums for all anomaly detection
algorithms. It supports:
- POINT algorithms (single value detection) - Phase 1
- SERIES algorithms (time window detection) - Phase 2
- Different bucket modes (segment, feature, metadata-only)

Usage:
    from MotorDA.base_algorithm import BaseAlgorithm, DetectionMode, BucketMode

    class MyAlgorithm(BaseAlgorithm):
        name = "myalgorithm"
        display_name = "My Algorithm"
        detection_mode = DetectionMode.POINT
        bucket_mode = BucketMode.SEGMENT
        
        def train(self, data, bucket_key=None, metadata=None):
            ...
        
        def detect(self, value, baseline, metadata=None):
            ...
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class DetectionMode(Enum):
    """How the algorithm processes data for detection.
    
    POINT: Each data point is evaluated independently.
           The detect() method receives a single value.
           Examples: Z-Score, IQR, K-Means, Threshold
           
    SERIES: Detection requires a window of recent values.
            The detect() method receives value + history.
            Examples: ARMA, ARMAX, Prophet, LSTM
            
    BATCH: Detection processes many values at once.
           Not currently supported.
           Examples: Autoencoder batch inference
    """
    POINT = "point"
    SERIES = "series"
    BATCH = "batch"  # Future use


class BucketMode(Enum):
    """How the algorithm uses time-context buckets.
    
    SEGMENT: Training data is split by bucket key.
             A separate model/baseline is trained per bucket.
             At detection, the bucket's specific model is used.
             Best for: Z-Score, IQR, K-Means
             
    FEATURE: Bucket information is passed as input features.
             Training data stays continuous (not split).
             Bucket features (is_workday, hour, etc.) are inputs.
             Best for: ARMAX, Prophet, LSTM
             
    METADATA_ONLY: Bucket is not used in training or detection.
                   Only attached to anomaly output for context.
                   Use when: Algorithm doesn't benefit from time context
    """
    SEGMENT = "segment"
    FEATURE = "feature"
    METADATA_ONLY = "metadata_only"


@dataclass
class TrainingResult:
    """Result of training an algorithm on a dataset.
    
    Attributes:
        baseline: Algorithm-specific trained model/statistics
        data_points: Number of training points used
        sufficient_data: Whether there was enough data for reliable training
        metadata: Additional algorithm-specific metadata
    """
    baseline: Dict[str, Any]
    data_points: int
    sufficient_data: bool
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for MongoDB storage."""
        result = {
            **self.baseline,
            "data_points": self.data_points,
            "sufficient_data": self.sufficient_data,
        }
        if self.metadata:
            result["_metadata"] = self.metadata
        return result


@dataclass
class DetectionResult:
    """Result of running anomaly detection on a value.
    
    Attributes:
        is_anomaly: Whether the value is anomalous
        algorithm_details: Algorithm-specific detection details
        confidence: Optional confidence score (0-1)
    """
    is_anomaly: bool
    algorithm_details: Dict[str, Any]
    confidence: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for anomaly document."""
        result = {
            "is_anomaly": self.is_anomaly,
            **self.algorithm_details,
        }
        if self.confidence is not None:
            result["confidence"] = self.confidence
        return result


class BaseAlgorithm(ABC):
    """Abstract base class for all anomaly detection algorithms.
    
    Subclasses must:
    1. Set class attributes: name, display_name, detection_mode, bucket_mode
    2. Implement train() method
    3. Implement detect() method
    4. Optionally override required_history_length for SERIES mode
    5. Optionally override format_anomaly_text() for custom messages
    
    Example:
        class IQRAlgorithm(BaseAlgorithm):
            name = "iqr"
            display_name = "Interquartile Range"
            detection_mode = DetectionMode.POINT
            bucket_mode = BucketMode.SEGMENT
            
            def train(self, data, bucket_key=None, metadata=None):
                values = [d["value"] for d in data]
                q1, q3 = np.percentile(values, [25, 75])
                iqr = q3 - q1
                return TrainingResult(
                    baseline={"q1": q1, "q3": q3, "iqr": iqr,
                              "lower": q1 - 1.5*iqr, "upper": q3 + 1.5*iqr},
                    data_points=len(values),
                    sufficient_data=len(values) >= 10,
                )
            
            def detect(self, value, baseline, metadata=None):
                is_anomaly = value < baseline["lower"] or value > baseline["upper"]
                return DetectionResult(
                    is_anomaly=is_anomaly,
                    algorithm_details={
                        "value": value,
                        "lower_bound": baseline["lower"],
                        "upper_bound": baseline["upper"],
                        "q1": baseline["q1"],
                        "q3": baseline["q3"],
                    }
                )
    """
    
    # Class attributes - must be overridden by subclasses
    name: str = NotImplemented
    display_name: str = NotImplemented
    detection_mode: DetectionMode = NotImplemented
    bucket_mode: BucketMode = NotImplemented
    
    @property
    def required_history_length(self) -> int:
        """Number of historical values needed for SERIES mode detection.
        
        Override this in SERIES mode algorithms to specify how many
        previous values are needed for prediction/detection.
        
        Returns:
            0 for POINT mode algorithms
            N for SERIES mode algorithms (where N > 0)
        """
        return 0
    
    @property 
    def minimum_training_points(self) -> int:
        """Minimum number of data points needed for reliable training.
        
        Override this if your algorithm has specific data requirements.
        
        Returns:
            Default is 3 for basic statistics.
        """
        return 3
    
    @abstractmethod
    def train(
        self,
        data: List[Dict[str, Any]],
        bucket_key: Optional[str] = None,
        bucket_features: Optional[Dict[str, float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TrainingResult:
        """Train the algorithm on a dataset.
        
        For SEGMENT bucket mode:
            - data contains only points for this bucket
            - bucket_key identifies which bucket
            
        For FEATURE bucket mode:
            - data contains ALL points (continuous series)
            - bucket_features provides feature columns
            
        For METADATA_ONLY bucket mode:
            - data contains ALL points
            - bucket information is not used
        
        Args:
            data: List of data points, each with at least:
                  - "timestamp": datetime or ISO string
                  - "value": numeric value
                  Additional fields depend on algorithm.
                  
            bucket_key: For SEGMENT mode, identifies the bucket.
                       None for other modes.
                       
            bucket_features: For FEATURE mode, dict of feature values.
                            Example: {"is_workday": 1, "hour": 9}
                            None for other modes.
                            
            metadata: Algorithm-specific parameters from KB config.
                     Example: {"percentile": 99.5}
        
        Returns:
            TrainingResult containing the trained baseline/model.
        """
        pass
    
    @abstractmethod
    def detect(
        self,
        value: float,
        baseline: Dict[str, Any],
        history: Optional[List[Dict[str, Any]]] = None,
        bucket_features: Optional[Dict[str, float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DetectionResult:
        """Detect if a value is anomalous.
        
        For POINT mode:
            - Only value and baseline are used
            - history is ignored
            
        For SERIES mode:
            - history contains the last N values
            - N = required_history_length
            
        For FEATURE bucket mode:
            - bucket_features provides current bucket context
        
        Args:
            value: The current value to check for anomaly.
            
            baseline: Trained model/statistics from train().
                     Structure depends on algorithm.
                     
            history: For SERIES mode, list of recent data points.
                    Each point has "timestamp" and "value".
                    Ordered oldest to newest.
                    None for POINT mode.
                    
            bucket_features: For FEATURE bucket mode, current bucket context.
                            Example: {"is_workday": 1, "hour": 14}
                            None for SEGMENT or METADATA_ONLY modes.
                            
            metadata: Algorithm-specific parameters from KB config.
        
        Returns:
            DetectionResult with is_anomaly flag and algorithm details.
        """
        pass
    
    def format_anomaly_text(
        self, 
        value: float, 
        details: Dict[str, Any],
        bucket_key: Optional[str] = None,
    ) -> str:
        """Generate human-readable description of the anomaly.
        
        Override this to provide algorithm-specific descriptions.
        
        Args:
            value: The anomalous value
            details: Algorithm-specific details from detect()
            bucket_key: Optional bucket context
            
        Returns:
            Human-readable anomaly description
        """
        bucket_context = f" in bucket '{bucket_key}'" if bucket_key else ""
        return f"Anomaly detected by {self.display_name}{bucket_context}"
    
    def validate_config(self, metadata: Dict[str, Any]) -> List[str]:
        """Validate algorithm-specific configuration parameters.
        
        Override this to validate algorithm parameters from KB config.
        
        Args:
            metadata: Algorithm parameters from KB config
            
        Returns:
            List of error messages (empty if valid)
        """
        return []
    
    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"name='{self.name}', "
            f"mode={self.detection_mode.value}, "
            f"bucket={self.bucket_mode.value})"
        )
