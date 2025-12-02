"""Z-Score Algorithm - Statistical anomaly detection.

Self-contained algorithm implementation. Uses the pure zscore_algorithm module
from MotorDA.ZScore for the actual statistical computations.
"""

from dataclasses import dataclass
from typing import Dict, Any, List
import logging

from ..algorithm_interface import register_algorithm

logger = logging.getLogger(__name__)


@register_algorithm
@dataclass
class ZScoreAlgorithm:
    """Z-Score statistical anomaly detection.
    
    Detects anomalies based on how many standard deviations a value
    is from the mean (z-score). Values beyond the threshold percentile
    are flagged as anomalies.
    """
    
    __algorithm_meta__ = {
        "description": "Z-Score statistical anomaly detection based on standard deviations from mean",
        "best_for": "Stationary time series with approximately normal distribution",
        "parameters": ["percentile", "min_points"],
    }
    
    @property
    def name(self) -> str:
        return "zscore"
    
    def train(self, values: List[float], percentile: float = 99.5, min_points: int = 3, **_) -> Dict[str, Any]:
        """Train Z-Score baseline from raw float values.
        
        Args:
            values: List of numeric values
            percentile: Percentile for threshold (default 99.5)
            min_points: Minimum points for valid stats (default 3)
        
        Returns:
            Baseline dict with mean, std, threshold
        """
        from MotorDA.ZScore import zscore_algorithm
        baseline = zscore_algorithm.train(values, percentile, min_points)
        return baseline.to_dict()
    
    def train_multi_dimension(
        self,
        observed_values: List[Dict[str, Any]],
        parameters: List[Dict[str, Any]],
        percentile: float = 99.5
    ) -> Dict[str, Any]:
        """Train Z-Score baseline for multiple dimensions.
        
        This is the high-level interface used by TrainingOrchestrator.
        
        Args:
            observed_values: List of observation dicts with dimension values
            parameters: Algorithm parameters with 'dimension' keys
            percentile: Percentile for threshold calculation
        
        Returns:
            Dict with per-dimension baselines: {dimension_name: baseline_dict}
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
            
            if len(values) >= 3:  # Minimum points
                baseline = self.train(values, percentile)
                result[dimension] = baseline
                logger.info(f"[ZSCORE] Trained dimension '{dimension}' with {len(values)} values")
            else:
                logger.warning(f"[ZSCORE] Insufficient values for dimension '{dimension}': {len(values)}")
        
        return result
    
    def detect(self, value: float, baseline: Dict[str, Any]) -> Dict[str, Any]:
        """Detect if a single value is anomalous based on trained baseline.
        
        Args:
            value: The value to check
            baseline: Trained baseline dict
        
        Returns:
            Dict with is_anomaly, z_score, etc.
        """
        from MotorDA.ZScore import zscore_algorithm
        baseline_obj = zscore_algorithm.ZScoreBaseline.from_dict(baseline)
        result = zscore_algorithm.detect(value, baseline_obj)
        return result.to_dict()
    
    def detect_multi_dimension(
        self,
        observation: Dict[str, Any],
        baselines: Dict[str, Dict[str, Any]],
        parameters: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Detect anomalies across multiple dimensions.
        
        This is the high-level interface used by DetectionOrchestrator.
        
        Args:
            observation: Observation dict with dimension values
            baselines: Per-dimension baselines from train_multi_dimension
            parameters: Algorithm parameters with 'dimension' keys
        
        Returns:
            Dict with is_anomaly, dimension_results, etc.
        """
        dimension_results = {}
        is_any_anomaly = False
        
        for param in parameters:
            dimension = param.get("dimension")
            if not dimension:
                continue
            
            baseline = baselines.get(dimension)
            if not baseline:
                logger.warning(f"[ZSCORE] No baseline for dimension '{dimension}'")
                continue
            
            value = observation.get(dimension)
            if value is None:
                continue
            
            try:
                value = float(value)
            except (ValueError, TypeError):
                continue
            
            result = self.detect(value, baseline)
            dimension_results[dimension] = result
            
            if result.get("is_anomaly", False):
                is_any_anomaly = True
        
        return {
            "is_anomaly": is_any_anomaly,
            "dimensions": dimension_results,
            "observation": observation
        }
    
    def detect_batch(self, values: List[float], baseline: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect anomalies for multiple values.
        
        Args:
            values: List of values to check
            baseline: Trained baseline dict
        
        Returns:
            List of detection result dicts
        """
        return [self.detect(v, baseline) for v in values]
