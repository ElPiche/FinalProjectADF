"""Mock Algorithm - Simple threshold-based detection for testing.

This is a minimal algorithm implementation for testing and demonstration.
Shows the bare minimum needed to implement a new algorithm.
"""

from dataclasses import dataclass
from typing import Dict, Any, List
import logging

from ...algorithm_interface import register_algorithm

logger = logging.getLogger(__name__)


@register_algorithm
@dataclass
class MockAlgorithm:
    """Mock algorithm for testing and demonstration.
    
    Simple threshold-based detection: flags values that deviate
    from the mean by more than threshold.
    
    Algorithm Properties:
        is_multi_dimensional: False - trains/detects one dimension at a time
        supports_bucketing: True - separate model per time-context bucket
        min_training_samples: 1 - minimal requirement for testing
    """
    
    __algorithm_meta__ = {
        "description": "Mock algorithm for testing and demonstration",
        "parameters": ["percentile"],
    }
    
    # ─────────────────────────────────────────────────────────────────────────────
    # Algorithm Interface Properties (Phase 2)
    # ─────────────────────────────────────────────────────────────────────────────
    
    @property
    def name(self) -> str:
        return "mock"
    
    @property
    def is_multi_dimensional(self) -> bool:
        """Mock processes dimensions independently (single-dimensional)."""
        return False
    
    @property
    def supports_bucketing(self) -> bool:
        """Mock supports separate models per time-context bucket."""
        return True
    
    @property
    def min_training_samples(self) -> int:
        """Minimal requirement for testing purposes."""
        return 1
    
    def train(self, values: List[float], parameter: Dict[str, Any] = None, **_) -> Dict[str, Any]:
        """Train: compute mean and fixed threshold.
        
        Args:
            values: List of numeric values
            parameter: Algorithm parameter dict with optional metadata overrides:
                - percentile: via metadata[key="percentile"].value (default: 95.0)
        
        Returns:
            Baseline dict with mean, threshold, data_points
        """
        # ─────────────────────────────────────────────────────────────────────────
        # Resolve parameters: metadata overrides > defaults (User-Overridable Pattern)
        # ─────────────────────────────────────────────────────────────────────────
        percentile = 95.0  # Algorithm default
        
        if parameter:
            for meta in parameter.get("metadata", []):
                key = meta.get("key")
                val = meta.get("value")
                if key == "percentile" and val is not None:
                    try:
                        percentile = float(val)
                    except (ValueError, TypeError):
                        pass
        
        if not values:
            return {"mean": 0.0, "threshold": 10.0}
        mean = sum(values) / len(values)
        return {
            "mean": mean,
            "threshold": percentile / 10.0,
            "data_points": len(values),
        }
    
    def train_multi_dimension(
        self,
        observed_values: List[Dict[str, Any]],
        parameters: List[Dict[str, Any]],
        percentile: float = 95.0,
        **_  # Accept additional kwargs for API compatibility
    ) -> Dict[str, Any]:
        """Train mock baseline for multiple dimensions.
        
        Args:
            observed_values: List of observation dicts
            parameters: Algorithm parameters with 'dimension' keys
            percentile: Threshold parameter
            **_: Additional kwargs (ignored)
        
        Returns:
            Dict with per-dimension baselines
        """
        result = {}
        
        for param in parameters:
            dimension = param.get("dimension")
            if not dimension:
                continue
            
            # Extract values for this dimension
            values = []
            for obs in observed_values:
                val = obs.get(dimension)
                if val is not None:
                    try:
                        values.append(float(val))
                    except (ValueError, TypeError):
                        pass
            
            if values:
                baseline = self.train(values, percentile)
                result[dimension] = baseline
                logger.info(f"[MOCK] Trained dimension '{dimension}' with {len(values)} values")
        
        return result
    
    def detect(self, value: float, baseline: Dict[str, Any], parameter: Dict[str, Any] = None) -> Dict[str, Any]:
        """Detect: check if value deviates from mean beyond threshold.
        
        Args:
            value: The value to check
            baseline: Trained baseline dict
            parameter: Algorithm parameter dict (unused for detection, threshold from baseline)
        
        Returns:
            Dict with is_anomaly, deviation, threshold
        """
        mean = baseline.get("mean", 0.0)
        threshold = baseline.get("threshold", 10.0)
        deviation = abs(value - mean)
        is_anomaly = deviation > threshold
        return {
            "is_anomaly": is_anomaly,
            "value": value,
            "deviation": deviation,
            "threshold": threshold,
        }
    
    def detect_batch(self, values: List[float], baseline: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect batch: map detect over values."""
        return [self.detect(v, baseline) for v in values]
    
    def detect_multi_dimension(
        self,
        observation: Dict[str, Any],
        baselines: Dict[str, Any],
        parameters: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Detect if observation is anomalous across dimensions.
        
        Args:
            observation: Observation dict with dimension values
            baselines: Per-dimension baselines from training
            parameters: Algorithm parameters
        
        Returns:
            Detection result with is_anomaly and dimension_results
        """
        dimension_results = {}
        is_anomaly = False
        
        for param in parameters:
            dimension = param.get("dimension")
            if not dimension:
                continue
            
            baseline = baselines.get(dimension)
            if baseline is None:
                continue
            
            value = observation.get(dimension)
            if value is None:
                continue
            
            try:
                result = self.detect(float(value), baseline)
                dimension_results[dimension] = result
                if result.get("is_anomaly", False):
                    is_anomaly = True
            except (ValueError, TypeError):
                pass
        
        return {
            "is_anomaly": is_anomaly,
            "dimension_results": dimension_results,
        }
