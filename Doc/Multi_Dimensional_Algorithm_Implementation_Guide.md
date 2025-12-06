# Multi-Dimensional Algorithm Implementation Guide

> **Created**: December 2, 2025  
> **Branch**: `feature/fix-train-orchestrator`  
> **Status**: Design Complete - Ready for Implementation  
> **Reference**: `Doc/TODO_Implementation_Plan.md` Parts 5-8

## Executive Summary

This document provides the implementation specification for supporting **multi-dimensional algorithms** (like KMeans) alongside existing **single-dimensional algorithms** (ZScore, IQR). It covers:

1. Algorithm Interface changes
2. Orchestrator modifications  
3. Dispatcher control flow
4. Metadata handling
5. Bucketing system (modeling vs context)
6. Multi-worker architecture
7. Per-KB worker with dedicated change streams
8. Observation buffering for multi-dimensional detection

---

## 1. Terminology

| Term | Definition | Examples |
|------|------------|----------|
| **Single-Dimensional** | Processes each dimension independently. Each dimension has its own baseline. | ZScore, IQR |
| **Multi-Dimensional** | Processes all dimensions together as vectors. Single model for all dimensions. | KMeans, DBSCAN, Isolation Forest |

---

## 2. Algorithm Interface

### 2.1 Required Properties

Every algorithm MUST implement:

```python
@property
def name(self) -> str:
    """Algorithm identifier (e.g., 'zscore', 'kmeans')."""
    ...

@property
def is_multi_dimensional(self) -> bool:
    """True if algorithm processes all dimensions together."""
    ...
```

### 2.2 Required Methods (Based on Mode)

**If `is_multi_dimensional = False`:**
```python
def train(self, values: List[float], parameter: Dict = None, **kwargs) -> Dict[str, Any]:
    """Train baseline from single-dimension values.
    
    Args:
        values: List of numeric values for ONE dimension
        parameter: Full parameter dict (contains metadata for this dimension)
    
    Returns:
        Baseline dict (algorithm-specific structure)
    """
    ...

def detect(self, value: float, baseline: Dict[str, Any], parameter: Dict = None) -> Dict[str, Any]:
    """Detect if a single value is anomalous.
    
    Returns:
        Must include 'is_anomaly': bool
    """
    ...
```

**If `is_multi_dimensional = True`:**
```python
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
    
    Returns:
        Must include 'is_anomaly': bool
    """
    ...
```

### 2.3 Optional Methods

**For algorithms supporting BOTH modes (checked via `hasattr()`):**
```python
def resolve_multi_dimensional(self, parameters: List[Dict]) -> bool:
    """Dynamically resolve mode based on parameters/metadata.
    
    If present, algorithm MUST implement ALL four core methods.
    """
    ...
```

**For batch optimization (optional for any algorithm):**
```python
def detect_batch(self, values: List[float], baseline: Dict) -> List[Dict]:
    """Batch detection for single-dimensional."""
    ...

def detect_batch_multi_dimensional(
    self, 
    observations: List[Dict], 
    model: Dict, 
    parameters: List[Dict]
) -> List[Dict]:
    """Batch detection for multi-dimensional."""
    ...
```

### 2.4 Method Requirements Matrix

| `is_multi_dimensional` | Has `resolve_multi_dimensional` | Required Methods |
|------------------------|--------------------------------|------------------|
| `False` | No | `train`, `detect` |
| `True` | No | `train_multi_dimensional`, `detect_multi_dimensional` |
| Either | Yes | ALL four core methods |

---

## 3. Registration Validation (Fail-Fast)

Update `algorithm_interface.py`:

```python
def register_algorithm(cls: Type) -> Type:
    """Decorator to auto-register an algorithm with validation."""
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
    ALGORITHM_REGISTRY[name] = instance
    logger.info(f"Registered algorithm: {name} (multi_dimensional={is_multi_dim})")
    
    _export_registry_if_available()
    return cls
```

---

## 4. Metadata Handling

### 4.1 Core Principle: Algorithm Reads Its Own Metadata

**Orchestrator does NOT extract algorithm-specific parameters.**

```python
# ❌ WRONG - Orchestrator should NOT know about "percentile"
def _train_single_dimensional(self, algorithm, observations, percentile):
    baseline = algorithm.train(values, percentile=percentile)

# ✅ CORRECT - Orchestrator passes parameter, algorithm extracts what it needs
def _train_single_dimensional(self, algorithm, observations) -> Dict:
    result = {}
    for param in self.parameters:
        if not param.get("is_active", True):
            continue
        dimension = param["dimension"]
        values = [obs[dimension] for obs in observations if obs.get(dimension) is not None]
        if len(values) >= 3:
            result[dimension] = algorithm.train(values, parameter=param)
    return result
```

### 4.2 Algorithm Extracts Its Metadata

```python
# zscore.py
def train(self, values: List[float], parameter: Dict = None, **kwargs) -> Dict:
    percentile = 99.5  # Default
    if parameter:
        meta_list = parameter.get("metadata") or parameter.get("algorithm_metadata", [])
        for meta in meta_list:
            if meta.get("key") == "percentile":
                percentile = float(meta.get("value", 99.5))
    # Use percentile in training...

# iqr.py  
def train(self, values: List[float], parameter: Dict = None, **kwargs) -> Dict:
    multiplier = 1.5  # Default
    if parameter:
        meta_list = parameter.get("metadata") or parameter.get("algorithm_metadata", [])
        for meta in meta_list:
            if meta.get("key") == "multiplier":
                multiplier = float(meta.get("value", 1.5))
    # Use multiplier in training...
```

### 4.3 Metadata Field Name Varies by Source

| Data Flow | Source Collection | Field Name |
|-----------|-------------------|------------|
| Training | `anomaly_detection.training_config` | `algorithm_metadata` |
| Detection | `knowledge_base.kb_configs` | `metadata` |

**Always check both:**
```python
meta_list = param.get("metadata") or param.get("algorithm_metadata", [])
```

---

## 5. Dispatcher Changes

### 5.1 Mode Must Be Known at Dispatcher Level

The Dispatcher decides **loop vs batch** control flow BEFORE calling orchestrator.

**File:** `DADispatcher.py`

