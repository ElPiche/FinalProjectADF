# How to Add a New Anomaly Detection Algorithm

This guide explains how to add a new **POINT mode** algorithm to the Anomaly Detection Framework. POINT algorithms evaluate each data point independently (like Z-Score, IQR, Threshold).

> **📚 Prerequisites:** Read these documents first:
> - [Algorithm-Taxonomy.md](./Algorithm-Taxonomy.md) - Understand algorithm categories
> - [Bucket-Compatibility-Guide.md](./Bucket-Compatibility-Guide.md) - Choose correct bucket mode

> **⚠️ Note:** For SERIES algorithms (ARMA, LSTM), additional infrastructure is required. See Phase 2 documentation.

---

## Quick Start (2 Steps)

### Step 1: Create Your Algorithm

Create a new file `MotorDA/YourAlgorithm/algorithm.py`:

```python
"""Your Algorithm implementation."""

import statistics
from typing import Any, Dict, List, Optional

from MotorDA.base_algorithm import (
    BaseAlgorithm,
    BucketMode,
    DetectionMode,
    DetectionResult,
    TrainingResult,
)


class YourAlgorithm(BaseAlgorithm):
    """Brief description of your algorithm."""
    
    # Required: Algorithm metadata
    name = "youralgorithm"
    display_name = "Your Algorithm Name"
    detection_mode = DetectionMode.POINT
    bucket_mode = BucketMode.SEGMENT  # or FEATURE, METADATA_ONLY
    
    @property
    def minimum_training_points(self) -> int:
        return 10  # Adjust based on algorithm needs
    
    def train(
        self,
        data: List[Dict[str, Any]],
        bucket_key: Optional[str] = None,
        bucket_features: Optional[Dict[str, float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TrainingResult:
        """Train algorithm on data."""
        values = [d["value"] for d in data]
        
        # Your training logic here
        baseline = {
            "param1": self._calculate_param1(values),
            "param2": self._calculate_param2(values),
            # ... your algorithm's learned parameters
        }
        
        return TrainingResult(
            baseline=baseline,
            data_points=len(values),
            sufficient_data=len(values) >= self.minimum_training_points,
        )
    
    def detect(
        self,
        value: float,
        baseline: Dict[str, Any],
        history: Optional[List[Dict[str, Any]]] = None,
        bucket_features: Optional[Dict[str, float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DetectionResult:
        """Detect if value is anomalous."""
        # Your detection logic here
        score = self._calculate_score(value, baseline)
        threshold = baseline.get("threshold", 3.0)
        is_anomaly = score > threshold
        
        return DetectionResult(
            is_anomaly=is_anomaly,
            algorithm_details={
                "score": score,
                "threshold": threshold,
                "param1": baseline["param1"],
                # ... include useful debugging info
            },
        )
    
    def format_anomaly_text(
        self,
        value: float,
        details: Dict[str, Any],
        bucket_key: Optional[str] = None,
    ) -> str:
        """Human-readable anomaly description."""
        score = details.get("score", 0)
        threshold = details.get("threshold", 0)
        return f"Anomaly: score {score:.2f} exceeds threshold {threshold:.2f}"
    
    # Your helper methods
    def _calculate_param1(self, values):
        ...
    
    def _calculate_param2(self, values):
        ...
    
    def _calculate_score(self, value, baseline):
        ...
```

### Step 2: Register Your Algorithm

Edit `MotorDA/algorithm_registry.py`:

```python
# Add import
from MotorDA.YourAlgorithm.algorithm import YourAlgorithm

# Add to registry
ALGORITHMS: Dict[str, BaseAlgorithm] = {
    "zscore": ZScoreAlgorithm(),
    "youralgorithm": YourAlgorithm(),  # Add this line
}
```

### Step 3: Rebuild and Test

```bash
# Rebuild dispatcher container
docker-compose build dispatcher
docker-compose up -d dispatcher

# Check logs
docker logs da-dispatcher
```

---

## Complete Example: IQR Algorithm

Here's a complete implementation of the Interquartile Range algorithm:

