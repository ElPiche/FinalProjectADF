"""Z-Score Algorithm - Statistical anomaly detection.

Self-contained algorithm implementation. Uses the pure zscore_algorithm module
co-located in this package for the actual statistical computations.
"""

from dataclasses import dataclass
from typing import Dict, Any, List
import logging

from ...algorithm_interface import register_algorithm

logger = logging.getLogger(__name__)


@register_algorithm
@dataclass
class ZScoreAlgorithm:
    """Z-Score statistical anomaly detection.
    
    Detects anomalies based on how many standard deviations a value
    is from the mean (z-score). Values beyond the threshold percentile
    are flagged as anomalies.
    
    Algorithm Properties:
        is_multi_dimensional: False - trains/detects one dimension at a time
        supports_bucketing: True - separate model per time-context bucket
        min_training_samples: 3 - minimum points for valid statistics
    """
    
    __algorithm_meta__ = {
        "description": "Z-Score statistical anomaly detection based on standard deviations from mean",
        "best_for": "Stationary time series with approximately normal distribution",
        "parameters": ["percentile", "min_points"],
    }
    
    # ─────────────────────────────────────────────────────────────────────────────
    # Algorithm Interface Properties (Phase 2)
    # ─────────────────────────────────────────────────────────────────────────────
    
    @property
    def name(self) -> str:
        return "zscore"
    
    @property
    def is_multi_dimensional(self) -> bool:
        """Z-Score processes dimensions independently (single-dimensional)."""
        return False
    
    @property
    def supports_bucketing(self) -> bool:
        """Z-Score supports separate models per time-context bucket."""
        return True
    
    @property
    def min_training_samples(self) -> int:
        """Minimum samples needed for meaningful statistics (mean, std)."""
        return 3
    
    def train(self, values: List[float], parameter: Dict[str, Any] = None, **_) -> Dict[str, Any]:
        """Train Z-Score model from raw float values.
        
        Args:
            values: List of numeric values
            parameter: Algorithm parameter dict with optional metadata overrides:
                - percentile: via metadata[key="percentile"].value (default: 99.5)
                - min_points: via metadata[key="min_points"].value (default: 3)
        
        Returns:
            Model dict with mean, std, threshold
        """
        # ─────────────────────────────────────────────────────────────────────────
        # Resolve parameters: metadata overrides > defaults (User-Overridable Pattern)
        # ─────────────────────────────────────────────────────────────────────────
        percentile = 99.5  # Algorithm default
        min_points = self.min_training_samples  # Use property as default
        
        if parameter:
            for meta in parameter.get("metadata", []):
                key = meta.get("key")
                val = meta.get("value")
                if key == "percentile" and val is not None:
                    try:
                        percentile = float(val)
                    except (ValueError, TypeError):
                        pass
                elif key == "min_points" and val is not None:
                    try:
                        min_points = int(val)
                    except (ValueError, TypeError):
                        pass
        
        from . import zscore_algorithm
        model = zscore_algorithm.train(values, percentile, min_points)
        return model.to_dict()
    
    def detect(self, value: float, model: Dict[str, Any], parameter: Dict[str, Any] = None) -> Dict[str, Any]:
        """Detect if a single value is anomalous based on trained model.
        
        Args:
            value: The value to check
            model: Trained model dict
            parameter: Algorithm parameter dict (unused for detection, threshold from model)
        
        Returns:
            Dict with is_anomaly, z_score, etc.
        """
        from . import zscore_algorithm
        model_obj = zscore_algorithm.ZScoreModel.from_dict(model)
        result = zscore_algorithm.detect(value, model_obj)
        return result.to_dict()
    
    def detect_batch(self, values: List[float], model: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect anomalies for multiple values.
        
        Args:
            values: List of values to check
            model: Trained model dict
        
        Returns:
            List of detection result dicts
        """
        return [self.detect(v, model) for v in values]
