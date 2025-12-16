# Algorithm Taxonomy for Anomaly Detection Framework

This document provides a comprehensive classification of anomaly detection algorithms, their detection modes, infrastructure requirements, and compatibility with the current ADF system.

## Overview

Anomaly detection algorithms can be classified into **6 main categories** based on their approach. Each category has different requirements for:

- **Detection Mode**: How the algorithm processes data (single value vs. time window)
- **Training Data**: What gets stored after training
- **Infrastructure**: What pipeline components are needed
- **Bucket Compatibility**: How time-context buckets can be used

---

## Detection Modes

| Mode | Description | Data Required | Current Support |
|------|-------------|---------------|-----------------|
| **POINT** | Each data point evaluated independently | Single value + baseline | ✅ Fully Supported |
| **SERIES** | Requires window of recent values | Current + N previous values | ❌ Needs HistoryProvider |
| **BATCH** | Processes many values at once | Batch of values | ❌ Needs Model Serving |

---

## Algorithm Categories

### Category 1: Statistical Algorithms

**Detection Mode:** POINT

Statistical algorithms compare individual values against learned distribution parameters.

| Algorithm | Description | Training Output | Detection Input |
|-----------|-------------|-----------------|-----------------|
| **Z-Score** | Standard deviations from mean | `{mean, std, threshold}` | Single value |
| **Modified Z-Score** | Uses median instead of mean (robust to outliers) | `{median, mad, threshold}` | Single value |
| **IQR** | Interquartile range method | `{q1, q3, iqr, lower, upper}` | Single value |
| **Grubbs Test** | Statistical test for single outlier | `{mean, std, critical_value}` | Single value |
| **Threshold** | Simple min/max bounds | `{min, max}` | Single value |

**Infrastructure Status:** ✅ **FULLY SUPPORTED**

**Implementation Complexity:** Low - Just implement `train()` and `detect()` methods.

```python
# Example: Z-Score detection
z_score = (value - baseline["mean"]) / baseline["std"]
is_anomaly = abs(z_score) > baseline["threshold"]
```

---

### Category 2: Density-Based Algorithms

**Detection Mode:** POINT (with caveats)

Density-based algorithms identify anomalies as points in low-density regions.

| Algorithm | Description | Training Output | Detection Input | Infrastructure Issue |
|-----------|-------------|-----------------|-----------------|---------------------|
| **Isolation Forest** | Random tree isolation | Tree structure | Single value | ⚠️ Need to store tree |
| **LOF (Local Outlier Factor)** | Compare local density to neighbors | All training points | Single value | ❌ Need all points at detection |
| **k-NN Outlier** | Distance to k-th neighbor | All training points | Single value | ❌ Need all points at detection |

**Infrastructure Status:** ⚠️ **PARTIAL SUPPORT**

**Isolation Forest:** Can work - store serialized tree in `series_result`

**LOF/k-NN:** Problematic - requires storing all training data points, not just statistics

**Implementation Complexity:** Medium

```python
# Isolation Forest: Store model, load for detection
from sklearn.ensemble import IsolationForest

# Training
model = IsolationForest().fit(training_data)
baseline = {"model": serialize(model)}

# Detection  
model = deserialize(baseline["model"])
is_anomaly = model.predict([[value]])[0] == -1
```

---

### Category 3: Clustering Algorithms

**Detection Mode:** POINT

Clustering algorithms identify anomalies as points far from cluster centers.

| Algorithm | Description | Training Output | Detection Input |
|-----------|-------------|-----------------|-----------------|
| **K-Means** | Distance to nearest centroid | `{centroids, threshold}` | Single value |
| **DBSCAN** | Core/border/noise classification | All training points | Single value |

**Infrastructure Status:** ⚠️ **PARTIAL SUPPORT**

**K-Means:** ✅ Works - store centroids, compute distance at detection

**DBSCAN:** ❌ Problematic - needs all points for density computation

**Implementation Complexity:** Low (K-Means), High (DBSCAN)

```python
# K-Means detection
import numpy as np

centroids = np.array(baseline["centroids"])
distances = np.linalg.norm(centroids - value, axis=1)
min_distance = distances.min()
is_anomaly = min_distance > baseline["threshold"]
```

---

### Category 4: Time-Series Algorithms

**Detection Mode:** SERIES

Time-series algorithms predict future values based on historical patterns and flag deviations.

| Algorithm | Description | Training Output | Detection Input | History Needed |
|-----------|-------------|-----------------|-----------------|----------------|
| **ARMA/ARIMA** | Autoregressive moving average | AR/MA coefficients | Last p+q values | p + q values |
| **ARMAX** | ARMA with exogenous variables | Coefficients + feature weights | History + features | p + q values |
| **Prophet** | Trend + seasonality decomposition | Trend/seasonal params | Full history preferred | Variable |
| **Exponential Smoothing** | Weighted moving average | Smoothing parameters | Last N values | N values |

**Infrastructure Status:** ❌ **NOT SUPPORTED**

**Missing Components:**
1. `HistoryProvider` - Fetch recent N values at detection time
2. Continuous training - Don't split by bucket (breaks time series)
3. Feature injection - Pass bucket as exogenous variable