```python
"""IQR (Interquartile Range) Algorithm.

Detects anomalies using the 1.5*IQR rule:
- Lower bound: Q1 - 1.5 * IQR
- Upper bound: Q3 + 1.5 * IQR

Values outside these bounds are anomalies.
"""

import numpy as np
from typing import Any, Dict, List, Optional

from MotorDA.base_algorithm import (
    BaseAlgorithm,
    BucketMode,
    DetectionMode,
    DetectionResult,
    TrainingResult,
)


class IQRAlgorithm(BaseAlgorithm):
    """Interquartile Range anomaly detection."""
    
    name = "iqr"
    display_name = "Interquartile Range (IQR)"
    detection_mode = DetectionMode.POINT
    bucket_mode = BucketMode.SEGMENT
    
    @property
    def minimum_training_points(self) -> int:
        return 10  # Need enough for meaningful quartiles
    
    def train(
        self,
        data: List[Dict[str, Any]],
        bucket_key: Optional[str] = None,
        bucket_features: Optional[Dict[str, float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TrainingResult:
        """Calculate quartiles and IQR bounds."""
        values = np.array([d["value"] for d in data])
        
        q1 = float(np.percentile(values, 25))
        q3 = float(np.percentile(values, 75))
        iqr = q3 - q1
        
        # Get multiplier from metadata or use default
        multiplier = 1.5
        if metadata:
            multiplier = metadata.get("multiplier", 1.5)
        
        baseline = {
            "q1": q1,
            "q3": q3,
            "iqr": iqr,
            "multiplier": multiplier,
            "lower_bound": q1 - multiplier * iqr,
            "upper_bound": q3 + multiplier * iqr,
            "median": float(np.median(values)),
        }
        
        return TrainingResult(
            baseline=baseline,
            data_points=len(values),
            sufficient_data=len(values) >= self.minimum_training_points,
        )
    
    def detect(
        self,
        value: float,
        baseline: Dict[str, Any],
        history: Optional[List[Dict[str, Any]]] = None,
        bucket_features: Optional[Dict[str, float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DetectionResult:
        """Check if value is outside IQR bounds."""
        lower = baseline["lower_bound"]
        upper = baseline["upper_bound"]
        
        is_below = value < lower
        is_above = value > upper
        is_anomaly = is_below or is_above
        
        # Calculate how far outside the bounds
        if is_below:
            deviation = lower - value
            direction = "below"
        elif is_above:
            deviation = value - upper
            direction = "above"
        else:
            deviation = 0
            direction = "within"
        
        return DetectionResult(
            is_anomaly=is_anomaly,
            algorithm_details={
                "value": value,
                "lower_bound": lower,
                "upper_bound": upper,
                "q1": baseline["q1"],
                "q3": baseline["q3"],
                "iqr": baseline["iqr"],
                "median": baseline["median"],
                "deviation": deviation,
                "direction": direction,
            },
        )
    
    def format_anomaly_text(
        self,
        value: float,
        details: Dict[str, Any],
        bucket_key: Optional[str] = None,
    ) -> str:
        """Generate IQR-specific anomaly description."""
        direction = details.get("direction", "outside")
        deviation = details.get("deviation", 0)
        
        if direction == "below":
            bound = details["lower_bound"]
            return f"Value {value:.2f} is {deviation:.2f} below lower bound {bound:.2f}"
        else:
            bound = details["upper_bound"]
            return f"Value {value:.2f} is {deviation:.2f} above upper bound {bound:.2f}"
    
    def validate_config(self, metadata: Dict[str, Any]) -> List[str]:
        """Validate IQR configuration."""
        errors = []
        
        if metadata:
            multiplier = metadata.get("multiplier")
            if multiplier is not None:
                if not isinstance(multiplier, (int, float)):
                    errors.append("multiplier must be a number")
                elif multiplier <= 0:
                    errors.append("multiplier must be positive")
        
        return errors
```

---

## Bucket Mode Guide

### SEGMENT Mode (Default for Statistical Algorithms)

Use when you want different baselines for different time contexts:

```python
bucket_mode = BucketMode.SEGMENT

# Training is called once PER BUCKET:
# train(data=[...workday_09 data...], bucket_key="workday_09")
# train(data=[...weekend data...], bucket_key="weekend")

# Detection uses bucket-specific baseline:
# detect(value=100, baseline=workday_09_baseline)
```