```python
def detect_anomaly(config_id: str, serie_to_detect: Dict) -> Optional[Dict]:
    # ... existing config loading ...
    
    # Resolve mode ONCE at dispatcher level
    algorithm = get_algorithm(alg_name)
    
    if hasattr(algorithm, 'resolve_multi_dimensional'):
        is_multi_dim = algorithm.resolve_multi_dimensional(alg_params)
    else:
        is_multi_dim = algorithm.is_multi_dimensional
    
    # Create orchestrator with mode
    orchestrator = DetectionOrchestrator(
        algorithm_name=alg_name,
        parameters=alg_params,
        bucket_profile=bucket_profile,
        training_result=training_result,
        is_multi_dimensional=is_multi_dim  # NEW
    )
    
    # Control flow depends on mode
    if is_multi_dim:
        # Multi-dimensional: pass ALL observations at once
        results = orchestrator.detect_batch_multi_dimensional(
            observations=observed_values,
            timestamp_field=timestamp_field
        )
        anomalies = [{"observation": r["observation"], "detection_result": r} 
                     for r in results if r.get("is_anomaly")]
    else:
        # Single-dimensional: loop through observations
        anomalies = []
        for obs in observed_values:
            result = orchestrator.detect(observation=obs, timestamp_field=timestamp_field)
            if result.get("is_anomaly"):
                anomalies.append({"observation": obs, "detection_result": result})
    
    # ... rest of function ...
```

**Same pattern for `run_training()`:**
```python
def run_training(config_id: str, observed_values: List[Dict], ...):
    # ... existing config loading ...
    
    algorithm = get_algorithm(alg_name)
    
    if hasattr(algorithm, 'resolve_multi_dimensional'):
        is_multi_dim = algorithm.resolve_multi_dimensional(alg_params)
    else:
        is_multi_dim = algorithm.is_multi_dimensional
    
    orchestrator = TrainingOrchestrator(
        algorithm_name=alg_name,
        parameters=alg_params,
        bucket_profile=bucket_profile,
        is_multi_dimensional=is_multi_dim  # NEW
    )
    
    result = orchestrator.train(
        observations=observed_values,
        timestamp_field=timestamp_field
    )
    # ...
```

---

## 6. Orchestrator Changes

### 6.1 TrainingOrchestrator Updates

**File:** `training_orchestrator.py`

```python
@dataclass
class TrainingOrchestrator:
    algorithm_name: str
    parameters: List[Dict[str, Any]]
    bucket_profile: Optional[Dict[str, Any]] = None
    is_multi_dimensional: bool = False  # NEW - passed from Dispatcher
    bucket_resolver: Optional[BucketResolver] = field(default=None, init=False)
    
    def __post_init__(self):
        if self.bucket_profile:
            self.bucket_resolver = BucketResolver.from_dict(self.bucket_profile)
    
    def train(self, observations: List[Dict], timestamp_field: str) -> Dict:
        algorithm = get_algorithm(self.algorithm_name)
        groups = self.group_by_bucket(observations, timestamp_field)
        
        # Global fallback
        if self.is_multi_dimensional:
            global_fallback = algorithm.train_multi_dimensional(
                observations=observations,
                parameters=self.parameters
            )
        else:
            global_fallback = self._train_single_dimensional(algorithm, observations)
        
        # Per-bucket baselines
        buckets = {}
        for bucket_key, bucket_obs in groups.items():
            if len(bucket_obs) < 3:
                buckets[bucket_key] = {
                    "baselines": global_fallback,
                    "n_observations": len(bucket_obs),
                    "sufficient_data": False
                }
            else:
                if self.is_multi_dimensional:
                    baseline = algorithm.train_multi_dimensional(
                        observations=bucket_obs,
                        parameters=self.parameters
                    )
                else:
                    baseline = self._train_single_dimensional(algorithm, bucket_obs)
                
                buckets[bucket_key] = {
                    "baselines": baseline,
                    "n_observations": len(bucket_obs),
                    "sufficient_data": True
                }
        
        return {
            "algorithm": self.algorithm_name,
            "is_multi_dimensional": self.is_multi_dimensional,
            "bucket_profile_id": self.bucket_profile.get("profile_id") if self.bucket_profile else None,
            "buckets": buckets,
            "global_fallback": global_fallback,
            "n_total_observations": len(observations),
            "parameters": self.parameters
        }
    
    def _train_single_dimensional(self, algorithm, observations: List[Dict]) -> Dict:
        """Train each dimension independently. Algorithm reads its own metadata."""
        result = {}
        for param in self.parameters:
            if not param.get("is_active", True):
                continue
            dimension = param["dimension"]
            values = [obs[dimension] for obs in observations if obs.get(dimension) is not None]
            if len(values) >= 3:
                result[dimension] = algorithm.train(values, parameter=param)
        return result
```

### 6.2 DetectionOrchestrator Updates

```python
@dataclass
class DetectionOrchestrator:
    algorithm_name: str
    parameters: List[Dict[str, Any]]
    training_result: Dict[str, Any]
    bucket_profile: Optional[Dict[str, Any]] = None
    is_multi_dimensional: bool = False  # NEW
    bucket_resolver: Optional[BucketResolver] = field(default=None, init=False)
    
    def detect(self, observation: Dict, timestamp_field: str) -> Dict:
        """Detect single observation (single-dimensional mode)."""
        algorithm = get_algorithm(self.algorithm_name)
        
        ts = parse_timestamp(observation.get(timestamp_field))
        bucket_key = self.resolve_bucket_key(ts) if ts else "global_default"
        baselines = self.get_baseline_for_bucket(bucket_key)
        
        # Single-dimensional: detect per dimension
        result = self._detect_single_dimensional(algorithm, observation, baselines)
        result["bucket_key"] = bucket_key
        result["timestamp"] = ts.isoformat() if ts else None
        return result
    
    def _detect_single_dimensional(self, algorithm, observation: Dict, baselines: Dict) -> Dict:
        """Detect each dimension independently. Algorithm reads its own metadata."""
        dimension_results = {}
        is_anomaly = False
        
        for param in self.parameters:
            if not param.get("is_active", True):
                continue
            dimension = param["dimension"]
            value = observation.get(dimension)
            baseline = baselines.get(dimension)
            
            if value is not None and baseline is not None:
                result = algorithm.detect(value, baseline, parameter=param)
                dimension_results[dimension] = result
                if result.get("is_anomaly"):
                    is_anomaly = True
        
        return {"is_anomaly": is_anomaly, "dimension_results": dimension_results}
    
    def detect_batch_multi_dimensional(
        self, 
        observations: List[Dict], 
        timestamp_field: str
    ) -> List[Dict]:
        """Detect batch of observations (multi-dimensional mode)."""
        algorithm = get_algorithm(self.algorithm_name)
        results = []
        
        # Group by bucket for proper baseline lookup
        groups = self._group_by_bucket_for_detection(observations, timestamp_field)
        
        for bucket_key, bucket_obs in groups.items():
            model = self.get_baseline_for_bucket(bucket_key)
            
            # Check if algorithm has optimized batch method
            if hasattr(algorithm, 'detect_batch_multi_dimensional'):
                batch_results = algorithm.detect_batch_multi_dimensional(
                    observations=bucket_obs,
                    model=model,
                    parameters=self.parameters
                )
            else:
                # Fallback: call detect_multi_dimensional for each
                batch_results = []
                for obs in bucket_obs:
                    result = algorithm.detect_multi_dimensional(obs, model, self.parameters)
                    result["observation"] = obs
                    batch_results.append(result)
            
            for r in batch_results:
                r["bucket_key"] = bucket_key
            results.extend(batch_results)
        
        return results
```

