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
    baseline = algo.train([10, 20, 30])
    result = algo.detect(100, baseline)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol, Dict, Any, List, Type, runtime_checkable
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
    """Decorator to auto-register an algorithm.
    
    Just add @register_algorithm above your class.
    The decorator:
    1. Creates an instance
    2. Validates it implements the protocol
    3. Registers it by name
    4. Exports registry to shared volume (if available)
    
    Usage:
        @register_algorithm
        @dataclass
        class MyAlgorithm:
            __algorithm_meta__ = {
                "description": "My algorithm",
                "parameters": ["param1"],
            }
            
            @property
            def name(self) -> str:
                return "my_algo"
            
            def train(self, values, **kwargs): ...
            def detect(self, value, baseline): ...
            def detect_batch(self, values, baseline): ...
    """
    instance = cls()
    
    # Verify protocol compliance
    required = ['name', 'train', 'detect', 'detect_batch']
    missing = [m for m in required if not hasattr(instance, m)]
    if missing:
        raise TypeError(
            f"Class {cls.__name__} must implement AnomalyAlgorithm protocol. "
            f"Missing: {missing}"
        )
    
    name = instance.name.lower()
    
    if name in ALGORITHM_REGISTRY:
        logger.warning(f"Overwriting existing algorithm: {name}")
    
    ALGORITHM_REGISTRY[name] = instance
    logger.info(f"Registered algorithm: {name}")
    
    # Export registry after each registration
    _export_registry_if_available()
    
    return cls


@runtime_checkable
class AnomalyAlgorithm(Protocol):
    """Interface for anomaly detection algorithms.
    
    All algorithms MUST implement this protocol.
    This is a PURE statistical interface - no bucket logic.
    """
    
    @property
    def name(self) -> str:
        """Algorithm identifier (e.g., 'zscore', 'iqr')."""
        ...
    
    def train(self, values: List[float], **kwargs) -> Dict[str, Any]:
        """Train model from values, return serializable baseline."""
        ...
    
    def detect(self, value: float, baseline: Dict[str, Any]) -> Dict[str, Any]:
        """Detect if a single value is anomalous. Must return 'is_anomaly' key."""
        ...
    
    def detect_batch(self, values: List[float], baseline: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect anomalies for multiple values."""
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
    """Get metadata for algorithms (from __algorithm_meta__)."""
    if name:
        name_lower = name.lower()
        if name_lower not in ALGORITHM_REGISTRY:
            return None
        algo = ALGORITHM_REGISTRY[name_lower]
        meta = getattr(algo, '__algorithm_meta__', {})
        return {"name": name_lower, **meta}
    
    result = {}
    for algo_name, algo in ALGORITHM_REGISTRY.items():
        meta = getattr(algo, '__algorithm_meta__', {})
        result[algo_name] = {"name": algo_name, **meta}
    return result


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
