"""Algorithm Interface - Protocol + Registry for Anomaly Detection Algorithms.

This module defines:
1. The AnomalyAlgorithm protocol (interface contract)
2. The ALGORITHM_REGISTRY (populated by @register_algorithm)
3. The export_registry() function (writes to shared volume for KB-MCP)

Algorithms are self-contained in the algorithms/ folder.
Import the algorithms package to register all algorithms.

Usage:
    from MotorDA.Dispatcher.algorithm_interface import get_algorithm
    from MotorDA.Dispatcher import algorithms  # Triggers registration
    
    algo = get_algorithm("zscore")
    model = algo.train([10, 20, 30], parameter={"dimension": "cpu"})
    result = algo.detect(100, model, parameter={"dimension": "cpu"})
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol, Dict, Any, List, Type, runtime_checkable, Optional, Union
from dataclasses import dataclass

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# === ALGORITHM REGISTRY ======================================================

ALGORITHM_REGISTRY: Dict[str, "AnomalyAlgorithm"] = {}


def register_algorithm(cls: Type) -> Type:
    """Decorator to auto-register an algorithm with validation.
    
    Just add @register_algorithm above your class.
    The decorator:
    1. Creates an instance
    2. Validates required properties based on mode (is_multi_dimensional)
    3. Registers it by name
    4. Exports registry to shared volume (if available)
    
    Validation rules:
    - All algorithms MUST have: name, is_multi_dimensional
    - If is_multi_dimensional=False: MUST have train(), detect()
    - If is_multi_dimensional=True: MUST have train_multi_dimensional(), detect_multi_dimensional()
    - If has resolve_multi_dimensional(): MUST have ALL four core methods
    """
    instance = cls()
    
    # === REQUIRED: Basic properties ===
    if not hasattr(instance, 'name'):
        logger.error(f"Registration failed: {cls.__name__} missing 'name' property")
        raise TypeError(f"{cls.__name__} must implement 'name' property")
    
    if not hasattr(instance, 'is_multi_dimensional'):
        logger.error(f"Registration failed: {cls.__name__} missing 'is_multi_dimensional' property")
        raise TypeError(f"{cls.__name__} must implement 'is_multi_dimensional' property")
    
    is_multi_dim = instance.is_multi_dimensional
    
    # === FAIL-FAST: Validate required methods based on mode ===
    if is_multi_dim:
        required = ['train_multi_dimensional', 'detect_multi_dimensional']
    else:
        required = ['train', 'detect']
    
    missing = [m for m in required if not hasattr(instance, m)]
    if missing:
        mode_str = "multi-dimensional" if is_multi_dim else "single-dimensional"
        logger.error(f"Registration failed: {cls.__name__} is {mode_str} but missing: {missing}")
        raise TypeError(f"{cls.__name__} is {mode_str} but missing required methods: {missing}")
    
    # === If has resolver, must implement ALL methods ===
    if hasattr(instance, 'resolve_multi_dimensional'):
        all_methods = ['train', 'detect', 'train_multi_dimensional', 'detect_multi_dimensional']
        missing = [m for m in all_methods if not hasattr(instance, m)]
        if missing:
            logger.error(f"Registration failed: {cls.__name__} has resolver but missing: {missing}")
            raise TypeError(f"{cls.__name__} has resolve_multi_dimensional() but missing: {missing}")
    
    # Register
    name = instance.name.lower()
    
    if name in ALGORITHM_REGISTRY:
        logger.warning(f"Overwriting existing algorithm: {name}")
    
    ALGORITHM_REGISTRY[name] = instance
    
    # Log registration with properties
    supports_bucketing = getattr(instance, 'supports_bucketing', True)
    min_samples = getattr(instance, 'min_training_samples', 3)
    supports_both_modes = hasattr(instance, 'resolve_multi_dimensional')
    logger.info(
        f"Registered algorithm: {name} "
        f"(multi_dimensional={is_multi_dim}, supports_both_modes={supports_both_modes}, "
        f"supports_bucketing={supports_bucketing}, min_training_samples={min_samples})"
    )
    
    # Export registry after each registration
    _export_registry_if_available()
    
    return cls


@runtime_checkable
class AnomalyAlgorithm(Protocol):
    """Interface for anomaly detection algorithms.
    
    All algorithms MUST implement this protocol.
    This is a PURE statistical interface - no bucket logic.
    
    Required Properties:
    - name: str - Algorithm identifier
    - is_multi_dimensional: bool - True if processes all dimensions together
    
    Optional Properties (with defaults):
    - supports_bucketing: bool = True - Whether to train per time-bucket
    - min_training_samples: int = 3 - Minimum data for training
    
    Required Methods (based on is_multi_dimensional):
    - If False: train(values, parameter), detect(value, model, parameter)
    - If True: train_multi_dimensional(observations, parameters), detect_multi_dimensional(observation, model, parameters)
    """
    
    @property
    def name(self) -> str:
        """Algorithm identifier (e.g., 'zscore', 'iqr', 'kmeans')."""
        ...
    
    @property
    def is_multi_dimensional(self) -> bool:
        """True if algorithm processes all dimensions together as vectors.
        
        False (single-dimensional): Each dimension has its own model.
            - train() called per dimension with values list
            - detect() called per dimension with single value
        
        True (multi-dimensional): Single model for all dimensions.
            - train_multi_dimensional() called once with all observations
            - detect_multi_dimensional() called with complete observation vector
        """
        ...
    
    # === OPTIONAL PROPERTIES (defaults applied if not implemented) ===
    
    @property
    def supports_bucketing(self) -> bool:
        """Whether to train separate model per time-context bucket.
        
        True (default): Orchestrator trains per bucket (ZScore, IQR)
        False: Orchestrator trains single global model (KMeans, DBSCAN)
        
        Either way, detections are TAGGED with bucket context for analysis.
        
        This is the ALGORITHM DEFAULT. Users can override via parameter metadata:
        {"key": "supports_bucketing", "value": false}
        """
        return True
    
    @property
    def min_training_samples(self) -> int:
        """Minimum observations required for meaningful training.
        
        This is the ALGORITHM DEFAULT. Users can override via parameter metadata:
        {"key": "min_training_samples", "value": 10}
        
        Resolution order (same pattern as percentile, n_clusters, etc.):
        1. Check parameter.metadata for "min_training_samples" → use if found
        2. Else use this property value
        
        Used by orchestrator to decide: train this bucket or fall back to global.
        """
        return 3
    
    # === SINGLE-DIMENSIONAL METHODS (required if is_multi_dimensional=False) ===
    
    def train(self, values: List[float], parameter: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        """Train model from single-dimension values, return serializable model.
        
        Args:
            values: List of numeric values for ONE dimension
            parameter: Full parameter dict (contains metadata for this dimension)
                Algorithm extracts what it needs (percentile, multiplier, etc.)
        
        Returns:
            Model dict (algorithm-specific structure, e.g., mean/std for zscore)
        """
        ...
    
    def detect(self, value: float, model: Dict[str, Any], parameter: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Detect if a single value is anomalous.
        
        Args:
            value: The value to check
            model: Trained model dict from train()
            parameter: Full parameter dict (contains metadata)
        
        Returns:
            Must include 'is_anomaly': bool
        """
        ...
    
    def detect_batch(self, values: List[float], model: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect anomalies for multiple values (single-dimensional batch)."""
        ...
    
    # === MULTI-DIMENSIONAL METHODS (required if is_multi_dimensional=True) ===
    
    def train_multi_dimensional(
        self,
        observations: List[Dict[str, Any]],
        parameters: List[Dict[str, Any]],
        **kwargs
    ) -> Dict[str, Any]:
        """Train model from observations containing multiple dimensions.
        
        Args:
            observations: List of observation dicts (each has all dimensions)
            parameters: List of parameter dicts (one per dimension, with metadata)
        
        Returns:
            Model dict (algorithm-specific structure)
        """
        ...
    
    def detect_multi_dimensional(
        self,
        observation: Dict[str, Any],
        model: Dict[str, Any],
        parameters: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Detect if an observation is anomalous.
        
        Args:
            observation: Single observation dict with all dimension values
            model: Trained model from train_multi_dimensional
            parameters: List of parameter dicts (one per dimension)
        
        Returns:
            Must include 'is_anomaly': bool
        """
        ...


# === REGISTRY ACCESS =========================================================


def get_algorithm(name: str) -> AnomalyAlgorithm:
    """Get an algorithm by name from the registry."""
    name_lower = name.lower()
    if name_lower not in ALGORITHM_REGISTRY:
        available = list(ALGORITHM_REGISTRY.keys())
        raise ValueError(f"Unknown algorithm: '{name}'. Available: {available}")
    return ALGORITHM_REGISTRY[name_lower]


def is_algorithm_supported(name: str) -> bool:
    """Check if an algorithm is registered."""
    return name.lower() in ALGORITHM_REGISTRY


def list_algorithms() -> List[str]:
    """List all registered algorithm names."""
    return list(ALGORITHM_REGISTRY.keys())


def get_algorithm_info(name: str = None) -> Dict[str, Any]:
    """Get metadata for algorithms (from __algorithm_meta__ and properties)."""
    if name:
        name_lower = name.lower()
        if name_lower not in ALGORITHM_REGISTRY:
            return None
        algo = ALGORITHM_REGISTRY[name_lower]
        meta = getattr(algo, '__algorithm_meta__', {})
        return {
            "name": name_lower,
            "is_multi_dimensional": algo.is_multi_dimensional,
            "supports_both_modes": hasattr(algo, 'resolve_multi_dimensional'),
            "supports_bucketing": getattr(algo, 'supports_bucketing', True),
            "min_training_samples": getattr(algo, 'min_training_samples', 3),
            **meta
        }
    
    result = {}
    for algo_name, algo in ALGORITHM_REGISTRY.items():
        meta = getattr(algo, '__algorithm_meta__', {})
        result[algo_name] = {
            "name": algo_name,
            "is_multi_dimensional": algo.is_multi_dimensional,
            "supports_both_modes": hasattr(algo, 'resolve_multi_dimensional'),
            "supports_bucketing": getattr(algo, 'supports_bucketing', True),
            "min_training_samples": getattr(algo, 'min_training_samples', 3),
            **meta
        }
    return result


def resolve_algorithm_mode(algorithm: Union[str, AnomalyAlgorithm], parameters: Optional[List[Dict[str, Any]]] = None) -> bool:
    """Resolve whether to use multi-dimensional mode for an algorithm.
    
    Some algorithms may support both modes and use resolve_multi_dimensional()
    to dynamically decide based on parameters.
    
    Args:
        algorithm: The algorithm instance or algorithm name string
        parameters: Algorithm parameters from config (optional, defaults to empty list)
    
    Returns:
        True if multi-dimensional mode, False if single-dimensional
    
    Raises:
        ValueError: If algorithm name not found in registry
    """
    # Handle string algorithm names by looking up the algorithm
    if isinstance(algorithm, str):
        algo_instance = get_algorithm(algorithm)
        if algo_instance is None:
            raise ValueError(f"Unknown algorithm: {algorithm}")
        algorithm = algo_instance
    
    # Default parameters to empty list
    if parameters is None:
        parameters = []
    
    if hasattr(algorithm, 'resolve_multi_dimensional'):
        return algorithm.resolve_multi_dimensional(parameters)
    return algorithm.is_multi_dimensional


# === SHARED VOLUME EXPORT ====================================================


REGISTRY_PATH = Path(os.environ.get("ALGORITHM_REGISTRY_PATH", "/app/registry/algorithms.json"))


def _export_registry_if_available():
    """Export registry to shared volume if path exists."""
    try:
        # Only export if the registry directory exists (i.e., in Docker with volume)
        if REGISTRY_PATH.parent.exists():
            export_registry()
    except Exception as e:
        # Don't fail registration if export fails
        logger.debug(f"Could not export registry: {e}")


def export_registry():
    """Export algorithm registry to JSON file for KB-MCP to read.
    
    This is called automatically after each algorithm registers.
    KB-MCP reads this file to know which algorithms are available.
    """
    data = get_algorithm_info()
    
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(data, indent=2))
    
    logger.info(f"Exported {len(data)} algorithms to {REGISTRY_PATH}")


def import_registry() -> Dict[str, Any]:
    """Import algorithm registry from JSON file.
    
    Used by KB-MCP to read available algorithms.
    Returns empty dict if file doesn't exist yet.
    """
    if not REGISTRY_PATH.exists():
        logger.warning(f"Registry file not found: {REGISTRY_PATH}")
        return {}
    
    try:
        return json.loads(REGISTRY_PATH.read_text())
    except Exception as e:
        logger.error(f"Failed to read registry: {e}")
        return {}