---

## 7. Data Preparation Summary

### 7.1 Who Does What

| Responsibility | Single-Dimensional | Multi-Dimensional |
|----------------|-------------------|-------------------|
| Group by bucket | Orchestrator | Orchestrator |
| Extract dimension values | Orchestrator (per-dim loop) | Algorithm (internally) |
| Filter `is_active` | Orchestrator (per-dim) | Algorithm (from parameters) |
| Read metadata (percentile, etc.) | Algorithm | Algorithm |
| Call method | `algorithm.train(values, parameter)` | `algorithm.train_multi_dimensional(observations, parameters)` |

### 7.2 Data Flow Visualization

**Single-Dimensional:**
```
Observations: [{"ts": ..., "A": 10, "B": 20}, {"ts": ..., "A": 15, "B": 25}]
                                ↓
                    Orchestrator loops per dimension
                                ↓
        A → algorithm.train([10, 15], parameter={"dimension": "A", "metadata": [...]})
        B → algorithm.train([20, 25], parameter={"dimension": "B", "metadata": [...]})
                                ↓
        Result: {"A": {baseline}, "B": {baseline}}
```

**Multi-Dimensional:**
```
Observations: [{"ts": ..., "A": 10, "B": 20}, {"ts": ..., "A": 15, "B": 25}]
                                ↓
                    Orchestrator passes all at once
                                ↓
        algorithm.train_multi_dimensional(
            observations=[{"A": 10, "B": 20}, {"A": 15, "B": 25}],
            parameters=[{"dimension": "A", ...}, {"dimension": "B", ...}]
        )
                                ↓
        Result: {model}  (single model for all dimensions)
```

---

## 8. Bucketing System

### 8.1 Two Concerns: Modeling vs Context

Bucketing serves TWO separate purposes that must not be conflated:

| Concern | Description | Who Controls |
|---------|-------------|--------------|
| **Buckets for Modeling** | Train separate model per time-context bucket | Algorithm decides (opt-in via property) |
| **Buckets for Context** | Tag anomalies with time context for analysis | Always on (Orchestrator) |

### 8.2 The Problem: Not All Algorithms Benefit from Bucketing

**ZScore/IQR (benefits from bucketing):**
- Different baselines for different time contexts make sense
- "Normal" at 3am is different from "normal" at 3pm
- Needs only ~3-10 observations per bucket

**KMeans (may NOT benefit from bucketing):**
- Needs significantly more data for meaningful clusters
- If `n_clusters=5` and `dimensions=3`, need ~50+ observations per bucket
- Sparse buckets = garbage clusters
- May prefer single global model trained on ALL data

### 8.3 New Algorithm Properties

```python
class AnomalyAlgorithm(Protocol):
    # ... existing properties ...
    
    @property
    def supports_bucketing(self) -> bool:
        """Whether to train separate model per time-context bucket.
        
        True (default): Orchestrator trains per bucket
        False: Orchestrator trains single global model
        
        Either way, detections are TAGGED with bucket context for analysis.
        """
        return True  # Default - most algorithms benefit
    
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
        return 3  # Default for simple algorithms
```

**ZScore implementation:**
```python
@property
def supports_bucketing(self) -> bool:
    return True  # Different baselines for different time contexts

@property
def min_training_samples(self) -> int:
    return 3  # Simple stats work with few samples
```

**KMeans implementation:**
```python
@property
def supports_bucketing(self) -> bool:
    return False  # Need all data for meaningful clusters

@property
def min_training_samples(self) -> int:
    return 50  # Clustering needs volume
```

### 8.4 Orchestrator Bucketing Logic

```python
def _resolve_min_training_samples(self, algorithm) -> int:
    """Resolve min_training_samples with user override support.
    
    Priority:
    1. User override in parameter metadata
    2. Algorithm default property
    """
    # Check for user override in any parameter's metadata
    for param in self.parameters:
        meta_list = param.get("metadata") or param.get("algorithm_metadata", [])
        for meta in meta_list:
            if meta.get("key") == "min_training_samples":
                return int(meta.get("value"))
    
    # Fall back to algorithm default
    return getattr(algorithm, 'min_training_samples', 3)

def train(self, observations: List[Dict], timestamp_field: str) -> Dict:
    algorithm = get_algorithm(self.algorithm_name)
    
    # Always train global model first
    if self.is_multi_dimensional:
        global_model = algorithm.train_multi_dimensional(observations, self.parameters)
    else:
        global_model = self._train_single_dimensional(algorithm, observations)
    
    # Check if algorithm supports bucketing
    supports_bucketing = getattr(algorithm, 'supports_bucketing', True)
    min_samples = self._resolve_min_training_samples(algorithm)
    
    if supports_bucketing and self.bucket_resolver:
        # Train per bucket (ZScore, IQR)
        groups = self.group_by_bucket(observations, timestamp_field)
        buckets = {}
        
        for bucket_key, bucket_obs in groups.items():
            if len(bucket_obs) < min_samples:
                # Insufficient data - use global fallback
                buckets[bucket_key] = {
                    "baselines": global_model,
                    "n_observations": len(bucket_obs),
                    "sufficient_data": False,
                    "used_global_fallback": True
                }
            else:
                # Train bucket-specific model
                if self.is_multi_dimensional:
                    baseline = algorithm.train_multi_dimensional(bucket_obs, self.parameters)
                else:
                    baseline = self._train_single_dimensional(algorithm, bucket_obs)
                
                buckets[bucket_key] = {
                    "baselines": baseline,
                    "n_observations": len(bucket_obs),
                    "sufficient_data": True,
                    "used_global_fallback": False
                }
    else:
        # Single global model (KMeans) - store as "global" bucket
        buckets = {
            "global": {
                "baselines": global_model,
                "n_observations": len(observations),
                "sufficient_data": True,
                "used_global_fallback": False
            }
        }
    
    return {
        "algorithm": self.algorithm_name,
        "is_multi_dimensional": self.is_multi_dimensional,
        "supports_bucketing": supports_bucketing,
        "bucket_profile_id": self.bucket_profile.get("profile_id") if self.bucket_profile else None,
        "buckets": buckets,
        "global_fallback": global_model,
        "n_total_observations": len(observations),
        "parameters": self.parameters
    }
```

