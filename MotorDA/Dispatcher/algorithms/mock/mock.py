"""Mock Algorithm - Comprehensive Testing Algorithm for Anomaly Detection Framework.

================================================================================
PURPOSE
================================================================================
This is a fully-featured algorithm implementation designed for:
1. TESTING: Validates the entire anomaly detection stack
2. DEMONSTRATION: Shows how to implement new algorithms
3. MODE TESTING: Supports BOTH single-dim AND multi-dim modes (switchable!)

================================================================================
ALGORITHM MODES EXPLAINED
================================================================================

SINGLE-DIMENSIONAL MODE (is_multi_dimensional=False):
    - Each dimension is trained INDEPENDENTLY
    - Train method receives: List[float] (values for ONE dimension)
    - Detect method receives: float (single value), model (for that dimension)
    - Example: Z-Score, IQR
    - Flow:
        for each dimension:
            model[dim] = algo.train(values_for_dim, parameter)
        for each observation:
            for each dimension:
                result = algo.detect(obs[dim], model[dim], parameter)

MULTI-DIMENSIONAL MODE (is_multi_dimensional=True):
    - All dimensions are trained TOGETHER as vectors
    - Train method receives: List[Dict] (complete observations)
    - Detect method receives: Dict (complete observation), model (single model)
    - Example: K-Means (clusters in N-dimensional space), PCA
    - Flow:
        model = algo.train_multi_dimensional(all_observations, parameters)
        for each observation:
            result = algo.detect_multi_dimensional(obs, model, parameters)

================================================================================
USER-OVERRIDABLE PARAMETERS (Phase 3 Pattern)
================================================================================

Users can override algorithm defaults via KB config parameter metadata:

    "algorithm": {
        "name": "mock",
        "parameters": [
            {
                "dimension": "request_count",
                "is_active": true,
                "metadata": [
                    {"key": "percentile", "value": "99.0"},       // Override threshold
                    {"key": "force_multi_dim", "value": "true"}   // Force multi-dim mode
                ]
            }
        ]
    }

Resolution order (highest priority first):
1. parameter.metadata[key="X"] → User override
2. Algorithm default (e.g., self.min_training_samples = 3)

================================================================================
STATISTICS USED
================================================================================

This mock uses simple threshold-based detection for predictability:

TRAINING:
    - Computes: mean = sum(values) / len(values)
    - Threshold derived from percentile parameter (default 95.0)
    - threshold = percentile / 10.0 (so 95.0 → 9.5 deviation allowed)

DETECTION (Single-Dim):
    - deviation = |value - mean|
    - is_anomaly = deviation > threshold

DETECTION (Multi-Dim):
    - Euclidean distance from centroid (mean of all dimensions)
    - is_anomaly = distance > (threshold * sqrt(n_dimensions))

================================================================================
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional
import logging
import math

from ...algorithm_interface import register_algorithm

logger = logging.getLogger(__name__)


@register_algorithm
@dataclass
class MockAlgorithm:
    """Mock algorithm supporting BOTH single and multi-dimensional modes.
    
    This algorithm demonstrates the FULL interface:
    - Can switch between modes via resolve_multi_dimensional()
    - User can force mode via "force_multi_dim" metadata
    - Implements all 4 core methods (train, detect, train_multi_dimensional, detect_multi_dimensional)
    
    Use Cases:
    - Testing the dispatcher's routing logic
    - Validating KB configurations
    - Performance testing without heavy computation
    - Demonstrating algorithm implementation patterns
    """
    
    # ═══════════════════════════════════════════════════════════════════════════
    # ALGORITHM METADATA (exposed to KB-MCP via registry)
    # ═══════════════════════════════════════════════════════════════════════════
    
    __algorithm_meta__ = {
        "description": "Mock algorithm for testing - supports both single and multi-dimensional modes",
        "parameters": ["percentile", "force_multi_dim"],  # Parameters users can override
    }
    
    # ═══════════════════════════════════════════════════════════════════════════
    # ALGORITHM INTERFACE PROPERTIES (Required by Protocol)
    # ═══════════════════════════════════════════════════════════════════════════
    
    @property
    def name(self) -> str:
        """Algorithm identifier used in KB configs.
        
        Example KB config:
            "algorithm": {"name": "mock", ...}
        """
        return "mock"
    
    @property
    def is_multi_dimensional(self) -> bool:
        """DEFAULT mode when resolve_multi_dimensional() is not called.
        
        Since this algorithm supports both modes, this is just the fallback.
        The actual mode is determined by resolve_multi_dimensional().
        
        Returns:
            False - default to single-dimensional for backwards compatibility
        """
        return False
    
    @property
    def supports_bucketing(self) -> bool:
        """Whether to train separate models per time-context bucket.
        
        True = separate models for "workday_09", "weekend_14", etc.
        False = single global model (e.g., for KMeans clustering)
        
        Mock supports bucketing because it's simple enough to benefit from it.
        """
        return True
    
    @property
    def min_training_samples(self) -> int:
        """Minimum observations needed for meaningful training.
        
        Mock uses 1 for maximum flexibility in testing.
        Real algorithms typically need more (ZScore=3, KMeans=10+).
        
        User can override via metadata: {"key": "min_training_samples", "value": "10"}
        """
        return 1
    
    # ═══════════════════════════════════════════════════════════════════════════
    # MODE RESOLUTION (Phase 2 - Dynamic Mode Selection)
    # ═══════════════════════════════════════════════════════════════════════════
    
    def resolve_multi_dimensional(self, parameters: List[Dict[str, Any]]) -> bool:
        """Dynamically decide whether to use multi-dimensional mode.
        
        This method is called by the orchestrator BEFORE training to decide
        which path to take (single-dim vs multi-dim).
        
        Decision Logic:
        1. If ANY parameter has metadata force_multi_dim=true → multi-dim
        2. If num_dimensions >= 3 → multi-dim (correlations become interesting)
        3. Otherwise → single-dim
        
        Args:
            parameters: List of algorithm parameters from KB config
                Each has: dimension, is_active, optional metadata[]
        
        Returns:
            True for multi-dimensional mode, False for single-dimensional
        
        Example KB config to force multi-dim:
            "metadata": [{"key": "multi_dimensional", "value": "true"}]
        
        Note: Supports both field names:
            - "metadata" (generic)
            - "algorithm_metadata" (KB-MCP specific format)
        """
        active_dims = 0
        force_multi = False
        
        for param in parameters:
            # Skip inactive dimensions
            if not param.get("is_active", True):
                continue
            
            active_dims += 1
            
            # Check for user override in metadata
            # Support both field names: "metadata" (generic) and "algorithm_metadata" (KB-MCP format)
            metadata = param.get("metadata", []) or param.get("algorithm_metadata", [])
            for meta in metadata:
                key = meta.get("key", "").lower()
                # Accept both key names: "multi_dimensional" (standard) and "force_multi_dim" (legacy)
                if key in ("multi_dimensional", "force_multi_dim"):
                    val = str(meta.get("value", "")).lower()
                    if val in ("true", "1", "yes"):
                        force_multi = True
                        logger.info("[MOCK] User forced multi-dimensional mode via metadata")
        
        # Decision logic
        if force_multi:
            return True
        
        # Auto-switch to multi-dim if 3+ dimensions (correlations matter)
        if active_dims >= 3:
            logger.info(f"[MOCK] Auto-selected multi-dimensional mode ({active_dims} dimensions)")
            return True
        
        logger.info(f"[MOCK] Using single-dimensional mode ({active_dims} dimensions)")
        return False
    
    # ═══════════════════════════════════════════════════════════════════════════
    # HELPER: Extract percentile from parameter metadata
    # ═══════════════════════════════════════════════════════════════════════════
    
    def _get_percentile(self, parameter: Optional[Dict[str, Any]] = None, default: float = 95.0) -> float:
        """Extract percentile from parameter metadata, or use default.
        
        This demonstrates the USER-OVERRIDABLE PATTERN:
        1. Check parameter.metadata for "percentile"
        2. If found, use it (user override)
        3. If not, use the default (algorithm default)
        
        Args:
            parameter: Algorithm parameter dict (may have metadata)
            default: Default percentile if not specified
        
        Returns:
            Percentile value (float between 0-100)
        """
        if not parameter:
            return default
        
        # Support both field names: "metadata" (generic) and "algorithm_metadata" (KB-MCP format)
        metadata = parameter.get("metadata", []) or parameter.get("algorithm_metadata", [])
        for meta in metadata:
            if meta.get("key") == "percentile":
                try:
                    return float(meta.get("value", default))
                except (ValueError, TypeError):
                    logger.warning(f"[MOCK] Invalid percentile value, using default {default}")
        
        return default
    
    # ═══════════════════════════════════════════════════════════════════════════
    # SINGLE-DIMENSIONAL METHODS
    # ═══════════════════════════════════════════════════════════════════════════
    
    def train(
        self,
        values: List[float],
        parameter: Optional[Dict[str, Any]] = None,
        **_  # Accept extra kwargs for compatibility
    ) -> Dict[str, Any]:
        """Train a single-dimensional model from a list of values.
        
        This is called ONCE per dimension, per bucket:
            model["request_count"]["workday_09"] = train(values, param)
        
        Statistical method:
            mean = average of all values
            threshold = percentile / 10 (simple scaling for testing)
        
        Args:
            values: List of numeric values for ONE dimension
            parameter: Dict with dimension name and optional metadata
                Example: {"dimension": "request_count", "metadata": [...]}
            **_: Additional kwargs (ignored, for API compatibility)
        
        Returns:
            Model dict containing:
            - mean: float - Center of the data
            - threshold: float - Deviation limit for anomaly
            - data_points: int - Number of training samples used
        """
        # Extract user-overridable percentile
        percentile = self._get_percentile(parameter)
        
        # Handle edge case: no training data
        if not values:
            logger.warning("[MOCK] No training data provided, using defaults")
            return {
                "mean": 0.0,
                "threshold": percentile / 10.0,
                "data_points": 0,
            }
        
        # Compute statistics
        mean = sum(values) / len(values)
        threshold = percentile / 10.0  # Simple scaling for predictable behavior
        
        logger.debug(f"[MOCK] Trained: mean={mean:.2f}, threshold={threshold:.2f}, n={len(values)}")
        
        return {
            "mean": mean,
            "threshold": threshold,
            "data_points": len(values),
        }
    
    def detect(
        self,
        value: float,
        model: Dict[str, Any],
        parameter: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Detect if a single value is anomalous.
        
        Detection logic:
            deviation = |value - mean|
            is_anomaly = deviation > threshold
        
        Args:
            value: The numeric value to check
            model: Trained model dict from train()
            parameter: Algorithm parameter (unused here, threshold from model)
        
        Returns:
            Detection result dict:
            - is_anomaly: bool - Whether this value is anomalous
            - value: float - The checked value
            - deviation: float - How far from mean
            - threshold: float - Maximum allowed deviation
            - mean: float - Expected value from training
        """
        mean = model.get("mean", 0.0)
        threshold = model.get("threshold", 10.0)
        
        deviation = abs(value - mean)
        is_anomaly = deviation > threshold
        
        return {
            "is_anomaly": is_anomaly,
            "value": value,
            "deviation": deviation,
            "threshold": threshold,
            "mean": mean,
        }
    
    def detect_batch(
        self,
        values: List[float],
        model: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Detect anomalies for a batch of single-dimensional values.
        
        Simply maps detect() over the list of values.
        Used for batch processing efficiency.
        
        Args:
            values: List of values to check
            model: Trained model dict
        
        Returns:
            List of detection results (one per value)
        """
        return [self.detect(v, model) for v in values]
    
    # ═══════════════════════════════════════════════════════════════════════════
    # MULTI-DIMENSIONAL METHODS
    # ═══════════════════════════════════════════════════════════════════════════
    
    def train_multi_dimensional(
        self,
        observations: List[Dict[str, Any]],
        parameters: List[Dict[str, Any]],
        **_  # Accept extra kwargs for compatibility
    ) -> Dict[str, Any]:
        """Train a multi-dimensional model from complete observations.
        
        Unlike single-dim training, this receives ALL dimensions at once,
        allowing the algorithm to capture cross-dimensional relationships.
        
        For Mock, we compute:
        1. Centroid: mean of each dimension (center of the data cloud)
        2. Per-dimension means for normalization
        3. Threshold based on percentile and number of dimensions
        
        Args:
            observations: List of observation dicts, each containing all dimensions
                Example: [{"ts": ..., "cpu": 50, "memory": 70}, ...]
            parameters: List of parameter dicts defining which dimensions to use
                Example: [{"dimension": "cpu", "is_active": true}, ...]
            **_: Additional kwargs (ignored)
        
        Returns:
            Model dict containing:
            - centroid: Dict[str, float] - Mean per dimension
            - threshold: float - Distance threshold for anomaly
            - n_dimensions: int - Number of active dimensions
            - n_observations: int - Training sample count
        """
        # Determine which dimensions to use (active ones only)
        active_dims = []
        percentile = 95.0  # Will be overridden if any param has it
        
        for param in parameters:
            if param.get("is_active", True):
                dim = param.get("dimension")
                if dim:
                    active_dims.append(dim)
                    # Get percentile from any parameter that has it
                    p = self._get_percentile(param)
                    if p != 95.0:
                        percentile = p
        
        if not active_dims:
            logger.warning("[MOCK] No active dimensions for multi-dim training")
            return {"centroid": {}, "threshold": 10.0, "n_dimensions": 0}
        
        # Compute centroid (mean per dimension)
        centroid = {dim: 0.0 for dim in active_dims}
        counts = {dim: 0 for dim in active_dims}
        
        for obs in observations:
            for dim in active_dims:
                val = obs.get(dim)
                if val is not None:
                    try:
                        centroid[dim] += float(val)
                        counts[dim] += 1
                    except (ValueError, TypeError):
                        pass
        
        # Finalize centroid (compute means)
        for dim in active_dims:
            if counts[dim] > 0:
                centroid[dim] /= counts[dim]
        
        # Compute threshold (scaled by number of dimensions)
        # More dimensions = larger expected distance, so scale threshold up
        base_threshold = percentile / 10.0
        threshold = base_threshold * math.sqrt(len(active_dims))
        
        logger.info(
            f"[MOCK] Multi-dim training complete: {len(active_dims)} dims, "
            f"{len(observations)} observations, threshold={threshold:.2f}"
        )
        
        return {
            "centroid": centroid,
            "threshold": threshold,
            "n_dimensions": len(active_dims),
            "n_observations": len(observations),
            "percentile": percentile,
        }
    
    def detect_multi_dimensional(
        self,
        observation: Dict[str, Any],
        models: Dict[str, Any],
        parameters: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Detect if a multi-dimensional observation is anomalous.
        
        Uses Euclidean distance from centroid:
            distance = sqrt(sum((obs[dim] - centroid[dim])^2 for dim in dimensions))
            is_anomaly = distance > threshold
        
        This captures CROSS-DIMENSIONAL anomalies that single-dim would miss.
        Example: CPU=50% and Memory=50% are normal individually, but
                 CPU=90% while Memory=10% might indicate a problem.
        
        Args:
            observation: Single observation dict with all dimension values
            models: Model dict from train_multi_dimensional()
                Note: In multi-dim mode, this is the full model (not per-dimension)
            parameters: List of parameter dicts (for dimension names)
        
        Returns:
            Detection result:
            - is_anomaly: bool
            - distance: float - Euclidean distance from centroid
            - threshold: float
            - dimension_contributions: Dict - How much each dim contributed
        """
        # Handle case where models might be per-dimension or unified model
        if "centroid" in models:
            # Unified multi-dim model
            centroid = models.get("centroid", {})
            threshold = models.get("threshold", 10.0)
        else:
            # Models are per-dimension, compute centroid from them
            centroid = {}
            threshold = 10.0
            for param in parameters:
                dim = param.get("dimension")
                if dim and dim in models:
                    centroid[dim] = models[dim].get("mean", 0.0)
                    threshold = max(threshold, models[dim].get("threshold", 10.0))
            threshold *= math.sqrt(len(centroid)) if centroid else 1.0
        
        # Compute Euclidean distance from centroid
        distance_sq = 0.0
        dimension_contributions = {}
        
        for dim, center in centroid.items():
            val = observation.get(dim)
            if val is not None:
                try:
                    diff = float(val) - center
                    contribution = diff ** 2
                    distance_sq += contribution
                    dimension_contributions[dim] = {
                        "value": float(val),
                        "center": center,
                        "diff": diff,
                        "contribution": contribution,
                    }
                except (ValueError, TypeError):
                    pass
        
        distance = math.sqrt(distance_sq)
        is_anomaly = distance > threshold
        
        # Also check individual dimensions and report which ones are anomalous
        anomalous_dims = []
        for dim, contrib in dimension_contributions.items():
            # Individual dimension is anomalous if it contributes > 50% of threshold
            if abs(contrib["diff"]) > threshold / math.sqrt(len(centroid) or 1):
                anomalous_dims.append(dim)
        
        return {
            "is_anomaly": is_anomaly,
            "distance": distance,
            "threshold": threshold,
            "dimension_contributions": dimension_contributions,
            "anomalous_dimensions": anomalous_dims,
            "dimensions": list(centroid.keys()),
        }