**Implementation Complexity:** High

```python
# ARMA detection (requires history)
def detect_arma(value, baseline, history):
    # Predict next value from history
    ar_params = baseline["ar_params"]
    predicted = sum(ar * h for ar, h in zip(ar_params, history))
    
    # Check residual
    residual = abs(value - predicted)
    threshold = baseline["residual_std"] * 3
    is_anomaly = residual > threshold
    
    return is_anomaly, {"predicted": predicted, "residual": residual}
```

---

### Category 5: Neural Network Algorithms

**Detection Mode:** SERIES or BATCH

Neural networks learn complex patterns for anomaly detection.

| Algorithm | Description | Training Output | Detection Input | Infrastructure |
|-----------|-------------|-----------------|-----------------|----------------|
| **LSTM** | Recurrent network prediction | Model weights | Sequence window | Model serving |
| **Autoencoder** | Reconstruction error | Model weights | Value/vector | Model serving |
| **Variational Autoencoder** | Probabilistic reconstruction | Model weights | Value/vector | Model serving |
| **CNN (for sequences)** | Convolutional pattern matching | Model weights | Sequence window | Model serving |

**Infrastructure Status:** ❌ **NOT SUPPORTED**

**Missing Components:**
1. Model storage (S3/MinIO/GridFS for model weights)
2. Model serving (TensorFlow Serving, TorchServe, or ONNX Runtime)
3. GPU support (optional but recommended)
4. Batch inference pipeline

**Implementation Complexity:** Very High

```python
# LSTM detection (requires model serving infrastructure)
def detect_lstm(sequence, model_endpoint):
    # Call model serving endpoint
    response = requests.post(model_endpoint, json={"sequence": sequence})
    prediction = response.json()["prediction"]
    
    # Actual value is last in sequence
    actual = sequence[-1]
    error = abs(actual - prediction)
    threshold = response.json()["threshold"]
    
    return error > threshold
```

---

### Category 6: Ensemble Algorithms

**Detection Mode:** META (combines other algorithms)

Ensemble methods combine multiple algorithms for more robust detection.

| Algorithm | Description | Component Algorithms | Combination Method |
|-----------|-------------|---------------------|-------------------|
| **Voting** | Majority vote | Any POINT algorithms | Count votes |
| **Averaging** | Average anomaly scores | Algorithms with scores | Mean/weighted mean |
| **Stacking** | Meta-model on outputs | Any algorithms | Trained combiner |

**Infrastructure Status:** ❌ **NOT SUPPORTED**

**Missing Components:**
1. Multi-algorithm execution pipeline
2. Score normalization across algorithms
3. Meta-model training (for stacking)

**Implementation Complexity:** Medium to High

---

## Summary Matrix

| Category | Examples | Mode | Current Support | Effort to Add |
|----------|----------|------|-----------------|---------------|
| **Statistical** | Z-Score, IQR, Threshold | POINT | ✅ Full | Low |
| **Density** | Isolation Forest, LOF | POINT+ | ⚠️ Partial | Medium |
| **Clustering** | K-Means, DBSCAN | POINT | ⚠️ Partial | Medium |
| **Time-Series** | ARMA, Prophet | SERIES | ❌ None | High |
| **Neural Network** | LSTM, Autoencoder | SERIES/BATCH | ❌ None | Very High |
| **Ensemble** | Voting, Stacking | META | ❌ None | High |

---

## Implementation Phases

### Phase 1: Point Algorithms (Current)
- ✅ Z-Score (implemented)
- ✅ IQR
- ⬜ Modified Z-Score
- ⬜ Threshold
- ✅ K-Means

### Phase 2: Series Algorithms (Requires HistoryProvider)
- ⬜ Add `HistoryProvider` to fetch recent values
- ⬜ Add `SeriesOrchestrator` (no bucket splitting)
- ⬜ ARMA/ARIMA
- ⬜ ARMAX (with bucket as feature)
- ⬜ Exponential Smoothing

### Phase 3: Neural Networks (Requires Model Serving)
- ⬜ Add model storage (GridFS or S3)
- ⬜ Add model serving container
- ⬜ LSTM
- ⬜ Autoencoder

### Phase 4: Advanced Features
- ⬜ Ensemble methods
- ⬜ Online learning (model updates with new data)
- ⬜ Explainable anomaly detection

---

## Related Documents

- [Bucket-Compatibility-Guide.md](./Bucket-Compatibility-Guide.md) - How buckets work with each algorithm type
- [Adding-Point-Algorithms.md](./How-To-Add-New-Algorithm.md) - Step-by-step guide for POINT algorithms
- [Phase-2-HistoryProvider.md](./Phase-2-HistoryProvider.md) - Infrastructure for SERIES algorithms (future)

---

## References

- [Wikipedia: Anomaly Detection](https://en.wikipedia.org/wiki/Anomaly_detection)
- [PyOD: Python Outlier Detection Library](https://pyod.readthedocs.io/)
- [scikit-learn: Outlier Detection](https://scikit-learn.org/stable/modules/outlier_detection.html)
