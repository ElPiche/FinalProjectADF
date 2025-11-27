# Bucket Compatibility Guide

This document explains how time-context buckets interact with different anomaly detection algorithms and provides guidance on which bucket mode to use for each algorithm type.

## Overview

The ADF bucket system provides **time-context awareness** for anomaly detection. A value that's normal at 3 AM might be anomalous at 3 PM. Buckets capture this context.

However, **not all algorithms can use buckets the same way**. This guide explains the three bucket usage modes and which algorithms are compatible with each.

---

## Bucket Usage Modes

### Mode 1: Bucket as Training Segment

**How it works:**
1. Training data is split by bucket key
2. A separate model/baseline is trained per bucket
3. At detection, resolve the bucket and use that bucket's model

```
Training Data                    Bucketed Training
┌──────────────────────────┐     ┌────────────────────────────────────┐
│ 09:00  value=100         │     │ workday_09: mean=95, std=10        │
│ 09:15  value=90          │────▶│ workday_10: mean=150, std=20       │
│ 10:00  value=150         │     │ weekend:    mean=50, std=5         │
│ Saturday 09:00 value=50  │     └────────────────────────────────────┘
└──────────────────────────┘

Detection:
  Value: 200 at Monday 09:30
  Bucket: workday_09
  Baseline: {mean: 95, std: 10}
  Result: Anomaly! (uses correct time-context baseline)
```

**✅ Best for:** Algorithms that compute independent statistics per group
- Z-Score, IQR, Modified Z-Score, Threshold
- K-Means (if enough data per bucket)
- Isolation Forest (if enough data per bucket)

**❌ Bad for:** Algorithms that need temporal continuity
- ARMA, Prophet, LSTM (splitting breaks the time series!)

---

### Mode 2: Bucket as Feature (Exogenous Variable)

**How it works:**
1. Training data stays as one continuous series
2. Bucket key is added as an input feature/column
3. Algorithm learns relationship between bucket and values

```
Training Data (preserved order, bucket added as feature)
┌──────┬───────┬─────────────┬────────────┬──────┐
│ time │ value │ bucket_key  │ is_workday │ hour │
├──────┼───────┼─────────────┼────────────┼──────┤
│ t1   │ 100   │ workday_09  │ 1          │ 9    │
│ t2   │ 102   │ workday_09  │ 1          │ 9    │
│ t3   │ 105   │ workday_10  │ 1          │ 10   │
│ t4   │ 50    │ weekend     │ 0          │ 9    │
└──────┴───────┴─────────────┴────────────┴──────┘

Model learns:
- Temporal patterns (from time order)
- "Weekdays have higher values" (from is_workday feature)
- "Hour 10 > Hour 9" (from hour feature)
```

**✅ Best for:** Algorithms that model temporal dependencies
- ARMAX (the X means eXogenous variables!)
- Prophet (has built-in holiday/regressor support)
- LSTM (bucket becomes part of input feature vector)
- Autoencoder (bucket in feature encoding)

**⚠️ Possible for:** Clustering (bucket as extra dimension)

