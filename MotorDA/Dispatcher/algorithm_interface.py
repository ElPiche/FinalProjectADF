"""Algorithm Interface - Protocol + Registry for Anomaly Detection Algorithms.

This module defines the interface contract for all anomaly detection algorithms
and provides a registry for dynamic algorithm lookup.

Design Pattern: Protocol (structural subtyping) + Registry (factory pattern)

Usage:
    from MotorDA.Dispatcher.algorithm_interface import get_algorithm, ALGORITHM_REGISTRY
    
    # Get an algorithm by name
    algorithm = get_algorithm("zscore")
    
    # Train a baseline
    baseline = algorithm.train(values=[10, 20, 30], percentile=99.5)
    
    # Detect anomaly
    result = algorithm.detect(value=100.0, baseline=baseline)
    
    # Check available algorithms
    print(list(ALGORITHM_REGISTRY.keys()))  # ['zscore']
"""

from __future__ import annotations

from typing import Protocol, Dict, Any, List, runtime_checkable
from dataclasses import dataclass

import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


@runtime_checkable
class AnomalyAlgorithm(Protocol):
    """Interface for anomaly detection algorithms.
    
    All anomaly detection algorithms MUST implement this protocol.
    
    This is a PURE statistical interface - no bucket logic here.
    Bucketing is the Dispatcher/Orchestrator's responsibility.
    
    Methods:
        name: Algorithm identifier (e.g., 'zscore', 'arma', 'kmeans')
        train: Train a baseline from values
        detect: Detect if a single value is anomalous
        detect_batch: Detect anomalies for multiple values
    """
    
    @property
    def name(self) -> str:
        """Algorithm identifier (e.g., 'zscore', 'arma', 'kmeans')."""
        ...
    
    def train(self, values: List[float], percentile: float = 99.5, **kwargs) -> Dict[str, Any]:
        """Train model from values, return serializable baseline.
        
        Args:
            values: List of numeric values to train on
            percentile: Percentile for threshold calculation
            **kwargs: Algorithm-specific parameters
        
        Returns:
            Dict containing the trained baseline (must be JSON-serializable)
        """
        ...
    
    def detect(self, value: float, baseline: Dict[str, Any]) -> Dict[str, Any]:
        """Detect if a single value is anomalous.
        
        Args:
            value: The value to check
            baseline: Trained baseline dict from train()
        
        Returns:
            Dict with at least 'is_anomaly' (bool) key
        """
        ...
    
    def detect_batch(self, values: List[float], baseline: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect anomalies for multiple values.
        
        Args:
            values: List of values to check
            baseline: Trained baseline dict from train()
        
        Returns:
            List of detection result dicts
        """
        ...


@dataclass
class ZScoreAlgorithm:
    """Z-Score implementation of AnomalyAlgorithm protocol.
    
    This is a thin wrapper around the pure zscore_algorithm module.
    It implements the AnomalyAlgorithm protocol to allow dynamic dispatch.
    
    It also provides higher-level train/detect methods that accept
    observed_values dicts (multi-dimensional) instead of raw float lists.
    """
    
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


# === ALGORITHM REGISTRY ======================================================
# This is the single source of truth for available algorithms.
# To add a new algorithm:
#   1. Create a class implementing AnomalyAlgorithm protocol
#   2. Add it to this registry

ALGORITHM_REGISTRY: Dict[str, AnomalyAlgorithm] = {
    "zscore": ZScoreAlgorithm(),
    # Future additions:
    # "arma": ARMAAlgorithm(),
    # "kmeans": KMeansAlgorithm(),
    # "isolation_forest": IsolationForestAlgorithm(),
}


def get_algorithm(name: str) -> AnomalyAlgorithm:
    """Get an algorithm by name from the registry.
    
    Args:
        name: Algorithm identifier (case-insensitive)
    
    Returns:
        AnomalyAlgorithm instance
    
    Raises:
        ValueError: If algorithm is not found
    """
    name_lower = name.lower()
    if name_lower not in ALGORITHM_REGISTRY:
        available = list(ALGORITHM_REGISTRY.keys())
        raise ValueError(f"Unknown algorithm: '{name}'. Available: {available}")
    return ALGORITHM_REGISTRY[name_lower]


def is_algorithm_registered(name: str) -> bool:
    """Check if an algorithm is registered.
    
    Args:
        name: Algorithm identifier (case-insensitive)
    
    Returns:
        True if algorithm exists in registry
    """
    return name.lower() in ALGORITHM_REGISTRY


def list_algorithms() -> List[str]:
    """List all registered algorithm names.
    
    Returns:
        List of algorithm names
    """
    return list(ALGORITHM_REGISTRY.keys())


def register_algorithm(algorithm: AnomalyAlgorithm) -> None:
    """Register a new algorithm (for testing or plugins).
    
    Args:
        algorithm: AnomalyAlgorithm instance
    """
    if not isinstance(algorithm, AnomalyAlgorithm):
        raise TypeError(f"Algorithm must implement AnomalyAlgorithm protocol, got {type(algorithm)}")
    
    name = algorithm.name.lower()
    if name in ALGORITHM_REGISTRY:
        logger.warning(f"Overwriting existing algorithm: {name}")
    
    ALGORITHM_REGISTRY[name] = algorithm
    logger.info(f"Registered algorithm: {name}")


# === VERIFICATION ============================================================
# Ensure ZScoreAlgorithm implements the protocol
def _verify_protocol_implementation():
    """Verify that ZScoreAlgorithm implements AnomalyAlgorithm protocol."""
    algo = ZScoreAlgorithm()
    assert isinstance(algo, AnomalyAlgorithm), "ZScoreAlgorithm must implement AnomalyAlgorithm protocol"
    assert hasattr(algo, 'name')
    assert hasattr(algo, 'train')
    assert hasattr(algo, 'detect')
    assert hasattr(algo, 'detect_batch')

_verify_protocol_implementation()