### 8.5 Detection with Bucket Context (Always On)

Even when `supports_bucketing=False`, detections are TAGGED with bucket context:

```python
def detect(self, observation: Dict, timestamp_field: str) -> Dict:
    algorithm = get_algorithm(self.algorithm_name)
    supports_bucketing = self.training_result.get("supports_bucketing", True)
    
    # Always resolve bucket for CONTEXT (when did anomaly happen?)
    ts = parse_timestamp(observation.get(timestamp_field))
    bucket_context = self.resolve_bucket_key(ts) if ts else "unknown"
    
    # Get appropriate model
    if supports_bucketing:
        # Use bucket-specific baseline
        baselines = self.get_baseline_for_bucket(bucket_context)
    else:
        # Use global model
        baselines = self.training_result["buckets"]["global"]["baselines"]
    
    # Run detection
    if self.is_multi_dimensional:
        result = algorithm.detect_multi_dimensional(observation, baselines, self.parameters)
    else:
        result = self._detect_single_dimensional(algorithm, observation, baselines)
    
    # Always tag with bucket context for analysis
    result["bucket_context"] = bucket_context
    result["timestamp"] = ts.isoformat() if ts else None
    
    return result
```

### 8.6 Parallelization by Bucket

When `supports_bucketing=True`, the orchestrator CAN parallelize training across buckets:

```python
from concurrent.futures import ThreadPoolExecutor

def train(self, observations: List[Dict], timestamp_field: str) -> Dict:
    algorithm = get_algorithm(self.algorithm_name)
    supports_bucketing = getattr(algorithm, 'supports_bucketing', True)
    
    if not supports_bucketing or not self.bucket_resolver:
        # No parallelization - single global model
        return self._train_global_only(algorithm, observations)
    
    # Group by bucket
    groups = self.group_by_bucket(observations, timestamp_field)
    
    # Train global fallback first (needed for sparse buckets)
    global_model = self._train_model(algorithm, observations)
    
    # Parallelize bucket training
    buckets = {}
    min_samples = getattr(algorithm, 'min_training_samples', 3)
    
    def train_bucket(bucket_key: str, bucket_obs: List[Dict]) -> tuple:
        if len(bucket_obs) < min_samples:
            return bucket_key, {
                "baselines": global_model,
                "n_observations": len(bucket_obs),
                "sufficient_data": False
            }
        else:
            baseline = self._train_model(algorithm, bucket_obs)
            return bucket_key, {
                "baselines": baseline,
                "n_observations": len(bucket_obs),
                "sufficient_data": True
            }
    
    # Use thread pool for parallel bucket training
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(train_bucket, key, obs) 
            for key, obs in groups.items()
        ]
        for future in futures:
            bucket_key, result = future.result()
            buckets[bucket_key] = result
    
    return {
        "algorithm": self.algorithm_name,
        "supports_bucketing": True,
        "buckets": buckets,
        "global_fallback": global_model,
        # ...
    }
```

### 8.7 Three-Tier Bucketing Design Summary

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          BUCKET HANDLING                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. MODELING (algorithm decides via supports_bucketing property)            │
│     ┌──────────────────────────────────────────────────────────────────┐   │
│     │ supports_bucketing = True          supports_bucketing = False    │   │
│     │ ─────────────────────────          ──────────────────────────    │   │
│     │ Train per bucket                   Train single global model     │   │
│     │ ZScore, IQR                        KMeans, DBSCAN                 │   │
│     │ min_samples: 3                     min_samples: 50                │   │
│     └──────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  2. CONTEXT (always on - orchestrator handles)                              │
│     ┌──────────────────────────────────────────────────────────────────┐   │
│     │ Every detection is TAGGED with bucket_context                     │   │
│     │ "This anomaly happened during workday_14"                         │   │
│     │ Enables time-based analysis in Kibana regardless of model type    │   │
│     └──────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  3. PARALLELIZATION (orchestrator can exploit when bucketing enabled)       │
│     ┌──────────────────────────────────────────────────────────────────┐   │
│     │ If supports_bucketing=True:                                       │   │
│     │   Orchestrator can parallelize training across buckets            │   │
│     │   ThreadPoolExecutor for bucket-level parallelism                 │   │
│     │ If supports_bucketing=False:                                      │   │
│     │   Algorithm handles internal parallelization (numpy, sklearn)     │   │
│     └──────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.8 Storage Format (Consistent Regardless of Bucketing)

**With bucketing (ZScore):**
```json
{
  "algorithm": "zscore",
  "supports_bucketing": true,
  "buckets": {
    "workday_14": {"baselines": {"dim_A": {...}, "dim_B": {...}}, "n_observations": 150},
    "weekend_10": {"baselines": {"dim_A": {...}, "dim_B": {...}}, "n_observations": 45}
  },
  "global_fallback": {"dim_A": {...}, "dim_B": {...}}
}
```

**Without bucketing (KMeans):**
```json
{
  "algorithm": "kmeans",
  "supports_bucketing": false,
  "buckets": {
    "global": {"baselines": {"centroids": [...], "threshold": 2.5}, "n_observations": 1000}
  },
  "global_fallback": {"centroids": [...], "threshold": 2.5}
}
```

---

## 9. Multi-Worker Architecture

### 9.1 Core Principle: One KB Config = One Worker

**Horizontal scaling** at Dispatcher level by KB config.  
**Vertical scaling** at Algorithm level (internal parallelization).

