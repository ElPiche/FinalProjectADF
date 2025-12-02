"""IQR Algorithm - Interquartile Range anomaly detection.

Self-contained algorithm using IQR (Interquartile Range) method.
Values outside Q1 - multiplier*IQR or Q3 + multiplier*IQR are anomalies.

This is a robust method that works well with non-normal distributions
and is less sensitive to extreme outliers than Z-Score.
"""

from dataclasses import dataclass
from typing import Dict, Any, List
import logging

from ...algorithm_interface import register_algorithm

logger = logging.getLogger(__name__)


@register_algorithm
@dataclass
class IQRAlgorithm:
    """Interquartile Range (IQR) anomaly detection.
    
    Uses the IQR method to detect outliers:
    - Q1 = 25th percentile
    - Q3 = 75th percentile
    - IQR = Q3 - Q1
    - Lower bound = Q1 - multiplier * IQR
    - Upper bound = Q3 + multiplier * IQR
    
    Values outside these bounds are flagged as anomalies.
    Default multiplier is 1.5 (standard) or 3.0 (extreme outliers only).
    """
    
    __algorithm_meta__ = {
        "description": "IQR-based outlier detection using quartiles, robust to non-normal distributions",
        "best_for": "Data with outliers, non-normal distributions, or when Z-Score is too sensitive",
        "parameters": ["multiplier"],
    }
    
    @property
    def name(self) -> str:
        return "iqr"
    
    def _percentile(self, values: List[float], p: float) -> float:
        """Calculate percentile of sorted values."""
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        k = (len(sorted_vals) - 1) * (p / 100.0)
        f = int(k)
        c = f + 1 if f + 1 < len(sorted_vals) else f
        return sorted_vals[f] + (k - f) * (sorted_vals[c] - sorted_vals[f])
    
    def train(self, values: List[float], multiplier: float = 1.5, **_) -> Dict[str, Any]:
        """Train IQR baseline from values.
        
        Args:
            values: List of numeric values
            multiplier: IQR multiplier for bounds (default 1.5)
        
        Returns:
            Baseline dict with q1, q3, iqr, bounds
        """
        if len(values) < 4:
            # Not enough data for quartiles
            mean = sum(values) / len(values) if values else 0.0
            return {
                "q1": mean,
                "q3": mean,
                "iqr": 0.0,
                "lower_bound": mean - 10.0,
                "upper_bound": mean + 10.0,
                "multiplier": multiplier,
                "data_points": len(values),
            }
        
        q1 = self._percentile(values, 25)
        q3 = self._percentile(values, 75)
        iqr = q3 - q1
        
        lower_bound = q1 - multiplier * iqr
        upper_bound = q3 + multiplier * iqr
        
        logger.info(f"[IQR] Trained: Q1={q1:.2f}, Q3={q3:.2f}, IQR={iqr:.2f}, bounds=[{lower_bound:.2f}, {upper_bound:.2f}]")
        
        return {
            "q1": q1,
            "q3": q3,
            "iqr": iqr,
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
            "multiplier": multiplier,
            "data_points": len(values),
        }
    
    def train_multi_dimension(
        self,
        observed_values: List[Dict[str, Any]],
        parameters: List[Dict[str, Any]],
        multiplier: float = 1.5,
        **_  # Accept but ignore additional kwargs (e.g., percentile from orchestrator)
    ) -> Dict[str, Any]:
        """Train IQR baseline for multiple dimensions.
        
        Args:
            observed_values: List of observation dicts with dimension values
            parameters: Algorithm parameters with 'dimension' keys
            multiplier: IQR multiplier for bounds
            **_: Additional kwargs (ignored for API compatibility)
        
        Returns:
            Dict with per-dimension baselines
        """
        result = {}
        
        for param in parameters:
            dimension = param.get("dimension")
            if not dimension:
                continue
            
            # Get multiplier from metadata if provided
            dim_multiplier = multiplier
            for meta in param.get("metadata", []):
                if meta.get("key") == "multiplier":
                    try:
                        dim_multiplier = float(meta.get("value", multiplier))
                    except (ValueError, TypeError):
                        pass
            
            # Extract values for this dimension
            values = []
            for obs in observed_values:
                val = obs.get(dimension)
                if val is not None:
                    try:
                        values.append(float(val))
                    except (ValueError, TypeError):
                        pass
            
            if len(values) >= 4:  # Need at least 4 for quartiles
                baseline = self.train(values, dim_multiplier)
                result[dimension] = baseline
                logger.info(f"[IQR] Trained dimension '{dimension}' with {len(values)} values")
            else:
                logger.warning(f"[IQR] Insufficient values for dimension '{dimension}': {len(values)} (need 4+)")
        
        return result
    
    def detect(self, value: float, baseline: Dict[str, Any]) -> Dict[str, Any]:
        """Detect if value is outside IQR bounds.
        
        Args:
            value: The value to check
            baseline: Trained baseline dict
        
        Returns:
            Dict with is_anomaly, bounds, etc.
        """
        lower = baseline.get("lower_bound", float("-inf"))
        upper = baseline.get("upper_bound", float("inf"))
        
        is_anomaly = value < lower or value > upper
        
        # Calculate how far outside bounds (0 if inside)
        if value < lower:
            distance = lower - value
        elif value > upper:
            distance = value - upper
        else:
            distance = 0.0
        
        return {
            "is_anomaly": is_anomaly,
            "value": value,
            "lower_bound": lower,
            "upper_bound": upper,
            "distance_from_bounds": distance,
            "q1": baseline.get("q1"),
            "q3": baseline.get("q3"),
        }
    
    def detect_multi_dimension(
        self,
        observation: Dict[str, Any],
        baselines: Dict[str, Dict[str, Any]],
        parameters: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Detect anomalies across multiple dimensions.
        
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
                logger.warning(f"[IQR] No baseline for dimension '{dimension}'")
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
