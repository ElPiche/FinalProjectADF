# How to Add a New Algorithm to the Anomaly Detection Framework

**Last Updated:** December 1, 2025  
**Status:** Algorithm-Agnostic Stack Complete

This guide walks you through adding a new anomaly detection algorithm to the framework. The system is designed to be **extensible** - adding a new algorithm requires changes in exactly **3 locations**.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Step-by-Step Guide](#2-step-by-step-guide)
   - [Step 1: Create the Algorithm Class](#step-1-create-the-algorithm-class-motorda)
   - [Step 2: Register in Algorithm Registry](#step-2-register-in-algorithm-registry-motorda)
   - [Step 3: Add to KB-MCP Supported Algorithms](#step-3-add-to-kb-mcp-supported-algorithms-mcp)
3. [Complete Example: Adding ARMA Algorithm](#3-complete-example-adding-arma-algorithm)
4. [Testing Your Algorithm](#4-testing-your-algorithm)
5. [Using the Algorithm](#5-using-the-algorithm)
6. [Improvement Suggestions](#6-improvement-suggestions)

---

## 1. Architecture Overview

The algorithm system has three layers:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         USER INTERFACE LAYER                             │
│                                                                          │
│   Claude Desktop ──► KB-MCP ──► Validates algorithm name                │
│                          │                                               │
│                          ▼                                               │
│              SUPPORTED_ALGORITHMS = {"zscore", "arma", ...}             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         DISPATCHER LAYER                                 │
│                                                                          │
│   DADispatcher.py ──► get_algorithm(name) ──► ALGORITHM_REGISTRY        │
│                                                     │                    │
│                          ┌──────────────────────────┘                    │
│                          ▼                                               │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                     │
│   │ ZScoreAlgo  │  │  ARMAAlgo   │  │ KMeansAlgo  │  ...                │
│   └─────────────┘  └─────────────┘  └─────────────┘                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         ALGORITHM LAYER                                  │
│                                                                          │
│   Pure statistical implementations (no MongoDB, no buckets)              │
│   - train(values) → baseline dict                                        │
│   - detect(value, baseline) → {is_anomaly, score, ...}                  │
└─────────────────────────────────────────────────────────────────────────┘
```

**Key Design Principles:**

1. **Algorithms are pure statistics** - No MongoDB, no HTTP, no bucket logic
2. **Orchestrators handle context** - Bucket resolution, config lookup
3. **Registry enables dynamic dispatch** - No switch statements
4. **KB-MCP validates early** - Prevents invalid algorithm names at config time

---

## 2. Step-by-Step Guide

### Step 1: Create the Algorithm Class (MotorDA)

**Location:** `MotorDA/Dispatcher/algorithm_interface.py` (or a new file in `MotorDA/Dispatcher/algorithms/`)

Your algorithm must implement these methods:

```python
from dataclasses import dataclass
from typing import Dict, Any, List

@dataclass
class YourAlgorithm:
    """Your algorithm implementation."""
    
    @property
    def name(self) -> str:
        """Return the algorithm identifier (lowercase)."""
        return "your_algo"
    
    def train(self, values: List[float], percentile: float = 99.5, **kwargs) -> Dict[str, Any]:
        """
        Train a baseline from raw float values.
        
        Args:
            values: List of numeric training values
            percentile: Threshold percentile (default 99.5)
            **kwargs: Algorithm-specific parameters
        
        Returns:
            Serializable dict with trained model parameters.
            MUST be JSON-serializable for MongoDB storage.
        """
        # Your training logic here
        return {
            "model_param_1": ...,
            "model_param_2": ...,
            "threshold": ...,
        }
    
    def detect(self, value: float, baseline: Dict[str, Any]) -> Dict[str, Any]:
        """
        Detect if a single value is anomalous.
        
        Args:
            value: The value to check
            baseline: Dict from train() method
        
        Returns:
            Dict with at least 'is_anomaly' (bool) key.
        """
        # Your detection logic here
        return {
            "is_anomaly": True or False,
            "score": ...,
            "threshold": baseline["threshold"],
            "value": value,
        }
    
    def detect_batch(self, values: List[float], baseline: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect anomalies for multiple values."""
        return [self.detect(v, baseline) for v in values]
    
    def train_multi_dimension(
        self,
        observed_values: List[Dict[str, Any]],
        parameters: List[Dict[str, Any]],
        percentile: float = 99.5
    ) -> Dict[str, Any]:
        """
        Train baselines for multiple dimensions.
        
        This is called by TrainingOrchestrator.
        
        Args:
            observed_values: List of observation dicts with dimension values
            parameters: Algorithm parameters with 'dimension' keys
            percentile: Threshold percentile
        
        Returns:
            Dict mapping dimension names to baseline dicts.
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
        
        return result
    
    def detect_multi_dimension(
        self,
        observation: Dict[str, Any],
        baselines: Dict[str, Dict[str, Any]],
        parameters: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Detect anomalies across multiple dimensions.
        
        This is called by DetectionOrchestrator.
        
        Args:
            observation: Observation dict with dimension values
            baselines: Per-dimension baselines from train_multi_dimension
            parameters: Algorithm parameters with 'dimension' keys
        
        Returns:
            Dict with 'is_anomaly' flag and per-dimension results.
        """
        dimension_results = {}
        is_any_anomaly = False
        
        for param in parameters:
            dimension = param.get("dimension")
            if not dimension:
                continue
            
            baseline = baselines.get(dimension)
            if not baseline:
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
```

### Step 2: Register in Algorithm Registry (MotorDA)

**Location:** `MotorDA/Dispatcher/algorithm_interface.py`

Add your algorithm to the `ALGORITHM_REGISTRY`:

```python
# At the bottom of algorithm_interface.py, find:
ALGORITHM_REGISTRY: Dict[str, AnomalyAlgorithm] = {
    "zscore": ZScoreAlgorithm(),
    # Add your algorithm here:
    "your_algo": YourAlgorithm(),
}
```

That's it for the Dispatcher side!

### Step 3: Add to KB-MCP Supported Algorithms (MCP)

**Location:** `MCP/KB-MCP/models.py`

Find the `SUPPORTED_ALGORITHMS` set at the top of the file and add your algorithm:

```python
# Line ~16 in models.py
SUPPORTED_ALGORITHMS = {"zscore", "your_algo"}  # ← Add your algorithm name
```

This enables:
- Validation when users create configs via Claude Desktop
- Clear error messages if wrong algorithm name is used
- Autocomplete/suggestion support in MCP tools

---

## 3. Complete Example: Adding ARMA Algorithm

Here's a complete example of adding an ARMA (AutoRegressive Moving Average) algorithm:

### Step 1: Create `MotorDA/Dispatcher/algorithms/arma_algorithm.py`

```python
"""ARMA Algorithm for time-series anomaly detection."""

from dataclasses import dataclass
from typing import Dict, Any, List
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass 
class ARMABaseline:
    """ARMA model baseline parameters."""
    ar_coeffs: List[float]
    ma_coeffs: List[float]
    mean: float
    residual_std: float
    threshold: float
    data_points: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "ar_coeffs": self.ar_coeffs,
            "ma_coeffs": self.ma_coeffs,
            "mean": self.mean,
            "residual_std": self.residual_std,
            "threshold": self.threshold,
            "data_points": self.data_points,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ARMABaseline":
        return cls(
            ar_coeffs=d["ar_coeffs"],
            ma_coeffs=d["ma_coeffs"],
            mean=d["mean"],
            residual_std=d["residual_std"],
            threshold=d["threshold"],
            data_points=d.get("data_points", 0),
        )


@dataclass
class ARMAAlgorithm:
    """ARMA implementation of AnomalyAlgorithm Protocol."""
    
    @property
    def name(self) -> str:
        return "arma"
    
    def train(
        self, 
        values: List[float], 
        percentile: float = 99.5,
        ar_order: int = 2,
        ma_order: int = 1,
        **_
    ) -> Dict[str, Any]:
        """Train ARMA model from values."""
        if len(values) < max(ar_order, ma_order) + 3:
            # Not enough data, return simple stats
            arr = np.array(values)
            return ARMABaseline(
                ar_coeffs=[],
                ma_coeffs=[],
                mean=float(np.mean(arr)),
                residual_std=float(np.std(arr)) or 1e-6,
                threshold=3.0,
                data_points=len(values)
            ).to_dict()
        
        arr = np.array(values, dtype=float)
        mean = float(np.mean(arr))
        centered = arr - mean
        
        # Simple AR coefficient estimation (Yule-Walker)
        ar_coeffs = self._estimate_ar_coeffs(centered, ar_order)
        
        # Calculate residuals
        residuals = self._calculate_residuals(centered, ar_coeffs)
        residual_std = float(np.std(residuals)) or 1e-6
        
        # MA coefficients from residual autocorrelation
        ma_coeffs = self._estimate_ma_coeffs(residuals, ma_order)
        
        # Threshold based on residual distribution
        threshold = float(np.percentile(np.abs(residuals / residual_std), percentile))
        
        return ARMABaseline(
            ar_coeffs=ar_coeffs,
            ma_coeffs=ma_coeffs,
            mean=mean,
            residual_std=residual_std,
            threshold=threshold,
            data_points=len(values)
        ).to_dict()
    
    def _estimate_ar_coeffs(self, values: np.ndarray, order: int) -> List[float]:
        """Estimate AR coefficients using Yule-Walker equations."""
        if order == 0:
            return []
        # Simplified estimation
        n = len(values)
        r = np.correlate(values, values, mode='full')[n-1:]
        r = r[:order+1]
        if r[0] == 0:
            return [0.0] * order
        # Solve Yule-Walker
        R = np.zeros((order, order))
        for i in range(order):
            for j in range(order):
                R[i, j] = r[abs(i - j)]
        try:
            coeffs = np.linalg.solve(R, r[1:order+1])
            return coeffs.tolist()
        except np.linalg.LinAlgError:
            return [0.0] * order
    
    def _calculate_residuals(self, values: np.ndarray, ar_coeffs: List[float]) -> np.ndarray:
        """Calculate residuals after AR filtering."""
        if not ar_coeffs:
            return values
        order = len(ar_coeffs)
        residuals = []
        for t in range(order, len(values)):
            pred = sum(c * values[t-i-1] for i, c in enumerate(ar_coeffs))
            residuals.append(values[t] - pred)
        return np.array(residuals) if residuals else values
    
    def _estimate_ma_coeffs(self, residuals: np.ndarray, order: int) -> List[float]:
        """Estimate MA coefficients from residuals."""
        if order == 0 or len(residuals) < order + 1:
            return []
        # Simplified: use autocorrelation of residuals
        n = len(residuals)
        r = np.correlate(residuals, residuals, mode='full')[n-1:]
        if r[0] == 0:
            return [0.0] * order
        return (r[1:order+1] / r[0]).tolist()
    
    def detect(self, value: float, baseline: Dict[str, Any]) -> Dict[str, Any]:
        """Detect if value is anomalous using ARMA model."""
        bl = ARMABaseline.from_dict(baseline)
        
        # Simple detection: z-score of deviation from mean
        deviation = value - bl.mean
        z_score = deviation / bl.residual_std
        is_anomaly = abs(z_score) > bl.threshold
        
        return {
            "is_anomaly": is_anomaly,
            "value": value,
            "z_score": z_score,
            "mean": bl.mean,
            "threshold": bl.threshold,
        }
    
    def detect_batch(self, values: List[float], baseline: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect anomalies for multiple values."""
        return [self.detect(v, baseline) for v in values]
    
    def train_multi_dimension(
        self,
        observed_values: List[Dict[str, Any]],
        parameters: List[Dict[str, Any]],
        percentile: float = 99.5
    ) -> Dict[str, Any]:
        """Train ARMA baselines for multiple dimensions."""
        result = {}
        for param in parameters:
            dimension = param.get("dimension")
            if not dimension:
                continue
            
            values = []
            for obs in observed_values:
                val = obs.get(dimension)
                if val is not None:
                    try:
                        values.append(float(val))
                    except (ValueError, TypeError):
                        pass
            
            if len(values) >= 3:
                baseline = self.train(values, percentile)
                result[dimension] = baseline
                logger.info(f"[ARMA] Trained dimension '{dimension}' with {len(values)} values")
            else:
                logger.warning(f"[ARMA] Insufficient values for dimension '{dimension}': {len(values)}")
        
        return result
    
    def detect_multi_dimension(
        self,
        observation: Dict[str, Any],
        baselines: Dict[str, Dict[str, Any]],
        parameters: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Detect anomalies across multiple dimensions."""
        dimension_results = {}
        is_any_anomaly = False
        
        for param in parameters:
            dimension = param.get("dimension")
            if not dimension:
                continue
            
            baseline = baselines.get(dimension)
            if not baseline:
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
```

### Step 2: Register in `algorithm_interface.py`

```python
# Add import at top
from Dispatcher.algorithms.arma_algorithm import ARMAAlgorithm

# Add to registry
ALGORITHM_REGISTRY: Dict[str, AnomalyAlgorithm] = {
    "zscore": ZScoreAlgorithm(),
    "arma": ARMAAlgorithm(),  # ← Add this line
}
```

### Step 3: Update `MCP/KB-MCP/models.py`

```python
SUPPORTED_ALGORITHMS = {"zscore", "arma"}  # ← Add "arma"
```

---

## 4. Testing Your Algorithm

### Unit Tests

Create `MotorDA/Dispatcher/tests/test_arma_algorithm.py`:

```python
import pytest
from Dispatcher.algorithms.arma_algorithm import ARMAAlgorithm

class TestARMAAlgorithm:
    def setup_method(self):
        self.algo = ARMAAlgorithm()
    
    def test_name(self):
        assert self.algo.name == "arma"
    
    def test_train_basic(self):
        values = [10, 12, 11, 13, 12, 14, 13, 15]
        baseline = self.algo.train(values)
        assert "mean" in baseline
        assert "threshold" in baseline
        assert "residual_std" in baseline
    
    def test_detect_normal(self):
        values = [10, 12, 11, 13, 12, 14, 13, 15]
        baseline = self.algo.train(values)
        result = self.algo.detect(12.5, baseline)
        assert "is_anomaly" in result
        assert result["is_anomaly"] == False
    
    def test_detect_anomaly(self):
        values = [10, 12, 11, 13, 12, 14, 13, 15]
        baseline = self.algo.train(values)
        result = self.algo.detect(100.0, baseline)
        assert result["is_anomaly"] == True
```

### Integration Test in Docker

```bash
# Rebuild dispatcher
docker-compose build dispatcher
docker-compose restart dispatcher

# Check algorithm is registered
docker logs da-dispatcher 2>&1 | head -10
# Should show: [DISPATCHER] Available algorithms: ['zscore', 'arma']

# Test via MongoDB insert
docker exec mongodb mongosh -u admin -p '1q2w3E*' --authenticationDatabase admin --eval "
  db = db.getSiblingDB('anomaly_detection');
  db.series.insertOne({
    config_id: 'test-arma-config',
    type: 'training',
    observed_values: [
      {timestamp: '2025-11-15T10:00:00Z', error_count: 5},
      {timestamp: '2025-11-15T11:00:00Z', error_count: 10},
      {timestamp: '2025-11-15T12:00:00Z', error_count: 8}
    ]
  });
"
```

---

## 5. Using the Algorithm

### Via Claude Desktop (KB-MCP)

```
User: Create a new anomaly detection config using ARMA algorithm

Claude: I'll create the config for you.

[Calls create_da_config with algorithm.name = "arma"]
```

### Via Direct MCP Tool Call

```json
{
  "name": "my-arma-detection",
  "description": "ARMA-based anomaly detection for API latency",
  "source_index": "api-logs",
  "elasticsearch_sql_query": "SELECT \"@timestamp\", AVG(latency_ms) AS latency FROM \"api-logs\" WHERE \"@timestamp\" >= '$from' AND \"@timestamp\" < '$to' GROUP BY 1",
  "query_mode": {"type": "aggregated", "timestamp_field": "@timestamp"},
  "training_from": "2025-11-01T00:00:00Z",
  "training_to": "2025-12-01T00:00:00Z",
  "training_is_active": true,
  "detection_frequency": "*/5 * * * *",
  "detection_window": 300,
  "detection_start": "2025-12-01T00:00:00Z",
  "detection_is_active": true,
  "algorithm": {
    "name": "arma",
    "parameters": [{"dimension": "latency", "is_active": true}]
  }
}
```

---

## 6. Improvement Suggestions

### Current Pain Points

| Issue | Current State | Impact |
|-------|---------------|--------|
| **3 files to edit** | Must edit algorithm_interface.py, models.py | Easy to forget one |
| **Manual registration** | Must add to ALGORITHM_REGISTRY dict | Boilerplate |
| **Duplicate algorithm lists** | SUPPORTED_ALGORITHMS in MCP, ALGORITHM_REGISTRY in Dispatcher | Can get out of sync |
| **No algorithm discovery** | Hardcoded lists | Can't dynamically load plugins |

### Proposed Improvements

#### Improvement 1: Auto-Registration via Decorators

Instead of manually adding to `ALGORITHM_REGISTRY`:

```python
# Current (manual)
ALGORITHM_REGISTRY = {
    "zscore": ZScoreAlgorithm(),
    "arma": ARMAAlgorithm(),
}

# Proposed (auto-registration)
@register_algorithm
@dataclass
class ARMAAlgorithm:
    @property
    def name(self) -> str:
        return "arma"
    # ...
```

Implementation:

```python
# algorithm_interface.py
ALGORITHM_REGISTRY: Dict[str, "AnomalyAlgorithm"] = {}

def register_algorithm(cls):
    """Decorator to auto-register algorithm classes."""
    instance = cls()
    ALGORITHM_REGISTRY[instance.name.lower()] = instance
    return cls
```

#### Improvement 2: Single Source of Truth for Algorithm Names

Create a shared constants file:

```python
# shared/algorithm_constants.py (new file)
SUPPORTED_ALGORITHMS = frozenset({"zscore", "arma", "kmeans"})

# MCP/KB-MCP/models.py
from shared.algorithm_constants import SUPPORTED_ALGORITHMS

# MotorDA/Dispatcher/algorithm_interface.py
from shared.algorithm_constants import SUPPORTED_ALGORITHMS

def validate_registry():
    """Ensure registry matches SUPPORTED_ALGORITHMS."""
    registered = set(ALGORITHM_REGISTRY.keys())
    if registered != SUPPORTED_ALGORITHMS:
        missing = SUPPORTED_ALGORITHMS - registered
        extra = registered - SUPPORTED_ALGORITHMS
        raise RuntimeError(f"Algorithm mismatch! Missing: {missing}, Extra: {extra}")
```

#### Improvement 3: Dynamic Algorithm Discovery

Automatically discover and load algorithm modules:

```python
# algorithm_interface.py
import importlib
import pkgutil
from pathlib import Path

def discover_algorithms():
    """Auto-discover algorithm classes in algorithms/ directory."""
    algorithms_path = Path(__file__).parent / "algorithms"
    
    for _, module_name, _ in pkgutil.iter_modules([str(algorithms_path)]):
        module = importlib.import_module(f"Dispatcher.algorithms.{module_name}")
        
        # Find classes with @register_algorithm decorator
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if hasattr(attr, "_is_algorithm") and attr._is_algorithm:
                instance = attr()
                ALGORITHM_REGISTRY[instance.name] = instance

# Call at module load
discover_algorithms()
```

#### Improvement 4: MCP Tool to List Available Algorithms

Add a new MCP tool:

```python
# mcp_tools.py
@mcp.tool()
async def list_available_algorithms() -> str:
    """List all supported anomaly detection algorithms.
    
    Returns details about each algorithm including:
    - Name
    - Description
    - Required parameters
    - Example usage
    """
    # Query dispatcher or use shared constants
    algorithms = {
        "zscore": {
            "description": "Z-Score statistical anomaly detection",
            "best_for": "Stationary time series with normal distribution",
            "parameters": ["percentile (default 99.5)"]
        },
        "arma": {
            "description": "ARMA time-series model",
            "best_for": "Time series with autocorrelation",
            "parameters": ["ar_order (default 2)", "ma_order (default 1)"]
        }
    }
    return json.dumps(algorithms, indent=2)
```

#### Improvement 5: Algorithm Metadata in Registry

Add metadata to algorithms for better discoverability:

```python
@dataclass
class AlgorithmMetadata:
    name: str
    description: str
    best_for: str
    min_data_points: int
    parameters: List[str]

@dataclass
class ZScoreAlgorithm:
    metadata = AlgorithmMetadata(
        name="zscore",
        description="Z-Score statistical anomaly detection",
        best_for="Stationary time series",
        min_data_points=3,
        parameters=["percentile"]
    )
    
    @property
    def name(self) -> str:
        return self.metadata.name
```

### Implementation Priority

| Improvement | Effort | Impact | Priority |
|-------------|--------|--------|----------|
| Auto-registration decorator | Low | Medium | 🟢 Do First |
| Single source of truth | Low | High | 🟢 Do First |
| List algorithms MCP tool | Low | Medium | 🟢 Do First |
| Dynamic discovery | Medium | Medium | 🟡 Nice to Have |
| Algorithm metadata | Medium | High | 🟡 Nice to Have |

### Quick Win: Sync Check Script

Add a validation script that runs in CI:

```python
# scripts/validate_algorithm_sync.py
#!/usr/bin/env python3
"""Validate that KB-MCP and Dispatcher algorithm lists are in sync."""

import sys
sys.path.insert(0, "MCP/KB-MCP")
sys.path.insert(0, "MotorDA")

from models import SUPPORTED_ALGORITHMS
from Dispatcher.algorithm_interface import ALGORITHM_REGISTRY

mcp_algos = set(SUPPORTED_ALGORITHMS)
dispatcher_algos = set(ALGORITHM_REGISTRY.keys())

if mcp_algos != dispatcher_algos:
    print("❌ Algorithm mismatch detected!")
    print(f"   MCP only: {mcp_algos - dispatcher_algos}")
    print(f"   Dispatcher only: {dispatcher_algos - mcp_algos}")
    sys.exit(1)

print(f"✅ Algorithms in sync: {sorted(mcp_algos)}")
```

---

## Summary

### Current Process (3 Steps)

1. **Create algorithm class** in `MotorDA/Dispatcher/` implementing the protocol
2. **Add to ALGORITHM_REGISTRY** in `algorithm_interface.py`
3. **Add to SUPPORTED_ALGORITHMS** in `MCP/KB-MCP/models.py`

### Recommended Improvements (Priority Order)

1. **Auto-registration decorator** - Eliminate step 2
2. **Single source of truth** - Share algorithm list between MCP and Dispatcher
3. **List algorithms MCP tool** - Better user experience
4. **Validation script** - Catch sync issues in CI

With these improvements, adding a new algorithm would be reduced to:

1. Create algorithm class with `@register_algorithm` decorator
2. Done! (Automatic sync between MCP and Dispatcher)