### FEATURE Mode (For Time-Series Algorithms)

Use when bucket should be an input feature, not a data split:

```python
bucket_mode = BucketMode.FEATURE

# Training receives ALL data plus bucket features:
# train(data=[...all data...], bucket_features={"is_workday": 1, "hour": 9})

# Detection receives current bucket context:
# detect(value=100, baseline=model, bucket_features={"is_workday": 1, "hour": 14})
```

### METADATA_ONLY Mode

Use when algorithm doesn't benefit from time context:

```python
bucket_mode = BucketMode.METADATA_ONLY

# Training ignores buckets
# Detection ignores buckets
# Bucket is still attached to anomaly output for context
```

---

## Algorithm Details Output

Your `detect()` method should return useful information in `algorithm_details`:

```python
DetectionResult(
    is_anomaly=True,
    algorithm_details={
        # Always include these
        "value": value,
        "threshold": threshold,
        
        # Include algorithm-specific metrics
        "score": calculated_score,
        
        # Include training statistics used
        "baseline_data_points": baseline.get("data_points", 0),
        
        # Include any bounds or limits
        "lower_bound": baseline.get("lower_bound"),
        "upper_bound": baseline.get("upper_bound"),
        
        # Include helpful debugging info
        "deviation_from_expected": value - expected,
    }
)
```

This data appears in Elasticsearch anomaly documents under `algorithm_details`.

---

## Testing Your Algorithm

### Unit Tests

Create `MotorDA/YourAlgorithm/test_algorithm.py`:

```python
import pytest
from MotorDA.YourAlgorithm.algorithm import YourAlgorithm


class TestYourAlgorithm:
    
    def setup_method(self):
        self.algo = YourAlgorithm()
    
    def test_training_basic(self):
        data = [{"timestamp": f"2025-01-01T{i:02d}:00:00Z", "value": i * 10} 
                for i in range(20)]
        
        result = self.algo.train(data)
        
        assert result.sufficient_data
        assert result.data_points == 20
        assert "param1" in result.baseline
    
    def test_detection_normal(self):
        baseline = {"param1": 100, "threshold": 3.0}
        
        result = self.algo.detect(value=100, baseline=baseline)
        
        assert not result.is_anomaly
    
    def test_detection_anomaly(self):
        baseline = {"param1": 100, "threshold": 3.0}
        
        result = self.algo.detect(value=999, baseline=baseline)
        
        assert result.is_anomaly
        assert "score" in result.algorithm_details
```

### Integration Test

```bash
# 1. Create KB config with your algorithm via MCP
# (Use create_da_config tool)

# 2. Trigger training
docker logs -f da-dispatcher

# 3. Inject test data
docker exec mongodb mongosh -u admin -p '1q2w3E*' --authenticationDatabase admin --eval "
db = db.getSiblingDB('anomaly_detection');
db.series.insertOne({
  metadata: {kbId: '<your_kb_id>', dim: 'test_metric', mode: 1},
  timestamp: new Date(),
  value: 99999
})
"

# 4. Check for anomaly
curl 'http://localhost:9201/ds_anomalies_result/_search?pretty'
```

---

## Checklist

Before submitting your algorithm:

- [ ] Extends `BaseAlgorithm`
- [ ] Sets all required class attributes (`name`, `display_name`, `detection_mode`, `bucket_mode`)
- [ ] Implements `train()` returning `TrainingResult`
- [ ] Implements `detect()` returning `DetectionResult`
- [ ] Overrides `format_anomaly_text()` for meaningful messages
- [ ] Added to `algorithm_registry.py`
- [ ] Unit tests pass
- [ ] Integration test with real data works
- [ ] Docker container rebuilt

---

## Related Documents

- [Algorithm-Taxonomy.md](./Algorithm-Taxonomy.md) - Complete algorithm classification
- [Bucket-Compatibility-Guide.md](./Bucket-Compatibility-Guide.md) - Bucket usage modes
- [BaseAlgorithm Source](../MotorDA/base_algorithm.py) - Base class implementation
