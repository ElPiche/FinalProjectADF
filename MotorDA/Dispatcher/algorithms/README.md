# Algorithms Package

This folder contains all anomaly detection algorithms for the DA (Data Anomaly) system.

## Architecture

```
algorithms/
├── __init__.py              # Auto-discovers all algorithms (no manual imports needed!)
├── README.md                # This file
├── zscore/                  # Z-Score algorithm (single-dimensional)
│   ├── zscore.py            # Main algorithm class with @register_algorithm
│   ├── zscore_algorithm.py  # Pure statistical functions
│   └── tests/
│       └── test_zscore_algorithm.py
├── iqr/                     # IQR algorithm (single-dimensional)
│   ├── iqr.py
│   └── tests/
│       └── test_iqr_algorithm.py
├── k_means/                 # K-Means algorithm (multi-dimensional)
│   ├── k_means.py
│   └── tests/
│       └── test_k_means_algorithm.py
└── mock/                    # Mock algorithm for testing (dual-mode)
    ├── mock.py
    └── tests/
        └── test_mock_algorithm.py
```

## How to Add a New Algorithm

### Step 1: Create Your Algorithm Folder

```bash
mkdir -p MotorDA/Dispatcher/algorithms/my_algo/tests
```

### Step 2: Create the Algorithm Class

Create `my_algo/my_algo.py`:

```python
"""My Algorithm - Brief description.

Detailed explanation of what this algorithm does.
"""

from dataclasses import dataclass
from typing import Dict, Any, List
import logging

from ...algorithm_interface import register_algorithm

logger = logging.getLogger(__name__)


@register_algorithm  # <-- This decorator auto-registers your algorithm!
@dataclass
class MyAlgorithm:
    """My custom anomaly detection algorithm."""
    
    # Metadata shown in MCP tool responses
    __algorithm_meta__ = {
        "description": "Brief description of your algorithm",
        "best_for": "When to use this algorithm",
        "parameters": ["param1", "param2"],
    }
    
    @property
    def name(self) -> str:
        """Algorithm identifier (lowercase, used in configs)."""
        return "my_algo"
    
    def train(self, values: List[float], **kwargs) -> Dict[str, Any]:
        """Train model from values.
        
        Args:
            values: List of numeric training values
            **kwargs: Algorithm-specific parameters
        
        Returns:
            Serializable model dict (stored in MongoDB)
        """
        # Your training logic here
        return {
            "mean": sum(values) / len(values) if values else 0,
            "data_points": len(values),
        }
    
    def detect(self, value: float, model: Dict[str, Any]) -> Dict[str, Any]:
        """Detect if a single value is anomalous.
        
        Args:
            value: Value to check
            model: Trained model from train()
        
        Returns:
            Dict with at least 'is_anomaly' key
        """
        # Your detection logic here
        return {
            "is_anomaly": False,
            "value": value,
        }
    
    def detect_batch(self, values: List[float], model: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect anomalies for multiple values."""
        return [self.detect(v, model) for v in values]
    
    # OPTIONAL: Multi-dimension support (recommended)
    def train_multi_dimension(
        self,
        observed_values: List[Dict[str, Any]],
        parameters: List[Dict[str, Any]],
        **kwargs
    ) -> Dict[str, Any]:
        """Train on multiple dimensions.
        
        Args:
            observed_values: List of observation dicts
            parameters: List with 'dimension' keys
        
        Returns:
            Dict mapping dimension names to models
        """
        result = {}
        for param in parameters:
            dimension = param.get("dimension")
            if not dimension:
                continue
            values = [obs.get(dimension) for obs in observed_values if obs.get(dimension) is not None]
            values = [float(v) for v in values]
            if values:
                result[dimension] = self.train(values, **kwargs)
        return result
    
    def detect_multi_dimension(
        self,
        observation: Dict[str, Any],
        models: Dict[str, Dict[str, Any]],
        parameters: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Detect anomalies across multiple dimensions."""
        is_anomaly = False
        dimension_results = {}
        
        for param in parameters:
            dimension = param.get("dimension")
            model = models.get(dimension)
            value = observation.get(dimension)
            
            if dimension and model and value is not None:
                result = self.detect(float(value), model)
                dimension_results[dimension] = result
                if result.get("is_anomaly"):
                    is_anomaly = True
        
        return {"is_anomaly": is_anomaly, "dimensions": dimension_results}
```

### Step 3: Add Tests

Create `my_algo/tests/test_my_algo.py`:

```python
"""Tests for My Algorithm."""

import pytest
from MotorDA.Dispatcher.algorithms.my_algo.my_algo import MyAlgorithm


@pytest.fixture
def algo():
    return MyAlgorithm()


class TestTrain:
    def test_train_basic(self, algo):
        model = algo.train([1, 2, 3, 4, 5])
        assert "mean" in model
        assert model["data_points"] == 5


class TestDetect:
    def test_detect_normal(self, algo):
        model = algo.train([1, 2, 3, 4, 5])
        result = algo.detect(3.0, model)
        assert "is_anomaly" in result
```

### Step 4: That's It!

The auto-discovery in `__init__.py` will automatically:
1. Find your `my_algo/my_algo.py` file
2. Import it and trigger the `@register_algorithm` decorator
3. Make it available via `get_algorithm("my_algo")`
4. Export it to the shared registry for KB-MCP to discover

**No manual imports or modifications to `__init__.py` needed!**

## Running Tests

```bash
# Run all algorithm tests
docker exec da-dispatcher python -m pytest /app/MotorDA/Dispatcher/algorithms/*/tests/ -v

# Run specific algorithm tests
docker exec da-dispatcher python -m pytest /app/MotorDA/Dispatcher/algorithms/zscore/tests/ -v
docker exec da-dispatcher python -m pytest /app/MotorDA/Dispatcher/algorithms/iqr/tests/ -v
```

## Algorithm Interface

All algorithms must implement the `AnomalyAlgorithm` protocol:

| Method | Required | Description |
|--------|----------|-------------|
| `name` | ✅ | Property returning algorithm identifier |
| `train(values, **kwargs)` | ✅ | Train model from values |
| `detect(value, model)` | ✅ | Detect single value |
| `detect_batch(values, model)` | ✅ | Detect multiple values |
| `train_multi_dimension(...)` | Optional | Multi-dimension training |
| `detect_multi_dimension(...)` | Optional | Multi-dimension detection |

## Disabling an Algorithm

To disable an algorithm without deleting it, comment out the `@register_algorithm` decorator:

```python
# @register_algorithm  # <-- Commented out = algorithm won't register
@dataclass
class MockAlgorithm:
    ...
```

## Available Algorithms

| Name | Description | Best For |
|------|-------------|----------|
| `zscore` | Statistical detection using standard deviations | Normal distributions |
| `iqr` | IQR-based outlier detection | Skewed data, robust to outliers |
| `mock` | Simple threshold detection | Testing only (disabled by default) |