```
┌─────────────────────────────────────────────────────────────────┐
│                    DISPATCHER LAYER                              │
│                                                                 │
│   Worker 1        Worker 2        Worker 3        Worker N      │
│   [KB-001]        [KB-002]        [KB-003]        [KB-00N]      │
│                                                                 │
│   - Each KB config assigned to exactly ONE worker               │
│   - Workers claim configs, not individual observations          │
│   - Load scales with number of KB configs                       │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                     ALGORITHM LAYER                              │
│                                                                 │
│   Algorithm decides internal parallelization:                    │
│   - ZScore: parallelize across dimensions (thread pool)         │
│   - KMeans: use sklearn vectorized operations                   │
│   - Dispatcher doesn't care HOW                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 9.2 Why This Works

1. **Data consistency**: Worker gets ALL observations for a KB config
2. **No splits for multi-dimensional**: KMeans gets complete vectors
3. **Natural load distribution**: More KB configs = more parallelism
4. **Algorithm owns performance**: Each algorithm optimizes itself

### 9.3 Implementation: DispatcherManager with Per-KB Workers

**Decision**: Single Dispatcher instance with `DispatcherManager` that spawns one `KBWorker` thread per active KB config.

**Why this approach:**
- Simple to implement and debug
- No external dependencies (no message queue)
- Sufficient for expected scale (tens to hundreds of KB configs)
- Natural fit with MongoDB change streams (one filtered cursor per worker)

**Multi-instance horizontal scaling** (multiple Dispatcher containers) is out of scope for this implementation. If needed later, it would require coordination via MongoDB locks or a message queue.

### 9.4 Per-KB Worker with Dedicated Change Stream Cursor

#### Why Per-KB Cursor?

MongoDB change streams have a **single cursor model** - all watchers on the same pipeline see ALL events. If multiple workers watch the same change stream without filtering, they:
1. All receive the same events (duplicate processing)
2. Race to process (inconsistent state)
3. Fight over cursor position

**Solution**: Each worker filters its change stream to ONLY its assigned KB config.

#### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DISPATCHER MANAGER                                   │
│                                                                             │
│   Watches: kb_configs collection for active KB configurations               │
│   Spawns: One KBWorker per active KB config                                 │
│   Stops: Workers when KB config becomes inactive                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ spawns
                                    ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│   KBWorker-001   │    │   KBWorker-002   │    │   KBWorker-003   │
│                  │    │                  │    │                  │
│  kb_id: "KB-001" │    │  kb_id: "KB-002" │    │  kb_id: "KB-003" │
│                  │    │                  │    │                  │
│  Change Stream:  │    │  Change Stream:  │    │  Change Stream:  │
│  filter by kbId  │    │  filter by kbId  │    │  filter by kbId  │
└──────────────────┘    └──────────────────┘    └──────────────────┘
          │                       │                       │
          │                       │                       │
          ▼                       ▼                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       MongoDB: series collection                             │
│                                                                             │
│   Documents: {kbId: "KB-001", timestamp: ..., dim: "metric_A", value: ...}  │
│              {kbId: "KB-002", timestamp: ..., dim: "metric_B", value: ...}  │
│              {kbId: "KB-003", timestamp: ..., dim: "metric_C", value: ...}  │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### KBWorker Implementation

```python
class KBWorker:
    """Worker dedicated to one KB config with filtered change stream."""
    
    def __init__(self, kb_id: str, kb_config: Dict, mongo_client: MongoClient):
        self.kb_id = kb_id
        self.kb_config = kb_config
        self.mongo = mongo_client
        self.running = False
        
        # Extract algorithm info
        algorithm_name = kb_config["algorithm"]["name"]
        self.algorithm = get_algorithm(algorithm_name)
        self.is_multi_dimensional = self.algorithm.is_multi_dimensional
        
        # For multi-dimensional: track expected dimensions
        self.dimensions = [
            p["dimension"] for p in kb_config["algorithm"]["parameters"]
            if p.get("is_active", True)
        ]
    
    def start(self):
        """Start watching change stream filtered to this KB."""
        self.running = True
        
        # Filtered pipeline - ONLY this KB's documents
        pipeline = [
            {"$match": {
                "operationType": "insert",
                "fullDocument.kbId": self.kb_id,
                "fullDocument.mode": 1  # Detection mode
            }}
        ]
        
        collection = self.mongo.anomaly_detection.series
        
        with collection.watch(pipeline=pipeline) as stream:
            for change in stream:
                if not self.running:
                    break
                self._process_change(change["fullDocument"])
    
    def stop(self):
        """Stop watching (graceful shutdown)."""
        self.running = False
    
    def _process_change(self, doc: Dict):
        """Process a single series element."""
        if self.is_multi_dimensional:
            self._buffer_for_multi_dimensional(doc)
        else:
            self._detect_single_dimensional(doc)
```

#### DispatcherManager Implementation

```python
class DispatcherManager:
    """Manages KBWorker lifecycle based on active KB configurations."""
    
    def __init__(self, mongo_client: MongoClient):
        self.mongo = mongo_client
        self.workers: Dict[str, KBWorker] = {}  # kb_id -> worker
        self.threads: Dict[str, Thread] = {}    # kb_id -> thread
    
    def start(self):
        """Start managing workers."""
        # Initial scan of active KB configs
        self._sync_workers()
        
        # Watch for KB config changes
        pipeline = [{"$match": {"operationType": {"$in": ["insert", "update", "delete"]}}}]
        collection = self.mongo.anomaly_detection.kb_configs
        
        with collection.watch(pipeline=pipeline) as stream:
            for change in stream:
                self._handle_config_change(change)
    
    def _sync_workers(self):
        """Ensure one worker per active KB config."""
        active_configs = list(self.mongo.anomaly_detection.kb_configs.find({
            "scheduling.detection_config.is_active": True
        }))
        
        active_ids = {str(c["_id"]) for c in active_configs}
        current_ids = set(self.workers.keys())
        
        # Spawn new workers
        for config in active_configs:
            kb_id = str(config["_id"])
            if kb_id not in current_ids:
                self._spawn_worker(kb_id, config)
        
        # Stop removed workers
        for kb_id in current_ids - active_ids:
            self._stop_worker(kb_id)
    
    def _spawn_worker(self, kb_id: str, config: Dict):
        """Create and start a new KBWorker."""
        worker = KBWorker(kb_id, config, self.mongo)
        self.workers[kb_id] = worker
        
        thread = Thread(target=worker.start, daemon=True)
        self.threads[kb_id] = thread
        thread.start()
        
        logger.info(f"Spawned worker for KB config: {kb_id}")
    
    def _stop_worker(self, kb_id: str):
        """Stop and remove a KBWorker."""
        if kb_id in self.workers:
            self.workers[kb_id].stop()
            del self.workers[kb_id]
            del self.threads[kb_id]
            logger.info(f"Stopped worker for KB config: {kb_id}")