**❌ Not applicable:** Simple statistical (Z-Score doesn't use features)

---

### Mode 3: Bucket as Output Metadata Only

**How it works:**
1. Training ignores buckets entirely
2. Detection ignores buckets entirely  
3. When anomaly is reported, attach bucket for context

```
Anomaly Document
{
  "algorithm": "ARMA",
  "metric": "response_time",
  "value": 500,
  "is_anomaly": true,
  "timestamp": "2025-01-15T09:30:00Z",
  
  // Bucket is just metadata - not used in detection
  "bucket_key": "workday_09",
  "bucket_profile_id": "business_hours_v1"
}
```

**✅ Best for:** ALL algorithms (no algorithm changes needed)

This mode is **always available** and **already implemented** in our anomaly output.

---

## Compatibility Matrix

| Algorithm | Segment Mode | Feature Mode | Metadata Mode | Recommended |
|-----------|:------------:|:------------:|:-------------:|-------------|
| **Z-Score** | ✅ Ideal | ❌ N/A | ✅ Always | **Segment** |
| **Modified Z-Score** | ✅ Ideal | ❌ N/A | ✅ Always | **Segment** |
| **IQR** | ✅ Ideal | ❌ N/A | ✅ Always | **Segment** |
| **Threshold** | ⚠️ Optional | ❌ N/A | ✅ Always | **Segment** or None |
| **K-Means** | ⚠️ If enough data | ⚠️ Possible | ✅ Always | **Segment** (coarse buckets) |
| **Isolation Forest** | ⚠️ If enough data | ⚠️ Possible | ✅ Always | **None** or Segment |
| **LOF** | ❌ Splits data | ⚠️ Possible | ✅ Always | **Feature** or None |
| **ARMA** | ❌ Breaks series | ❌ N/A | ✅ Always | **Metadata only** |
| **ARMAX** | ❌ Breaks series | ✅ **Ideal** | ✅ Always | **Feature** |
| **Prophet** | ❌ Breaks series | ✅ Built-in | ✅ Always | **Feature** |
| **LSTM** | ❌ Breaks series | ✅ Good | ✅ Always | **Feature** |
| **Autoencoder** | ⚠️ Possible | ✅ Good | ✅ Always | **Feature** |

---

## Why Segmentation Breaks Time-Series Algorithms

### The Problem

Time-series algorithms like ARMA predict `y(t)` based on `y(t-1), y(t-2), ...`

When you segment by bucket, you destroy the temporal order:

```
Original Time Series (ARMA can learn this):
t1 → t2 → t3 → t4 → t5 → t6 → t7 → t8
[100, 102, 105, 103, 50, 52, 55, 53]
     └─ ARMA learns: "next value ≈ previous + small δ"

Segmented by Bucket (BROKEN!):
workday_09: [100, 102, 50, 52]   ← Values from different times jumbled!
workday_10: [105, 103, 55, 53]   ← ARMA sees: 105 → 103 → 55 (wrong!)
```

### The Solution: Bucket as Feature

Keep the series intact, add bucket information as a column:

```
Preserved Series with Bucket Feature:
t  | value | is_workday | hour
---|-------|------------|-----
t1 | 100   | 1          | 9
t2 | 102   | 1          | 9
t3 | 105   | 1          | 10
t4 | 103   | 1          | 10
t5 | 50    | 0          | 9   ← Weekend starts
t6 | 52    | 0          | 9
t7 | 55    | 0          | 10
t8 | 53    | 0          | 10

ARMAX can now learn:
- Temporal pattern: "next ≈ previous + δ"
- Weekend effect: "values drop by ~50 on weekends"
```

---

## Trade-offs: Segment vs No Buckets

### More Buckets = Less Data Per Bucket

```
1000 training points total

No buckets:           1000 points → Robust statistics
2 buckets:            500 points each → Still good
10 buckets:           100 points each → Getting thin
48 buckets (hourly):  ~21 points each → May be insufficient!
```

### Recommendation: Use Coarse Buckets

| Granularity | Example Keys | Points per Bucket (1 month data) |
|-------------|--------------|----------------------------------|
| **Coarse** | workday, weekend | ~500+ | ✅ Recommended |
| **Medium** | workday_morning, workday_afternoon, weekend | ~200+ | ✅ Good |
| **Fine** | workday_09, workday_10, ... (hourly) | ~30 | ⚠️ Marginal |
| **Very Fine** | workday_09_mon, workday_09_tue, ... | ~5 | ❌ Too few |

---

## Bucket Feature Encoding

For algorithms that use bucket as a feature, you need to encode the bucket key:

### One-Hot Encoding
```python
# For small number of buckets
bucket_features = {
    "is_workday": 1 if bucket.startswith("workday") else 0,
    "is_weekend": 1 if bucket.startswith("weekend") else 0,
    "is_holiday": 1 if bucket.startswith("holiday") else 0,
}
```

### Numeric Encoding
```python
# Extract hour from bucket key
if "_" in bucket_key:
    parts = bucket_key.split("_")
    hour = int(parts[-1]) if parts[-1].isdigit() else 0
else:
    hour = 0

bucket_features = {
    "is_workday": 1 if bucket.startswith("workday") else 0,
    "hour": hour,
    "hour_sin": np.sin(2 * np.pi * hour / 24),  # Cyclical encoding
    "hour_cos": np.cos(2 * np.pi * hour / 24),
}
```

### Embedding (for Neural Networks)
```python
# Let the model learn bucket representations
bucket_embedding = nn.Embedding(num_buckets, embedding_dim)
bucket_vector = bucket_embedding(bucket_id)
```

---

## Implementation in BaseAlgorithm

The base algorithm class supports bucket mode declaration:

```python
from enum import Enum
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple

class BucketMode(Enum):
    SEGMENT = "segment"      # Train separate model per bucket
    FEATURE = "feature"      # Use bucket as input feature
    METADATA_ONLY = "none"   # Bucket only in output, not used in algorithm

class DetectionMode(Enum):
    POINT = "point"    # Single value input
    SERIES = "series"  # Needs history window

class BaseAlgorithm(ABC):
    """Base class for anomaly detection algorithms."""
    
    # Algorithm metadata - override in subclasses
    name: str
    display_name: str
    detection_mode: DetectionMode
    bucket_mode: BucketMode
    
    @property
    def required_history_length(self) -> int:
        """Number of historical values needed (0 for POINT mode)."""
        return 0
    
    @abstractmethod
    def train(
        self,
        data: List[Dict[str, Any]],  # [{timestamp, value, ...}]
        bucket_key: Optional[str] = None,  # For SEGMENT mode
        bucket_features: Optional[Dict[str, float]] = None,  # For FEATURE mode
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Train algorithm and return baseline/model."""
        pass
    
    @abstractmethod
    def detect(
        self,
        value: float,
        baseline: Dict[str, Any],
        history: Optional[List[Dict]] = None,  # For SERIES mode
        bucket_features: Optional[Dict[str, float]] = None,  # For FEATURE mode
        metadata: Optional[Dict] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """Detect anomaly. Returns (is_anomaly, algorithm_details)."""
        pass
    
    def format_anomaly_text(self, value: float, details: Dict) -> str:
        """Generate human-readable anomaly description."""
        return f"Anomaly detected by {self.display_name}"
```

---

## Examples

### Z-Score (Bucket as Segment)

```python
class ZScoreAlgorithm(BaseAlgorithm):
    name = "zscore"
    display_name = "Z-Score (Bucketed)"
    detection_mode = DetectionMode.POINT
    bucket_mode = BucketMode.SEGMENT  # ← Separate baseline per bucket
    
    def train(self, data, bucket_key=None, **kwargs):
        values = [d["value"] for d in data]
        return {
            "mean": statistics.mean(values),
            "std": statistics.stdev(values) if len(values) > 1 else 0,
            "threshold": np.percentile(values, 99.5),
            "data_points": len(values),
        }
    
    def detect(self, value, baseline, **kwargs):
        mean, std = baseline["mean"], baseline["std"]
        z_score = (value - mean) / std if std > 0 else 0
        is_anomaly = abs(z_score) > baseline["threshold"]
        
        return is_anomaly, {
            "z_score": z_score,
            "threshold": baseline["threshold"],
            "mean": mean,
            "std": std,
        }
```

### ARMAX (Bucket as Feature)

```python
class ARMAXAlgorithm(BaseAlgorithm):
    name = "armax"
    display_name = "ARMAX Time Series"
    detection_mode = DetectionMode.SERIES
    bucket_mode = BucketMode.FEATURE  # ← Bucket is input feature
    
    @property
    def required_history_length(self) -> int:
        return 10  # Need last 10 values
    
    def train(self, data, bucket_features=None, metadata=None, **kwargs):
        # Data stays continuous, bucket_features are exogenous variables
        from statsmodels.tsa.arima.model import ARIMA
        
        values = [d["value"] for d in data]
        # If bucket features available, use as exogenous
        exog = self._extract_exog(data) if bucket_features else None
        
        model = ARIMA(values, order=(2, 0, 2), exog=exog)
        fitted = model.fit()
        
        return {
            "ar_params": fitted.arparams.tolist(),
            "ma_params": fitted.maparams.tolist(),
            "exog_params": fitted.params[-len(exog[0]):].tolist() if exog else [],
            "residual_std": float(fitted.resid.std()),
        }
    
    def detect(self, value, baseline, history=None, bucket_features=None, **kwargs):
        if not history or len(history) < self.required_history_length:
            return False, {"error": "insufficient_history"}
        
        # Predict using AR terms and exogenous features
        ar_params = baseline["ar_params"]
        recent = [h["value"] for h in history[-len(ar_params):]]
        predicted = sum(ar * v for ar, v in zip(ar_params, reversed(recent)))
        
        # Add exogenous contribution if bucket features provided
        if bucket_features and baseline.get("exog_params"):
            for param, (key, val) in zip(baseline["exog_params"], bucket_features.items()):
                predicted += param * val
        
        residual = abs(value - predicted)
        threshold = baseline["residual_std"] * 3
        is_anomaly = residual > threshold
        
        return is_anomaly, {
            "predicted": predicted,
            "residual": residual,
            "threshold": threshold,
        }
```

---

## Current Infrastructure Support

| Bucket Mode | TrainingOrchestrator | DADispatcher | Status |
|-------------|---------------------|--------------|--------|
| **Segment** | ✅ `group_by_bucket()` | ✅ Bucket lookup | Implemented |
| **Feature** | ❌ Not implemented | ❌ Not implemented | Phase 2 |
| **Metadata** | ✅ Stored in result | ✅ In anomaly output | Implemented |

### Phase 2 Changes Needed for Feature Mode

1. **TrainingOrchestrator**: Add `prepare_with_features()` method
   - Keep data continuous
   - Add bucket columns (is_workday, hour, etc.)

2. **DADispatcher**: Pass bucket features to detect()
   - Resolve bucket key (already done)
   - Convert to feature dict
   - Pass to algorithm

3. **HistoryProvider**: Fetch recent values for SERIES algorithms
   - Query MongoDB for last N values
   - Return with bucket info for each

---

## Decision Guide

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Which bucket mode should I use for my algorithm?                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Does your algorithm need temporal order of data?                            │
│  │                                                                           │
│  ├─► NO  → Does it compute statistics (mean, std, quantiles)?               │
│  │         │                                                                 │
│  │         ├─► YES → Use SEGMENT mode (Z-Score, IQR)                        │
│  │         │                                                                 │
│  │         └─► NO  → Does it need all training points at detection?         │
│  │                   │                                                       │
│  │                   ├─► YES → Use METADATA_ONLY (LOF, k-NN)                │
│  │                   │                                                       │
│  │                   └─► NO  → Use SEGMENT if enough data (K-Means)         │
│  │                                                                           │
│  └─► YES → Does it support exogenous variables?                             │
│            │                                                                 │
│            ├─► YES → Use FEATURE mode (ARMAX, Prophet, LSTM)                │
│            │                                                                 │
│            └─► NO  → Use METADATA_ONLY (ARMA)                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Related Documents

- [Algorithm-Taxonomy.md](./Algorithm-Taxonomy.md) - Complete algorithm classification
- [How-To-Add-New-Algorithm.md](./How-To-Add-New-Algorithm.md) - Implementation guide for POINT algorithms
