# How to Add a New Algorithm to the Anomaly Detection Framework

> **Version:** 2.0 - December 2025  
> **Status:** Production Ready

This guide explains how to implement **any** anomaly detection algorithm for the ADF framework. The modular architecture supports both **single-dimensional** and **multi-dimensional** algorithms through a decorator-based registration system.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Algorithm Types](#2-algorithm-types)
3. [Step-by-Step Implementation](#3-step-by-step-implementation)
4. [Required Methods & Properties](#4-required-methods--properties)
5. [User-Overridable Parameters](#5-user-overridable-parameters)
6. [Algorithm Details Structure](#6-algorithm-details-structure)
7. [Advanced: Dual-Mode Algorithms](#7-advanced-dual-mode-algorithms)
8. [Registration & Discovery](#8-registration--discovery)
9. [Testing Your Algorithm](#9-testing-your-algorithm)
10. [Complete Examples](#10-complete-examples)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Orchestrator Layer                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  training_orchestrator.py / detection_orchestrator.py        │   │
│  │                                                              │   │
│  │  is_multi_dimensional = True?                                │   │
│  │  ├─ YES → algorithm.train_multi_dimensional(observations)   │   │
│  │  └─ NO  → for each dim: algorithm.train(values, parameter)  │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Algorithm Layer                              │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────┐  ┌────────────────┐   │
│  │    ZScore      │  │      IQR       │  │       Mock         │  │     KMeans      │   │
│  │  (single-dim)  │  │  (single-dim)  │  │   (dual-mode)      │  │ (multi-dim)     │   │
│  │                │  │                │  │                    │  │                │   │
│  │  train()       │  │  train()       │  │  train()           │  │ train_multi_dim │   │
│  │  detect()      │  │  detect()      │  │  detect()          │  │ detect_multi_dim│   │
│  │  detect_batch()│  │  detect_batch()│  │  train_multi_dim() │  │                │   │
│  └────────────────┘  └────────────────┘  │  detect_multi_dim()│  └────────────────┘   │
│                                          └────────────────────┘                      │
└─────────────────────────────────────────────────────────────────────┘
```

**Key Concept:** The orchestrator decides HOW to call your algorithm based on `is_multi_dimensional`:
- **Single-dimensional** (`is_multi_dimensional=False`): Orchestrator loops through dimensions and calls `train()` / `detect()` for each
- **Multi-dimensional** (`is_multi_dimensional=True`): Orchestrator passes ALL dimensions at once to `train_multi_dimensional()` / `detect_multi_dimensional()`

---

## 2. Algorithm Types

### 2.1 Single-Dimensional Algorithm
Processes each metric dimension independently. The orchestrator handles the looping.

**Examples:** Z-Score, IQR, Exponential Smoothing, ARIMA (per-series)

**You implement:**
- `train(values, parameter)` → Returns baseline dict
- `detect(value, baseline, parameter)` → Returns detection result dict
- `detect_batch(values, baseline)` → (Optional) Batch detection

### 2.2 Multi-Dimensional Algorithm
Considers correlations between dimensions. You receive ALL dimensions at once.

**Examples:** Mahalanobis Distance, KMeans, Isolation Forest, DBSCAN, Autoencoders

**You implement:**
- `train_multi_dimensional(observations, parameters)` → Returns baselines dict
- `detect_multi_dimensional(observation, baselines, parameters)` → Returns detection result dict

### 2.3 Dual-Mode Algorithm (Advanced)
Supports BOTH modes, with dynamic selection based on KB config metadata.

**Example:** Mock algorithm (for testing)

**You implement:** All methods from both types, plus `resolve_multi_dimensional(parameters)`.

---

## 3. Step-by-Step Implementation

### Step 1: Create Algorithm Directory
```
MotorDA/Dispatcher/algorithms/
└── your_algorithm/
    ├── __init__.py
    └── your_algorithm.py
```

### Step 2: Create `__init__.py`
```python
"""Your Algorithm package."""
from .your_algorithm import YourAlgorithm

__all__ = ["YourAlgorithm"]
```

### Step 3: Implement Algorithm Class
See Section 4 for required methods.

### Step 4: Register in Package Init
Edit `MotorDA/Dispatcher/algorithms/__init__.py`:
```python
from .your_algorithm import YourAlgorithm
# The @register_algorithm decorator handles registration automatically
```

### Step 5: Rebuild Dispatcher
```bash
docker compose build dispatcher
docker compose up -d dispatcher
```

---

## 4. Required Methods & Properties

### 4.1 Single-Dimensional Algorithm Template

```python
"""Your Algorithm - Brief description."""

from dataclasses import dataclass
from typing import Dict, Any, List
import logging

from ...algorithm_interface import register_algorithm

logger = logging.getLogger(__name__)


@register_algorithm
@dataclass
class YourAlgorithm:
    """Your algorithm description.
    
    Algorithm Properties:
        is_multi_dimensional: False - processes one dimension at a time
        supports_bucketing: True/False - separate model per time-context bucket
        min_training_samples: N - minimum data points needed
    """
    
    # ─────────────────────────────────────────────────────────────────────────
    # Algorithm Metadata (shown in KB-MCP list_available_algorithms)
    # ─────────────────────────────────────────────────────────────────────────
    __algorithm_meta__ = {
        "description": "One-line description shown to users",
        "best_for": "When to use this algorithm",
        "parameters": ["param1", "param2"],  # User-overridable via metadata
    }
    
    # ─────────────────────────────────────────────────────────────────────────
    # Required Properties
    # ─────────────────────────────────────────────────────────────────────────
    
    @property
    def name(self) -> str:
        """Unique algorithm identifier (lowercase, no spaces)."""
        return "your_algorithm"
    
    @property
    def is_multi_dimensional(self) -> bool:
        """Return False for single-dimensional algorithm."""
        return False
    
    @property
    def supports_bucketing(self) -> bool:
        """Whether algorithm supports time-context bucketing."""
        return True
    
    @property
    def min_training_samples(self) -> int:
        """Minimum samples needed for valid training."""
        return 10
    
    # ─────────────────────────────────────────────────────────────────────────
    # Required Methods
    # ─────────────────────────────────────────────────────────────────────────
    
    def train(self, values: List[float], parameter: Dict[str, Any] = None, **_) -> Dict[str, Any]:
        """Train baseline from values for ONE dimension.
        
        Args:
            values: List of numeric values (floats)
            parameter: Algorithm parameter dict with optional metadata overrides
                       Structure: {"dimension": "metric_name", "metadata": [...], "is_active": True}
        
        Returns:
            Baseline dict - structure is algorithm-specific
            Example: {"mean": 100.0, "std": 15.0, "threshold": 45.0}
        """
        # 1. Resolve user-overridable parameters from metadata
        param1_value = self._get_default_param1()
        if parameter:
            for meta in parameter.get("metadata", []):
                if meta.get("key") == "param1" and meta.get("value") is not None:
                    param1_value = meta.get("value")
        
        # 2. Compute baseline statistics
        baseline = self._compute_baseline(values, param1_value)
        
        logger.info(f"[{self.name.upper()}] Trained: {baseline}")
        return baseline
    
    def detect(self, value: float, baseline: Dict[str, Any], parameter: Dict[str, Any] = None) -> Dict[str, Any]:
        """Detect if a single value is anomalous.
        
        Args:
            value: The value to check
            baseline: Trained baseline dict from train()
            parameter: Algorithm parameter dict (usually unused, thresholds come from baseline)
        
        Returns:
            Detection result dict with AT LEAST:
            - "is_anomaly": bool
            - Any additional details for algorithm_details field
        """
        is_anomaly = self._check_anomaly(value, baseline)
        
        return {
            "is_anomaly": is_anomaly,
            "value": value,
            # Add algorithm-specific details here
            "your_metric": some_value,
        }
    
    def detect_batch(self, values: List[float], baseline: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect anomalies for multiple values (optional but recommended).
        
        Args:
            values: List of values to check
            baseline: Trained baseline dict
        
        Returns:
            List of detection result dicts
        """
        return [self.detect(v, baseline) for v in values]
```

### 4.2 Multi-Dimensional Algorithm Template

```python
@register_algorithm
@dataclass
class YourMultiDimAlgorithm:
    """Multi-dimensional anomaly detection."""
    
    __algorithm_meta__ = {
        "description": "Detects anomalies considering correlations between dimensions",
        "best_for": "Data where dimension relationships matter",
        "parameters": ["threshold"],
    }
    
    @property
    def name(self) -> str:
        return "your_multi_algo"
    
    @property
    def is_multi_dimensional(self) -> bool:
        """Return True - orchestrator will call train_multi_dimensional."""
        return True
    
    @property
    def supports_bucketing(self) -> bool:
        return True
    
    @property
    def min_training_samples(self) -> int:
        return 30  # Multi-dim often needs more data
    
    def train_multi_dimensional(
        self,
        observations: List[Dict[str, Any]],
        parameters: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Train on ALL dimensions simultaneously.
        
        Args:
            observations: List of observation dicts, each containing all dimension values
                          Example: [{"dim1": 100, "dim2": 50}, {"dim1": 105, "dim2": 48}, ...]
            parameters: List of parameter dicts, one per dimension
                        Each has: {"dimension": "dim_name", "metadata": [...], "is_active": True}
        
        Returns:
            Baselines dict - structure is algorithm-specific
            Example: {"center": [...], "covariance": [...], "threshold": 9.21}
        """
        # Extract dimension names
        dim_names = [p["dimension"] for p in parameters if p.get("is_active", True)]
        
        # Build data matrix from observations
        data_matrix = []
        for obs in observations:
            row = [float(obs.get(dim, 0)) for dim in dim_names]
            data_matrix.append(row)
        
        # Compute multi-dimensional baseline
        baselines = self._compute_multi_dim_baseline(data_matrix, dim_names)
        
        logger.info(f"[{self.name.upper()}] Multi-dim trained: {len(observations)} obs, {len(dim_names)} dims")
        return baselines
    
    def detect_multi_dimensional(
        self,
        observation: Dict[str, Any],
        baselines: Dict[str, Any],
        parameters: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Detect anomaly considering ALL dimensions together.
        
        Args:
            observation: Single observation dict with all dimension values
                         Example: {"dim1": 150, "dim2": 30}
            baselines: Trained baselines from train_multi_dimensional
            parameters: List of parameter dicts
        
        Returns:
            Detection result with AT LEAST:
            - "is_anomaly": bool
            - "dimension_contributions": Dict[str, Dict] - per-dimension details
        """
        dim_names = [p["dimension"] for p in parameters if p.get("is_active", True)]
        
        # Compute multi-dimensional anomaly score
        is_anomaly, score, contributions = self._compute_anomaly(observation, baselines, dim_names)
        
        return {
            "is_anomaly": is_anomaly,
            "anomaly_score": score,
            "dimension_contributions": contributions,  # IMPORTANT: Include this!
        }
```

---

## 5. User-Overridable Parameters

Users can override algorithm defaults via KB config metadata. This is the **User-Overridable Pattern**.

### KB Config Example
```json
{
  "algorithm": {
    "name": "zscore",
    "parameters": [
      {
        "dimension": "error_count",
        "is_active": true,
        "metadata": [
          {"key": "percentile", "value": "99.0"},
          {"key": "min_points", "value": "10"}
        ]
      }
    ]
  }
}
```

### Reading Metadata in Your Algorithm
```python
def train(self, values: List[float], parameter: Dict[str, Any] = None, **_) -> Dict[str, Any]:
    # Start with algorithm defaults
    percentile = 99.5  # Default
    min_points = 3     # Default
    
    # Override from metadata if provided
    if parameter:
        for meta in parameter.get("metadata", []):
            key = meta.get("key")
            val = meta.get("value")
            if key == "percentile" and val is not None:
                try:
                    percentile = float(val)
                except (ValueError, TypeError):
                    pass  # Keep default on parse error
            elif key == "min_points" and val is not None:
                try:
                    min_points = int(val)
                except (ValueError, TypeError):
                    pass
    
    # Now use percentile and min_points...
```

**Best Practice:** Document your overridable parameters in `__algorithm_meta__["parameters"]`.

---

## 6. Algorithm Details Structure

The `algorithm_details` field in anomaly results is **100% algorithm-implementation dependent**. The dispatcher stores whatever your algorithm returns.

### Single-Dimensional Example (Z-Score)
```json
{
  "algorithm_details": {
    "error_count": {
      "is_anomaly": true,
      "value": 150.0,
      "mean": 50.0,
      "std": 10.0,
      "z_score": 10.0,
      "threshold": 3.29
    }
  }
}
```

### Multi-Dimensional Example (Mock)
```json
{
  "algorithm_details": {
    "dimension_contributions": {
      "error_count": {
        "value": 150.0,
        "center": 50.0,
        "contribution": 10000.0
      },
      "request_count": {
        "value": 1000.0,
        "center": 800.0,
        "contribution": 40000.0
      }
    },
    "anomaly_score": 50000.0,
    "threshold": 10000.0
  }
}
```

### How the Dispatcher Uses algorithm_details

The dispatcher (`DADispatcher.py`) extracts metric/value for the primary anomaly fields:

```python
# From DADispatcher.py post_anomaly_to_insights()
dimension_results = (
    detection_details.get("dimensions", {}) or 
    detection_details.get("dimension_results", {}) or
    detection_details.get("dimension_contributions", {})
)

if dimension_results:
    # Multi-dimensional: pick first anomalous dimension
    for dim_name, dim_data in dimension_results.items():
        if dim_data.get("is_anomaly"):
            metric = dim_name
            value = dim_data.get("value", 0.0)
            break
```

**Recommendation:** Include a `dimension_contributions` key in multi-dim results with per-dimension breakdown.

---

## 7. Advanced: Dual-Mode Algorithms

A dual-mode algorithm can operate in EITHER single-dim OR multi-dim mode, selected dynamically.

### When to Use Dual-Mode
- Algorithm can work both ways (e.g., mock for testing)
- User wants to force multi-dim analysis even when algorithm defaults to single-dim

### Implementation

```python
@register_algorithm
@dataclass
class DualModeAlgorithm:
    """Supports both single-dim and multi-dim modes."""
    
    __algorithm_meta__ = {
        "description": "Dual-mode algorithm",
        "best_for": "Testing or flexible configurations",
        "parameters": ["multi_dimensional"],  # User can override
    }
    
    @property
    def name(self) -> str:
        return "dual_algo"
    
    @property
    def is_multi_dimensional(self) -> bool:
        """Default mode. Can be overridden via resolve_multi_dimensional."""
        return False
    
    @property
    def supports_both_modes(self) -> bool:
        """Signal to orchestrator that this algorithm supports mode resolution."""
        return True
    
    def resolve_multi_dimensional(self, parameters: List[Dict[str, Any]]) -> bool:
        """Dynamically decide mode based on KB config metadata.
        
        Called by orchestrator BEFORE training/detection to determine mode.
        
        Args:
            parameters: List of parameter dicts from KB config
        
        Returns:
            True for multi-dim mode, False for single-dim mode
        """
        # Check for user override in any parameter's metadata
        for param in parameters:
            for meta in param.get("metadata", []):
                if meta.get("key") == "multi_dimensional":
                    val = str(meta.get("value", "")).lower()
                    if val in ("true", "1", "yes"):
                        logger.info(f"[{self.name.upper()}] User forced multi-dim mode")
                        return True
        
        # Default to property value
        return self.is_multi_dimensional
    
    # Implement ALL methods: train, detect, train_multi_dimensional, detect_multi_dimensional
    def train(self, values, parameter=None, **_):
        # Single-dim training
        ...
    
    def detect(self, value, baseline, parameter=None):
        # Single-dim detection
        ...
    
    def train_multi_dimensional(self, observations, parameters):
        # Multi-dim training
        ...
    
    def detect_multi_dimensional(self, observation, baselines, parameters):
        # Multi-dim detection
        ...
```

### KB Config for Multi-Dim Override
```json
{
  "algorithm": {
    "name": "dual_algo",
    "parameters": [
      {
        "dimension": "metric1",
        "is_active": true,
        "metadata": [
          {"key": "multi_dimensional", "value": "true"}
        ]
      },
      {
        "dimension": "metric2",
        "is_active": true
      }
    ]
  }
}
```

---

## 8. Registration & Discovery

### How Registration Works

The `@register_algorithm` decorator (in `algorithm_interface.py`) automatically:
1. Adds your algorithm to the global `ALGORITHM_REGISTRY`
2. Makes it available to the orchestrator and KB-MCP

```python
# From algorithm_interface.py
ALGORITHM_REGISTRY: Dict[str, Any] = {}

def register_algorithm(cls):
    """Decorator to register an algorithm class."""
    instance = cls()
    name = instance.name
    ALGORITHM_REGISTRY[name] = instance
    logger.info(f"[REGISTRY] Registered algorithm: {name}")
    return cls
```

### Discovery at Runtime

The dispatcher exports `algorithms.json` to a shared volume for KB-MCP:

```json
{
  "zscore": {
    "description": "Z-Score statistical anomaly detection",
    "is_multi_dimensional": false,
    "supports_bucketing": true,
    "parameters": ["percentile", "min_points"]
  },
  "iqr": {
    "description": "IQR-based outlier detection",
    "is_multi_dimensional": false,
    "supports_bucketing": true,
    "parameters": ["multiplier"]
  }
}
```

### Verifying Registration

```bash
docker logs da-dispatcher 2>&1 | grep "Available algorithms"
# Output: [DISPATCHER] Available algorithms: ['zscore', 'iqr', 'mock', 'your_algorithm']
```

---

## 9. Testing Your Algorithm

### Unit Tests

Create `MotorDA/Dispatcher/algorithms/your_algorithm/test_your_algorithm.py`:

```python
import pytest
from .your_algorithm import YourAlgorithm


class TestYourAlgorithm:
    def setup_method(self):
        self.algo = YourAlgorithm()
    
    def test_properties(self):
        assert self.algo.name == "your_algorithm"
        assert self.algo.is_multi_dimensional == False
        assert self.algo.min_training_samples > 0
    
    def test_train_basic(self):
        values = [10.0, 12.0, 11.0, 13.0, 10.5, 11.5, 12.5, 11.0, 10.0, 12.0]
        baseline = self.algo.train(values)
        
        assert "your_key" in baseline
        assert baseline["your_key"] > 0
    
    def test_detect_normal(self):
        baseline = {"mean": 10.0, "threshold": 5.0}
        result = self.algo.detect(11.0, baseline)
        
        assert result["is_anomaly"] == False
    
    def test_detect_anomaly(self):
        baseline = {"mean": 10.0, "threshold": 5.0}
        result = self.algo.detect(100.0, baseline)
        
        assert result["is_anomaly"] == True
    
    def test_metadata_override(self):
        values = [10.0] * 20
        parameter = {
            "dimension": "test",
            "metadata": [{"key": "your_param", "value": "custom_value"}]
        }
        baseline = self.algo.train(values, parameter)
        # Assert custom parameter was used
```

### Integration Test

```bash
# 1. Rebuild dispatcher
docker compose build dispatcher
docker compose up -d dispatcher

# 2. Check logs for registration
docker logs da-dispatcher 2>&1 | grep your_algorithm

# 3. Create a KB config using your algorithm via KB-MCP
# Use create_da_config MCP tool with algorithm.name = "your_algorithm"

# 4. Check for training/detection in logs
docker logs da-dispatcher -f
```

---

## 10. Complete Examples

### Example 1: Simple Mean-Based Algorithm

```python
"""Mean-based anomaly detection - flags values far from mean."""

from dataclasses import dataclass
from typing import Dict, Any, List
import logging

from ...algorithm_interface import register_algorithm

logger = logging.getLogger(__name__)


@register_algorithm
@dataclass
class MeanAlgorithm:
    """Simple mean-based anomaly detection.
    
    Flags values more than `deviation_factor` standard deviations from mean.
    """
    
    __algorithm_meta__ = {
        "description": "Simple mean-based detection using standard deviation",
        "best_for": "Quick sanity checks on normally distributed data",
        "parameters": ["deviation_factor"],
    }
    
    @property
    def name(self) -> str:
        return "mean"
    
    @property
    def is_multi_dimensional(self) -> bool:
        return False
    
    @property
    def supports_bucketing(self) -> bool:
        return True
    
    @property
    def min_training_samples(self) -> int:
        return 5
    
    def train(self, values: List[float], parameter: Dict[str, Any] = None, **_) -> Dict[str, Any]:
        # Default parameter
        deviation_factor = 3.0
        
        # Override from metadata
        if parameter:
            for meta in parameter.get("metadata", []):
                if meta.get("key") == "deviation_factor":
                    try:
                        deviation_factor = float(meta.get("value"))
                    except:
                        pass
        
        n = len(values)
        mean = sum(values) / n
        variance = sum((x - mean) ** 2 for x in values) / n
        std = variance ** 0.5
        
        threshold = deviation_factor * std
        
        logger.info(f"[MEAN] Trained: mean={mean:.2f}, std={std:.2f}, threshold={threshold:.2f}")
        
        return {
            "mean": mean,
            "std": std,
            "threshold": threshold,
            "deviation_factor": deviation_factor,
            "data_points": n,
        }
    
    def detect(self, value: float, baseline: Dict[str, Any], parameter: Dict[str, Any] = None) -> Dict[str, Any]:
        mean = baseline.get("mean", 0)
        threshold = baseline.get("threshold", float("inf"))
        
        deviation = abs(value - mean)
        is_anomaly = deviation > threshold
        
        return {
            "is_anomaly": is_anomaly,
            "value": value,
            "mean": mean,
            "deviation": deviation,
            "threshold": threshold,
        }
    
    def detect_batch(self, values: List[float], baseline: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [self.detect(v, baseline) for v in values]
```

### Example 2: Mahalanobis Distance (Multi-Dimensional)

```python
"""Mahalanobis Distance - multi-dimensional anomaly detection."""

from dataclasses import dataclass
from typing import Dict, Any, List
import logging
import numpy as np

from ...algorithm_interface import register_algorithm

logger = logging.getLogger(__name__)


@register_algorithm
@dataclass
class MahalanobisAlgorithm:
    """Mahalanobis distance based anomaly detection.
    
    Considers correlations between dimensions using covariance matrix.
    Useful when dimensions are correlated.
    """
    
    __algorithm_meta__ = {
        "description": "Mahalanobis distance multi-dimensional anomaly detection",
        "best_for": "Correlated multi-variate data, detects joint anomalies",
        "parameters": ["chi2_percentile"],
    }
    
    @property
    def name(self) -> str:
        return "mahalanobis"
    
    @property
    def is_multi_dimensional(self) -> bool:
        return True
    
    @property
    def supports_bucketing(self) -> bool:
        return True
    
    @property
    def min_training_samples(self) -> int:
        return 50  # Need enough for covariance estimation
    
    def train_multi_dimensional(
        self,
        observations: List[Dict[str, Any]],
        parameters: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        # Get dimension names
        dim_names = [p["dimension"] for p in parameters if p.get("is_active", True)]
        n_dims = len(dim_names)
        
        # Resolve chi2_percentile from metadata
        chi2_percentile = 99.5
        for param in parameters:
            for meta in param.get("metadata", []):
                if meta.get("key") == "chi2_percentile":
                    try:
                        chi2_percentile = float(meta.get("value"))
                    except:
                        pass
        
        # Build data matrix
        data = []
        for obs in observations:
            row = [float(obs.get(dim, 0)) for dim in dim_names]
            data.append(row)
        
        data = np.array(data)
        
        # Compute mean and covariance
        mean = np.mean(data, axis=0)
        cov = np.cov(data.T)
        
        # Ensure covariance is invertible
        try:
            cov_inv = np.linalg.inv(cov)
        except np.linalg.LinAlgError:
            # Add small regularization
            cov_inv = np.linalg.inv(cov + np.eye(n_dims) * 1e-6)
        
        # Chi-squared threshold for n_dims degrees of freedom
        from scipy import stats
        threshold = stats.chi2.ppf(chi2_percentile / 100.0, df=n_dims)
        
        logger.info(f"[MAHALANOBIS] Multi-dim trained: {len(observations)} obs, {n_dims} dims, threshold={threshold:.2f}")
        
        return {
            "mean": mean.tolist(),
            "cov_inv": cov_inv.tolist(),
            "threshold": threshold,
            "dim_names": dim_names,
            "chi2_percentile": chi2_percentile,
        }
    
    def detect_multi_dimensional(
        self,
        observation: Dict[str, Any],
        baselines: Dict[str, Any],
        parameters: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        dim_names = baselines["dim_names"]
        mean = np.array(baselines["mean"])
        cov_inv = np.array(baselines["cov_inv"])
        threshold = baselines["threshold"]
        
        # Extract observation values
        x = np.array([float(observation.get(dim, 0)) for dim in dim_names])
        
        # Compute Mahalanobis distance squared
        diff = x - mean
        d_squared = diff.T @ cov_inv @ diff
        
        is_anomaly = d_squared > threshold
        
        # Compute per-dimension contributions
        contributions = {}
        for i, dim in enumerate(dim_names):
            contributions[dim] = {
                "value": x[i],
                "center": mean[i],
                "contribution": (diff[i] ** 2) * cov_inv[i, i],
            }
        
        return {
            "is_anomaly": bool(is_anomaly),
            "mahalanobis_distance_squared": float(d_squared),
            "threshold": threshold,
            "dimension_contributions": contributions,
        }
```

---

## Summary Checklist

- [ ] Create algorithm directory under `MotorDA/Dispatcher/algorithms/`
- [ ] Implement class with `@register_algorithm` decorator
- [ ] Add `__algorithm_meta__` for documentation
- [ ] Implement required properties: `name`, `is_multi_dimensional`, `supports_bucketing`, `min_training_samples`
- [ ] Implement required methods based on algorithm type
- [ ] Support user-overridable parameters via metadata
- [ ] Return meaningful `algorithm_details` structure
- [ ] Add `__init__.py` export
- [ ] Write unit tests
- [ ] Rebuild dispatcher and verify registration
- [ ] Test with a real KB config

---

## Questions?

Check existing implementations:
- **Z-Score**: `algorithms/zscore/zscore.py` - Single-dim statistical
- **IQR**: `algorithms/iqr/iqr.py` - Single-dim quartile-based
- **Mock**: `algorithms/mock/mock.py` - Dual-mode reference implementation