```

### 9.5 Observation Buffering for Multi-Dimensional Detection

#### The Problem

Extractor processes Elasticsearch cursor **page-by-page** (1000 docs per page). For each row with N dimensions, FilterService explodes it into N `SeriesElement` documents. These arrive at the Dispatcher as **separate change stream events**, not atomic observations.

For multi-dimensional algorithms (KMeans), we need **complete vectors** with ALL dimensions for the same timestamp.

```
Extractor Output (per page):
┌─────────────────────────────────────────────────────────────────┐
│   Page 1: 1000 rows × 3 dimensions = 3000 SeriesElements        │
│                                                                 │
│   {kbId, timestamp: T1, dim: "cpu", value: 45}                  │
│   {kbId, timestamp: T1, dim: "memory", value: 78}               │
│   {kbId, timestamp: T1, dim: "requests", value: 120}            │
│   {kbId, timestamp: T2, dim: "cpu", value: 50}                  │
│   ... (arrives as separate change events)                       │
└─────────────────────────────────────────────────────────────────┘

Multi-Dimensional Algorithm Needs:
┌─────────────────────────────────────────────────────────────────┐
│   observation T1: {"cpu": 45, "memory": 78, "requests": 120}    │
│   observation T2: {"cpu": 50, "memory": 80, "requests": 115}    │
└─────────────────────────────────────────────────────────────────┘
```

#### Buffering Solution

Worker maintains a buffer indexed by timestamp, collects dimensions until complete:

```python
class KBWorker:
    def __init__(self, kb_id: str, kb_config: Dict, mongo_client: MongoClient):
        # ... existing init ...
        
        # Buffering for multi-dimensional detection
        self.expected_dims = set(self.dimensions)
        self.buffer: Dict[datetime, Dict[str, Any]] = {}
        self.buffer_timeout_seconds = 0.5  # 500ms - batches arrive fast
    
    def _buffer_for_multi_dimensional(self, doc: Dict):
        """Buffer dimensions until observation is complete."""
        ts = doc["timestamp"]
        dim = doc["metadata"]["dim"]
        value = doc["value"]
        
        # Initialize timestamp entry if needed
        if ts not in self.buffer:
            self.buffer[ts] = {
                "_first_seen": time.time(),
                "_dims": {}
            }
        
        # Store this dimension's value
        self.buffer[ts]["_dims"][dim] = value
        
        # Check if observation is complete
        collected_dims = set(self.buffer[ts]["_dims"].keys())
        
        if collected_dims == self.expected_dims:
            # Complete! Extract and detect
            observation = self.buffer[ts]["_dims"].copy()
            del self.buffer[ts]
            self._detect_multi_dimensional(observation, ts)
    
    def _detect_multi_dimensional(self, observation: Dict, timestamp: datetime):
        """Run detection on complete observation vector."""
        model = self._get_trained_model()
        parameters = self.kb_config["algorithm"]["parameters"]
        
        result = self.algorithm.detect_multi_dimensional(
            observation=observation,
            model=model,
            parameters=parameters
        )
        
        if result.get("is_anomaly"):
            self._post_anomaly(result, observation, timestamp)
```

#### ⚠️ CRITICAL: Discard Incomplete Observations

**Safety Rule**: If buffer timeout expires, **DISCARD** incomplete observations. NEVER process partial data.

**Rationale**: Partial vectors cause false positives:
- Missing dimensions → vector looks different from training data
- KMeans distance inflated by zeros/defaults in missing dimensions
- Better to miss an anomaly than report a false positive

```python
def _flush_stale_buffers(self):
    """DISCARD incomplete observations - do NOT process partial data.
    
    Called periodically (e.g., every 100ms) to clean stale entries.
    """
    now = time.time()
    stale_timestamps = []
    
    for ts, entry in self.buffer.items():
        age_seconds = now - entry["_first_seen"]
        if age_seconds > self.buffer_timeout_seconds:
            stale_timestamps.append(ts)
    
    for ts in stale_timestamps:
        collected = set(self.buffer[ts]["_dims"].keys())
        missing = self.expected_dims - collected
        
        logger.warning(
            f"[{self.kb_id}] Discarding incomplete observation at {ts}. "
            f"Expected: {self.expected_dims}, Got: {collected}, "
            f"Missing: {missing}"
        )
        
        # DISCARD - do NOT process
        del self.buffer[ts]
```

#### Why 500ms Timeout is Sufficient

Extractor writes **batches** per cursor page. All SeriesElements from the same page arrive within milliseconds:

```
Timeline:
├── 0ms: Page 1 insert starts (3000 docs)
├── 50ms: Page 1 insert complete, change events fire
├── 100ms: Worker receives all 3000 events for page 1
├── ...
├── 500ms: Timeout - any incomplete observation is truly orphaned
```

If an observation is incomplete after 500ms, it means:
1. Extractor bug (dimension filtering failed)
2. MongoDB write failure
3. Network partition

All cases warrant discarding rather than processing with bad data.

#### Complete KBWorker with Buffering

```python
import time
import threading
from datetime import datetime
from typing import Dict, List, Set, Any
from threading import Thread

