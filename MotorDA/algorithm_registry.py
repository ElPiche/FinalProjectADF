"""Algorithm Registry for Anomaly Detection Framework.

This module provides a central registry for all available anomaly detection
algorithms. It supports automatic discovery and lookup by name.

Usage:
    from MotorDA.algorithm_registry import get_algorithm, list_algorithms
    
    # Get algorithm by name
    zscore = get_algorithm("zscore")
    
    # List all registered algorithms
    for name, algo in list_algorithms():
        print(f"{name}: {algo.display_name}")

To register a new algorithm:
    1. Create your algorithm class extending BaseAlgorithm
    2. Import and add to ALGORITHMS dict below
    3. Rebuild dispatcher container
"""

from typing import Dict, List, Optional, Tuple

# Support both import styles (from MotorDA or from within MotorDA)
try:
    from MotorDA.base_algorithm import BaseAlgorithm, DetectionMode, BucketMode
except ImportError:
    from base_algorithm import BaseAlgorithm, DetectionMode, BucketMode


# =============================================================================
# Algorithm Registry
# =============================================================================

# Import algorithm implementations
# Add new imports here as algorithms are implemented
try:
    from MotorDA.ZScore.algorithm import ZScoreAlgorithm
    from MotorDA.ARMAX.algorithm import ARMAXAlgorithm
except ImportError:
    from ZScore.algorithm import ZScoreAlgorithm
    from ARMAX.algorithm import ARMAXAlgorithm

# Registry: algorithm_name -> algorithm_instance
# To add a new POINT algorithm:
#   1. Create YourAlgorithm(BaseAlgorithm) in a new file
#   2. Import it above
#   3. Add it to ALGORITHMS below
ALGORITHMS: Dict[str, BaseAlgorithm] = {
    # Phase 1: POINT algorithms (currently supported)
    "zscore": ZScoreAlgorithm(),
    # "iqr": IQRAlgorithm(),          # TODO: implement
    # "threshold": ThresholdAlgorithm(),  # TODO: implement
    # "kmeans": KMeansAlgorithm(),    # TODO: implement
    
    # Phase 2: SERIES algorithms (requires HistoryProvider)
    "armax": ARMAXAlgorithm(),
    # "arma": ARMAAlgorithm(),
    
    # Phase 3: Neural networks (requires model serving)
    # "lstm": LSTMAlgorithm(),
    # "autoencoder": AutoencoderAlgorithm(),
}


# =============================================================================
# Registry Functions
# =============================================================================

def get_algorithm(name: str) -> Optional[BaseAlgorithm]:
    """Get algorithm instance by name.
    
    Args:
        name: Algorithm name (case-insensitive)
        
    Returns:
        Algorithm instance or None if not found
    """
    return ALGORITHMS.get(name.lower())


def list_algorithms() -> List[Tuple[str, BaseAlgorithm]]:
    """List all registered algorithms.
    
    Returns:
        List of (name, algorithm) tuples
    """
    return list(ALGORITHMS.items())


def list_algorithm_names() -> List[str]:
    """List names of all registered algorithms.
    
    Returns:
        List of algorithm names
    """
    return list(ALGORITHMS.keys())


def get_algorithms_by_mode(mode: DetectionMode) -> List[Tuple[str, BaseAlgorithm]]:
    """Get all algorithms with a specific detection mode.
    
    Args:
        mode: DetectionMode.POINT, SERIES, or BATCH
        
    Returns:
        List of (name, algorithm) tuples matching the mode
    """
    # Compare by .value to avoid import path enum issues
    return [
        (name, algo) 
        for name, algo in ALGORITHMS.items() 
        if algo.detection_mode.value == mode.value
    ]


def get_algorithms_by_bucket_mode(mode: BucketMode) -> List[Tuple[str, BaseAlgorithm]]:
    """Get all algorithms with a specific bucket mode.
    
    Args:
        mode: BucketMode.SEGMENT, FEATURE, or METADATA_ONLY
        
    Returns:
        List of (name, algorithm) tuples matching the bucket mode
    """
    # Compare by .value to avoid import path enum issues
    return [
        (name, algo)
        for name, algo in ALGORITHMS.items()
        if algo.bucket_mode.value == mode.value
    ]


def is_algorithm_supported(name: str) -> bool:
    """Check if an algorithm is registered and available.
    
    Args:
        name: Algorithm name (case-insensitive)
        
    Returns:
        True if algorithm is registered
    """
    return name.lower() in ALGORITHMS


def get_algorithm_info(name: str) -> Optional[Dict]:
    """Get information about an algorithm.
    
    Args:
        name: Algorithm name (case-insensitive)
        
    Returns:
        Dict with algorithm metadata or None if not found
    """
    algo = get_algorithm(name)
    if algo is None:
        return None
    
    return {
        "name": algo.name,
        "display_name": algo.display_name,
        "detection_mode": algo.detection_mode.value,
        "bucket_mode": algo.bucket_mode.value,
        "required_history_length": algo.required_history_length,
        "minimum_training_points": algo.minimum_training_points,
    }


def get_supported_algorithms_doc() -> str:
    """Generate documentation string for all supported algorithms.
    
    Returns:
        Formatted string describing all algorithms
    """
    if not ALGORITHMS:
        return "No algorithms currently registered."
    
    lines = ["Supported Algorithms:", ""]
    
    # Group by detection mode
    for mode in DetectionMode:
        algos = get_algorithms_by_mode(mode)
        if algos:
            lines.append(f"## {mode.value.upper()} Mode Algorithms")
            lines.append("")
            for name, algo in algos:
                lines.append(f"- **{algo.display_name}** (`{name}`)")
                lines.append(f"  - Bucket mode: {algo.bucket_mode.value}")
                if algo.required_history_length > 0:
                    lines.append(f"  - History required: {algo.required_history_length} values")
            lines.append("")
    
    return "\n".join(lines)


# =============================================================================
# Validation
# =============================================================================

def validate_algorithm_config(name: str, parameters: Dict) -> List[str]:
    """Validate algorithm configuration parameters.
    
    Args:
        name: Algorithm name
        parameters: Algorithm parameters from KB config
        
    Returns:
        List of error messages (empty if valid)
    """
    algo = get_algorithm(name)
    if algo is None:
        return [f"Unknown algorithm: '{name}'. Supported: {list_algorithm_names()}"]
    
    return algo.validate_config(parameters)