class KBWorker:
    """Worker dedicated to one KB config with filtered change stream."""
    
    def __init__(self, kb_id: str, kb_config: Dict, mongo_client: MongoClient):
        self.kb_id = kb_id
        self.kb_config = kb_config
        self.mongo = mongo_client
        self.running = False
        
        # Algorithm info
        algorithm_name = kb_config["algorithm"]["name"]
        self.algorithm = get_algorithm(algorithm_name)
        self.is_multi_dimensional = self.algorithm.is_multi_dimensional
        
        # Dimensions
        self.dimensions = [
            p["dimension"] for p in kb_config["algorithm"]["parameters"]
            if p.get("is_active", True)
        ]
        
        # Buffering for multi-dimensional
        if self.is_multi_dimensional:
            self.expected_dims: Set[str] = set(self.dimensions)
            self.buffer: Dict[datetime, Dict[str, Any]] = {}
            self.buffer_timeout_seconds = 0.5
            self._buffer_lock = threading.Lock()
    
    def start(self):
        """Start watching change stream filtered to this KB."""
        self.running = True
        
        # Start buffer cleanup thread for multi-dimensional
        if self.is_multi_dimensional:
            cleanup_thread = Thread(target=self._buffer_cleanup_loop, daemon=True)
            cleanup_thread.start()
        
        # Filtered pipeline
        pipeline = [
            {"$match": {
                "operationType": "insert",
                "fullDocument.kbId": self.kb_id,
                "fullDocument.mode": 1
            }}
        ]
        
        collection = self.mongo.anomaly_detection.series
        
        with collection.watch(pipeline=pipeline) as stream:
            for change in stream:
                if not self.running:
                    break
                self._process_change(change["fullDocument"])
    
    def stop(self):
        self.running = False
    
    def _process_change(self, doc: Dict):
        if self.is_multi_dimensional:
            self._buffer_for_multi_dimensional(doc)
        else:
            self._detect_single_dimensional(doc)
    
    def _buffer_for_multi_dimensional(self, doc: Dict):
        ts = doc["timestamp"]
        dim = doc["metadata"]["dim"]
        value = doc["value"]
        
        with self._buffer_lock:
            if ts not in self.buffer:
                self.buffer[ts] = {"_first_seen": time.time(), "_dims": {}}
            
            self.buffer[ts]["_dims"][dim] = value
            collected = set(self.buffer[ts]["_dims"].keys())
            
            if collected == self.expected_dims:
                observation = self.buffer[ts]["_dims"].copy()
                del self.buffer[ts]
                
        if collected == self.expected_dims:
            self._detect_multi_dimensional(observation, ts)
    
    def _buffer_cleanup_loop(self):
        """Periodically discard incomplete observations."""
        while self.running:
            time.sleep(0.1)  # Check every 100ms
            self._flush_stale_buffers()
    
    def _flush_stale_buffers(self):
        """DISCARD incomplete observations."""
        now = time.time()
        stale = []
        
        with self._buffer_lock:
            for ts, entry in self.buffer.items():
                if now - entry["_first_seen"] > self.buffer_timeout_seconds:
                    stale.append(ts)
            
            for ts in stale:
                collected = set(self.buffer[ts]["_dims"].keys())
                missing = self.expected_dims - collected
                logger.warning(
                    f"[{self.kb_id}] Discarding incomplete observation at {ts}. "
                    f"Missing dimensions: {missing}"
                )
                del self.buffer[ts]  # DISCARD
    
    def _detect_single_dimensional(self, doc: Dict):
        """Direct detection for single-dimensional algorithms."""
        # Existing single-dimensional flow
        ...
    
    def _detect_multi_dimensional(self, observation: Dict, timestamp: datetime):
        """Detection for complete multi-dimensional observation."""
        model = self._get_trained_model()
        parameters = self.kb_config["algorithm"]["parameters"]
        
        result = self.algorithm.detect_multi_dimensional(
            observation=observation,
            model=model,
            parameters=parameters
        )
        
        if result.get("is_anomaly"):
            self._post_anomaly(result, observation, timestamp)
```

---

## 10. Implementation Checklist

### Phase 1: Algorithm Interface
- [ ] Add `is_multi_dimensional` property to Protocol
- [ ] Add `supports_bucketing` property to Protocol (default: True)
- [ ] Add `min_training_samples` property to Protocol (default: 3)
- [ ] Update `register_algorithm` with mode validation
- [ ] Add `train()` signature with `parameter` argument
- [ ] Add `detect()` signature with `parameter` argument

### Phase 2: Update Existing Algorithms
- [ ] `zscore.py`: Add `is_multi_dimensional = False`
- [ ] `zscore.py`: Add `supports_bucketing = True`
- [ ] `zscore.py`: Add `min_training_samples = 3`
- [ ] `zscore.py`: Update `train()` to extract metadata from `parameter`
- [ ] `zscore.py`: Update `detect()` to accept `parameter`
- [ ] `iqr.py`: Same changes
- [ ] `mock.py`: Same changes

### Phase 3: Orchestrator Changes
- [ ] Add `is_multi_dimensional` field to `TrainingOrchestrator`
- [ ] Add `_train_single_dimensional()` method
- [ ] Update `train()` to check `supports_bucketing` property
- [ ] Update `train()` to use `min_training_samples` for fallback logic
- [ ] Add bucket parallelization option (ThreadPoolExecutor)
- [ ] Add `is_multi_dimensional` field to `DetectionOrchestrator`
- [ ] Add `_detect_single_dimensional()` method
- [ ] Update `detect()` to always tag with `bucket_context`
- [ ] Add `detect_batch_multi_dimensional()` method

### Phase 4: Dispatcher Changes
- [ ] `detect_anomaly()`: Resolve mode before orchestrator
- [ ] `detect_anomaly()`: Branch control flow (loop vs batch)
- [ ] `run_training()`: Resolve mode before orchestrator
- [ ] `run_training()`: Pass mode to orchestrator

### Phase 5: Testing
- [ ] Unit tests for registration validation
- [ ] Unit tests for single-dimensional flow with bucketing
- [ ] Unit tests for single-dimensional flow without bucketing
- [ ] Unit tests for bucket context tagging
- [ ] Integration test with existing algorithms
- [ ] (Future) Integration test with KMeans

### Phase 6: Per-KB Worker Architecture
- [ ] Create `KBWorker` class with filtered change stream
- [ ] Add MongoDB change stream pipeline filter by `kbId`
- [ ] Add MongoDB change stream pipeline filter by `mode: 1` (detection)
- [ ] Create `DispatcherManager` class
- [ ] Implement `_sync_workers()` for initial KB config scan
- [ ] Implement `_spawn_worker()` and `_stop_worker()` lifecycle
- [ ] Add KB config change stream watcher in manager
- [ ] Thread-per-worker execution model

### Phase 7: Observation Buffering (Multi-Dimensional Detection)
- [ ] Add `buffer` dict indexed by timestamp in `KBWorker`
- [ ] Add `expected_dims` set from KB config parameters
- [ ] Implement `_buffer_for_multi_dimensional()` method
- [ ] Track `_first_seen` timestamp for buffer entries
- [ ] Check dimension completeness on each incoming doc
- [ ] Implement `_flush_stale_buffers()` method
- [ ] **CRITICAL**: Discard (not process) incomplete observations
- [ ] Add `_buffer_cleanup_loop()` with 100ms interval
- [ ] Add `_buffer_lock` for thread safety
- [ ] Configurable `buffer_timeout_seconds` (default: 0.5)
- [ ] Warning log for discarded incomplete observations

### Phase 8: Integration Testing
- [ ] Test single-dimensional detection with KBWorker
- [ ] Test multi-dimensional detection with buffering
- [ ] Test incomplete observation discard behavior
- [ ] Test DispatcherManager worker spawn/stop lifecycle
- [ ] Test multiple KBWorkers in parallel
- [ ] Load test with high volume change stream events

---

## 11. Example: Adding KMeans Algorithm

```python
@register_algorithm
@dataclass
class KMeansAlgorithm:
    __algorithm_meta__ = {
        "description": "K-Means clustering for multi-dimensional anomaly detection",
        "best_for": "Finding outliers based on cluster distance",
        "metadata_schema": {
            "n_clusters": {"type": "int", "default": 5},
            "distance_threshold_percentile": {"type": "float", "default": 95.0}
        }
    }
    
    @property
    def name(self) -> str:
        return "kmeans"
    
    @property
    def is_multi_dimensional(self) -> bool:
        return True
    
    @property
    def supports_bucketing(self) -> bool:
        return False  # Need all data for meaningful clusters
    
    @property
    def min_training_samples(self) -> int:
        return 50  # Clustering needs significant data volume
    
    def train_multi_dimensional(
        self, 
        observations: List[Dict], 
        parameters: List[Dict],
        **kwargs
    ) -> Dict:
        # Extract settings from parameters metadata
        n_clusters = 5
        for param in parameters:
            meta_list = param.get("metadata") or param.get("algorithm_metadata", [])
            for meta in meta_list:
                if meta.get("key") == "n_clusters":
                    n_clusters = int(meta.get("value", 5))
                    break
        
        # Get active dimensions
        dimensions = [p["dimension"] for p in parameters if p.get("is_active", True)]
        
        # Build feature vectors
        vectors = []
        for obs in observations:
            vec = [obs.get(d, 0) for d in dimensions]
            vectors.append(vec)
        
        # Train KMeans
        from sklearn.cluster import KMeans
        kmeans = KMeans(n_clusters=n_clusters)
        kmeans.fit(vectors)
        
        # Calculate distance threshold from training data
        distances = kmeans.transform(vectors).min(axis=1)
        threshold = np.percentile(distances, 95)
        
        return {
            "centroids": kmeans.cluster_centers_.tolist(),
            "dimensions": dimensions,
            "threshold": threshold,
            "n_clusters": n_clusters
        }
    
    def detect_multi_dimensional(
        self,
        observation: Dict,
        model: Dict,
        parameters: List[Dict]
    ) -> Dict:
        dimensions = model["dimensions"]
        vec = [observation.get(d, 0) for d in dimensions]
        
        # Calculate distance to nearest centroid
        centroids = np.array(model["centroids"])
        distances = np.linalg.norm(centroids - vec, axis=1)
        min_distance = distances.min()
        
        is_anomaly = min_distance > model["threshold"]
        
        return {
            "is_anomaly": is_anomaly,
            "distance": min_distance,
            "threshold": model["threshold"],
            "nearest_cluster": int(distances.argmin())
        }
    
    def get_dashboard_fields(self, detection_result: Dict) -> Dict:
        return {
            "cluster_distance": detection_result.get("distance"),
            "distance_threshold": detection_result.get("threshold"),
            "nearest_cluster": detection_result.get("nearest_cluster")
        }
```

---

## 12. Example: ZScore with Bucketing Properties

```python
@register_algorithm
@dataclass
class ZScoreAlgorithm:
    __algorithm_meta__ = {
        "description": "Z-Score statistical anomaly detection",
        "best_for": "Normally distributed data with consistent patterns",
        "metadata_schema": {
            "percentile": {"type": "float", "default": 99.5}
        }
    }
    
    @property
    def name(self) -> str:
        return "zscore"
    
    @property
    def is_multi_dimensional(self) -> bool:
        return False  # Process each dimension independently
    
    @property
    def supports_bucketing(self) -> bool:
        return True  # Different baselines for different time contexts
    
    @property
    def min_training_samples(self) -> int:
        return 3  # Simple stats work with few samples
    
    def train(self, values: List[float], parameter: Dict = None, **kwargs) -> Dict:
        # Extract percentile from parameter metadata
        percentile = 99.5
        if parameter:
            meta_list = parameter.get("metadata") or parameter.get("algorithm_metadata", [])
            for meta in meta_list:
                if meta.get("key") == "percentile":
                    percentile = float(meta.get("value", 99.5))
        
        mean = np.mean(values)
        std = np.std(values)
        
        # Calculate threshold based on percentile
        z_scores = np.abs((np.array(values) - mean) / std) if std > 0 else np.zeros(len(values))
        threshold = np.percentile(z_scores, percentile)
        
        return {
            "mean": mean,
            "std": std,
            "threshold": threshold,
            "n_samples": len(values)
        }
    
    def detect(self, value: float, baseline: Dict, parameter: Dict = None) -> Dict:
        mean = baseline["mean"]
        std = baseline["std"]
        threshold = baseline["threshold"]
        
        if std == 0:
            z_score = 0.0
            is_anomaly = False
        else:
            z_score = abs((value - mean) / std)
            is_anomaly = z_score > threshold
        
        return {
            "is_anomaly": is_anomaly,
            "z_score": z_score,
            "mean": mean,
            "std": std,
            "threshold": threshold,
            "value": value
        }
    
    def get_dashboard_fields(self, detection_result: Dict) -> Dict:
        return {
            "z_score": detection_result.get("z_score"),
            "mean": detection_result.get("mean"),
            "std": detection_result.get("std"),
            "threshold": detection_result.get("threshold")
        }
```

---

## References

- Full design rationale: `Doc/TODO_Implementation_Plan.md` Parts 5-8
- Algorithm interface: `MotorDA/Dispatcher/algorithm_interface.py`
- Orchestrators: `MotorDA/Dispatcher/training_orchestrator.py`
- Dispatcher: `MotorDA/Dispatcher/DADispatcher.py`
