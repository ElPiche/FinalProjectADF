# TODO Implementation Plan - DADispatcher & Training Orchestrator Cleanup

> **Created**: December 2, 2025  
> **Branch**: `feature/fix-train-orchestrator`  
> **Status**: Ready for Implementation

## Executive Summary

This document outlines the cleanup of legacy schema fallbacks and code improvements in `DADispatcher.py` and `training_orchestrator.py`. Since we are **not in production**, we can safely remove backward compatibility code for old schemas.

---

## Part 1: Schema Fallback Removal (DADispatcher.py)

### 1.1 Remove `training_config` Collection Fallback (Line 364)

**Current Code:**
```python
#TODO: FIX remove fallback to old training_config
if not kb_config:
    # Fallback to training_config (old style)
    kb_config = get_collection(TRAINING_CONFIG_COLLECTION).find_one(
        {"kb_id": config_id}
    )
```

**Action:** Remove the fallback block entirely.

**Rationale:** 
- The `kb_configs` collection in `knowledge_base` DB is the authoritative source
- Detection should fail explicitly if KB config is missing (data integrity issue)

**Ramifications:**
- None - all configs should be in `kb_configs`
- If detection fails, it indicates a bug in config creation flow

---

### 1.2 Remove Old `algorithms[]` Schema Fallback (Line 380)

**Current Code:**
```python
#TODO: FIX remove fallback to old schema
if not alg_config:
    # Old schema with algorithms list
    algorithms = kb_config.get("algorithms", [])
    if algorithms:
        alg_config = algorithms[0]
```

**Action:** Remove the fallback. Only support `kb_config.algorithm` (singular).

**Rationale:**
- New unified schema uses singular `algorithm` field
- `KBConfig` model in `MCP/KB-MCP/models.py` already normalizes to singular via `_migrate_legacy_schema`

**Ramifications:**
- None - KB-MCP only creates new schema configs
- `models.py` line 287-290 handles migration at read time if needed

---

### 1.3 Remove Default Algorithm Fallback (Line 393)

**Current Code:**
```python
# TODO: Remove fallback to ZScore
alg_name = alg_config.get("name") or alg_config.get("alg_name", "zscore")
```

**Action:** Remove default, throw explicit error if missing.

**New Code:**
```python
alg_name = alg_config.get("name")
if not alg_name:
    raise ValueError(f"Algorithm name missing in config {config_id}. "
                     f"Config must have 'algorithm.name' field.")
alg_name = alg_name.lower()
```

**Rationale:**
- Algorithm name is required in schema validation
- Silent defaults hide configuration bugs

**Ramifications:**
- None - `AlgorithmConfig` validator in `models.py` requires name
- Early failure is better than wrong algorithm

---

### 1.4 Simplify Parameter Extraction (Line 401)

**Current Code:**
```python
# TODO: Remove ifs only alg_params = alg_config["parameters"] remains.
if isinstance(alg_config.get("parameters"), list):
    alg_params = alg_config["parameters"]
elif isinstance(alg_config.get("parameters"), dict):
    alg_params = alg_config["parameters"].get("observed_values", [])
else:
    alg_params = alg_config.get("alg_parameters", [])
```

**Action:** Remove only the dead `else` branch (legacy `alg_parameters` format).

**New Code:**
```python
if isinstance(alg_config.get("parameters"), list):
    alg_params = alg_config["parameters"]
elif isinstance(alg_config.get("parameters"), dict):
    alg_params = alg_config["parameters"].get("observed_values", [])
else:
    raise ValueError(f"Algorithm parameters missing or invalid format in config {config_id}")
```

**Rationale:**
- The Extractor creates `training_config` with `parameters.observed_values` structure (dict format)
- KB configs from MCP have `parameters` as direct list
- Both formats are valid and in use - keep both branches
- Only remove the `alg_parameters` fallback (truly legacy, no longer created)

**Why keep both branches:**
- `run_training()` receives `training_config` document from Extractor → dict with `observed_values`
- `detect_anomaly()` reads from `kb_configs` → direct list format
- Different code paths use different document sources

**Schema in Extractor (`AlgorithmParameters.java`):**
```java
@Field("observed_values")
private List<ObservedValue> observedValues;
```

This creates: `{"parameters": {"observed_values": [...]}}`

---

## Part 2: Add `replace` to Change Stream Pipeline (Line 686)

**Current Code:**
```python
#TODO: check for replace operationType
pipeline = [
    {"$match": {
        "$or": [
            {"operationType": "insert"},
            {"operationType": "update"}
        ]
    }}
]
```

**Action:** Add `replace` operationType.

**New Code:**
```python
pipeline = [
    {"$match": {
        "$or": [
            {"operationType": "insert"},
            {"operationType": "update"},
            {"operationType": "replace"}
        ]
    }}
]
```

**Investigation Results:**

1. **KB-MCP `modify_kb_config`** uses `collection.update_one()` with `$set`:
   ```python
   # mcp_tools_pkg/modify_kb_config.py:459
   result = await asyncio.to_thread(
       collection.update_one,
       {"_id": object_id},
       {"$set": payload},
   )
   ```
   This triggers `operationType: "update"` ✅ Already handled

2. **Extractor `BatchModeService`** uses Spring's `repository.save()`:
   ```java
   // BatchModeService.java:143-145
   trainingConfigRepository.findByKbId(config.getId()).ifPresent(trainingConfig ->
       trainConfig.setId(trainingConfig.getId()));  // Sets existing _id
   trainingConfigRepository.save(trainConfig);      // This does REPLACE
   ```
   Spring Data MongoDB's `save()` with existing `_id` triggers `operationType: "replace"` ⚠️ NOT handled

3. **Extractor `KbConfigReaderService`** already handles `replace`:
   ```java
   // KbConfigReaderService.java:56
   Aggregates.match(Filters.in("operationType", List.of("insert", "update", "replace")))
   ```

**Ramifications:**
- Without `replace`, retraining after `modify_kb_config` on KB config may not trigger
- The Extractor re-saves `training_config` when KB changes, triggering `replace`
- This is why training may not re-run after modifying a config

---

## Part 3: Algorithm Dashboard Fields (Lines 552-582)

**Current Code:**
```python
#TODO: remove hardcoded fields for dashboard, must be defined by each algorithm
# ... hardcoded extraction of z_score, iqr_score, lower_bound, etc.
```

**Action:** Add `get_dashboard_fields()` method to algorithm interface.

### 3.1 Update Algorithm Interface

**File:** `MotorDA/Dispatcher/algorithm_interface.py`

Add to `AnomalyAlgorithm` Protocol:
```python
def get_dashboard_fields(self, detection_result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract flat fields for Kibana dashboard from detection result.
    
    Returns dict with algorithm-specific fields like:
    - zscore: {"z_score": 2.5, "mean": 10.0, "std": 2.0, "threshold": 2.3}
    - iqr: {"iqr_score": 1.2, "lower_bound": 5.0, "upper_bound": 15.0, "q1": 7.0, "q3": 12.0}
    """
    ...
```

### 3.2 Implement in ZScore Algorithm

**File:** `MotorDA/Dispatcher/algorithms/zscore/zscore.py`

```python
def get_dashboard_fields(self, detection_result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract flat fields for Kibana from zscore detection."""
    return {
        "z_score": detection_result.get("z_score"),
        "mean": detection_result.get("mean"),
        "std": detection_result.get("std"),
        "threshold": detection_result.get("threshold"),
    }
```

### 3.3 Implement in IQR Algorithm

**File:** `MotorDA/Dispatcher/algorithms/iqr/iqr.py`

```python
def get_dashboard_fields(self, detection_result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract flat fields for Kibana from IQR detection."""
    return {
        "iqr_score": detection_result.get("distance_from_bounds"),
        "lower_bound": detection_result.get("lower_bound"),
        "upper_bound": detection_result.get("upper_bound"),
        "q1": detection_result.get("q1"),
        "q3": detection_result.get("q3"),
    }
```

### 3.4 Update DADispatcher

**File:** `MotorDA/Dispatcher/DADispatcher.py` (in `post_anomaly_to_insights`)

Replace hardcoded field extraction (lines 552-582) with:
```python
# Get flat fields from algorithm for Kibana dashboard
algorithm_instance = get_algorithm(algorithm)
algorithm_details_with_flat = serialize_for_json(dimension_results)

# Let algorithm define its dashboard fields
if primary_metric and primary_details:
    flat_fields = algorithm_instance.get_dashboard_fields(primary_details)
    algorithm_details_with_flat.update(flat_fields)
```

**Ramifications:**

| Component | Impact |
|-----------|--------|
| `algorithm_interface.py` | Add new method to Protocol |
| `register_algorithm` decorator | Add validation for new method |
| `zscore/zscore.py` | Implement `get_dashboard_fields()` |
| `iqr/iqr.py` | Implement `get_dashboard_fields()` |
| `mock/mock.py` | Implement `get_dashboard_fields()` (return empty) |
| Kibana dashboards | No change - same field names |
| Future algorithms | Must implement this method |

---

## Part 4: Rename `observed_values` → `dimensions`

### Files Affected

| File | Line | Current | New |
|------|------|---------|-----|
| `DADispatcher.py` | 436 | `observed_values = serie_to_detect.get("observed_values", [])` | `dimensions = serie_to_detect.get("observed_values", [])` |
| `DADispatcher.py` | 438 | `if not observed_values:` | `if not dimensions:` |
| `DADispatcher.py` | 442 | `logger.info(f"... {len(observed_values)} observations")` | `logger.info(f"... {len(dimensions)} observations")` |
| `DADispatcher.py` | 447 | `for obs in observed_values:` | `for obs in dimensions:` |
| `DADispatcher.py` | 717 | `observed_values = load_training_series(config_id)` | `dimensions = load_training_series(config_id)` |
| `DADispatcher.py` | 720 | `if not observed_values:` | `if not dimensions:` |
| `training_orchestrator.py` | 126 | `observed_values: List[Dict[str, Any]],` | `dimensions: List[Dict[str, Any]],` |
| `training_orchestrator.py` | 179 | `observed_values: List[Dict[str, Any]],` | `dimensions: List[Dict[str, Any]],` |

**Note:** This is a variable rename only. The MongoDB field name `observed_values` stays the same - we're just renaming the Python variable for clarity.

**Ramifications:**
- Internal refactor only
- No external API changes
- No MongoDB schema changes

---

## Part 5: Deferred Items (DO NOT IMPLEMENT)

| Location | Reason |
|----------|--------|
| `DADispatcher.py:445` | Multiple dimensions - keep, revisit for clustering |
| `DADispatcher.py:775` (`load_detection_observations`) | Keep for future KMeans clustering |
| `training_orchestrator.py:175` (`percentile` hardcode) | Part of metadata enhancements phase |
| `training_orchestrator.py:230` (`min_points` hardcode) | Part of metadata enhancements phase |
| `training_orchestrator.py:360` (`detect_batch` unused) | Keep for testing + clustering |
| `training_orchestrator.py:1` (rename file) | User will handle manually |

---

## Implementation Order

### Phase 1: Safe Changes (No Dependencies)
1. ✅ Line 686: Add `replace` to change stream pipeline
2. ✅ Line 393: Remove ZScore default, throw error
3. ✅ Line 364 + 380: Remove schema fallbacks (must be together)

### Phase 2: Algorithm Interface Extension
4. Add `get_dashboard_fields()` to `algorithm_interface.py`
5. Implement in `zscore.py`, `iqr.py`, `mock.py`
6. Update `DADispatcher.py` lines 552-582

### Phase 3: Parameter Extraction Fix
7. **Decision needed:** Option A or B for `run_training()` config source
8. Implement chosen option
9. Simplify line 401 parameter extraction

### Phase 4: Rename Pass
10. Rename `observed_values` → `dimensions` (all locations)

---

## Testing Requirements

| Change | Test |
|--------|------|
| Replace in pipeline | Create KB → Modify KB → Verify training re-triggers |
| Schema fallback removal | Run E2E test with new config |
| Dashboard fields | Create anomaly → Check Elasticsearch doc has flat fields |
| Rename | Unit tests should pass (no functional change) |

---

## Files Modified Summary

| File | Changes |
|------|---------|
| `MotorDA/Dispatcher/DADispatcher.py` | 8 locations |
| `MotorDA/Dispatcher/algorithm_interface.py` | 1 new method |
| `MotorDA/Dispatcher/algorithms/zscore/zscore.py` | 1 new method |
| `MotorDA/Dispatcher/algorithms/iqr/iqr.py` | 1 new method |
| `MotorDA/Dispatcher/algorithms/mock/mock.py` | 1 new method |
| `MotorDA/Dispatcher/training_orchestrator.py` | 2 renames |

---

## Part 6: Future - Algorithm Metadata Schema

> **Status:** Design Complete - Implementation Deferred

### Problem Statement

Currently, algorithm metadata is a "dumb" pass-through:
```json
"metadata": [{"key": "anything", "value": "whatever"}]
```

The AI/user can provide invalid keys that are silently ignored at runtime.

### Proposed Solution

Each algorithm declares its **expected metadata fields** in `__algorithm_meta__`:

```python
@register_algorithm
@dataclass
class IQRAlgorithm:
    __algorithm_meta__ = {
        "description": "IQR-based outlier detection",
        "best_for": "Non-normal distributions, robust to extreme outliers",
        
        # Declare expected metadata fields with types and defaults
        "metadata_schema": {
            "multiplier": {
                "type": "float",
                "default": 1.5,
                "description": "IQR multiplier for bounds (1.5=standard, 3.0=extreme only)",
                "required": False,
            }
        }
    }
```

### Example for Future KMeans

```python
__algorithm_meta__ = {
    "description": "K-Means clustering for multi-dimensional anomaly detection",
    "metadata_schema": {
        "n_clusters": {
            "type": "int",
            "default": 5,
            "description": "Number of clusters to form",
            "required": False,
        },
        "max_iterations": {
            "type": "int",
            "default": 300,
            "description": "Maximum iterations for convergence",
            "required": False,
        },
        "distance_threshold_percentile": {
            "type": "float",
            "default": 95.0,
            "description": "Percentile for anomaly distance threshold",
            "required": False,
        }
    }
}
```

### Integration Points

1. **`list_available_algorithms` MCP Tool** - Already reads `__algorithm_meta__`, would show metadata schema
2. **`create_da_config` / `modify_kb_config`** - Could validate metadata keys/types
3. **Algorithm at runtime** - Can trust metadata format

### Deferred Reason

- Requires schema validation in MCP tools
- Current algorithms work without it
- Will implement when adding KMeans or other complex algorithms

---

## Part 7: Future - Multi-Dimensional Algorithm Support

> **Status:** Design Complete - Implementation Deferred  
> **Depends On:** KMeans implementation by team member

### Problem Statement

Current architecture assumes all algorithms process dimensions **independently** (ZScore, IQR).
Future algorithms like KMeans need to process all dimensions **together**.

The orchestrator needs to know which mode to use, but:
- Mode should be **intrinsic to the algorithm**, not MCP metadata
- Some algorithms may support **both modes** dynamically
- Must be **fail-fast** with no silent fallbacks

### Design: Property + Optional Method Override

#### Algorithm Interface (Clean, Minimal, Fail-Fast)

```python
# algorithm_interface.py

import logging

logger = logging.getLogger(__name__)

@runtime_checkable
class AnomalyAlgorithm(Protocol):
    """Interface for anomaly detection algorithms.
    
    REQUIRED: name, is_multi_dimensional, and ONE of:
    - train() + detect() for single-dimensional algorithms
    - train_multi_dimensional() + detect_multi_dimensional() for multi-dimensional
    
    OPTIONAL:
    - detect_batch() for single-dimensional batch processing
    - detect_batch_multi_dimensional() for multi-dimensional batch processing
    - resolve_multi_dimensional() for algorithms supporting both modes
    """
    
    # === REQUIRED ===
    
    @property
    def name(self) -> str:
        """Algorithm identifier (e.g., 'zscore', 'kmeans')."""
        ...
    
    @property
    def is_multi_dimensional(self) -> bool:
        """True if algorithm processes all dimensions together.
        
        Single-dimensional (False): Each dimension trained/detected independently.
        Examples: ZScore, IQR - each dimension has its own baseline.
        
        Multi-dimensional (True): All dimensions processed together.
        Examples: KMeans, Isolation Forest - model uses relationships between dimensions.
        """
        ...
    
    # === SINGLE-DIMENSIONAL METHODS (required if is_multi_dimensional=False) ===
    
    def train(self, values: List[float], **kwargs) -> Dict[str, Any]:
        """Train baseline from single-dimension values."""
        ...
    
    def detect(self, value: float, baseline: Dict[str, Any]) -> Dict[str, Any]:
        """Detect if a single value is anomalous. Must return 'is_anomaly' key."""
        ...
    
    # === MULTI-DIMENSIONAL METHODS (required if is_multi_dimensional=True) ===
    
    def train_multi_dimensional(
        self,
        observations: List[Dict[str, Any]],
        parameters: List[Dict[str, Any]],
        **kwargs
    ) -> Dict[str, Any]:
        """Train model from observations containing multiple dimensions."""
        ...
    
    def detect_multi_dimensional(
        self,
        observation: Dict[str, Any],
        model: Dict[str, Any],
        parameters: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Detect if an observation is anomalous. Must return 'is_anomaly' key."""
        ...
    
    # === OPTIONAL METHODS ===
    # These are checked via hasattr() at runtime, not required by protocol
    #
    # def detect_batch(self, values: List[float], baseline: Dict) -> List[Dict]:
    #     """Optional: Batch detection for single-dimensional."""
    #
    # def detect_batch_multi_dimensional(self, observations: List[Dict], model: Dict, parameters: List[Dict]) -> List[Dict]:
    #     """Optional: Batch detection for multi-dimensional."""
    #
    # def resolve_multi_dimensional(self, parameters: List[Dict]) -> bool:
    #     """Optional: Dynamic mode resolution for algorithms supporting both modes."""
```

#### Registration Validation (Fail-Fast with Logging)

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
        missing = [m for m in required if not hasattr(instance, m)]
        if missing:
            logger.error(f"Registration failed: {cls.__name__} is multi-dimensional but missing: {missing}")
            raise TypeError(
                f"{cls.__name__} is multi-dimensional but missing required methods: {missing}. "
                f"Multi-dimensional algorithms must implement train_multi_dimensional() and detect_multi_dimensional()."
            )
    else:
        required = ['train', 'detect']
        missing = [m for m in required if not hasattr(instance, m)]
        if missing:
            logger.error(f"Registration failed: {cls.__name__} is single-dimensional but missing: {missing}")
            raise TypeError(
                f"{cls.__name__} is single-dimensional but missing required methods: {missing}. "
                f"Single-dimensional algorithms must implement train() and detect()."
            )
    
    # === OPTIONAL: Check for resolve_multi_dimensional ===
    has_resolver = hasattr(instance, 'resolve_multi_dimensional')
    
    # If algorithm has resolver, it MUST implement BOTH sets of methods
    if has_resolver:
        all_methods = ['train', 'detect', 'train_multi_dimensional', 'detect_multi_dimensional']
        missing = [m for m in all_methods if not hasattr(instance, m)]
        if missing:
            logger.error(f"Registration failed: {cls.__name__} has resolver but missing: {missing}")
            raise TypeError(
                f"{cls.__name__} has resolve_multi_dimensional() but missing methods: {missing}. "
                f"Algorithms supporting both modes must implement all training/detection methods."
            )
    
    # Register
    name = instance.name.lower()
    ALGORITHM_REGISTRY[name] = instance
    logger.info(f"Registered algorithm: {name} (multi_dimensional={is_multi_dim}, supports_both={has_resolver})")
    
    _export_registry_if_available()
    return cls
```

#### Orchestrator Usage (No Fallbacks)

```python
class TrainingOrchestrator:
    def __post_init__(self):
        if self.bucket_profile:
            self.bucket_resolver = BucketResolver.from_dict(self.bucket_profile)
        
        # Resolve mode once at init
        algorithm = get_algorithm(self.algorithm_name)
        
        # Check if algorithm supports dynamic mode resolution
        if hasattr(algorithm, 'resolve_multi_dimensional'):
            self.is_multi_dimensional = algorithm.resolve_multi_dimensional(self.parameters)
        else:
            self.is_multi_dimensional = algorithm.is_multi_dimensional
    
    def train(self, observations: List[Dict], timestamp_field: str, percentile: float) -> Dict:
        algorithm = get_algorithm(self.algorithm_name)
        groups = self.group_by_bucket(observations, timestamp_field)
        
        buckets = {}
        for bucket_key, bucket_obs in groups.items():
            if self.is_multi_dimensional:
                baseline = algorithm.train_multi_dimensional(
                    observations=bucket_obs,
                    parameters=self.parameters,
                    percentile=percentile
                )
            else:
                baseline = self._train_single_dimensional(algorithm, bucket_obs, percentile)
            
            buckets[bucket_key] = {"baselines": baseline, "n_observations": len(bucket_obs)}
        
        return {"algorithm": self.algorithm_name, "is_multi_dimensional": self.is_multi_dimensional, "buckets": buckets, ...}
    
    def _train_single_dimensional(self, algorithm, observations, percentile) -> Dict:
        """Train each dimension independently using algorithm.train()."""
        result = {}
        for param in self.parameters:
            if not param.get("is_active", True):
                continue
            dimension = param["dimension"]
            values = [obs[dimension] for obs in observations if obs.get(dimension) is not None]
            if len(values) >= 3:
                result[dimension] = algorithm.train(values, percentile=percentile)
        return result
```

### Method Requirements Matrix

| `is_multi_dimensional` | `has resolve_multi_dimensional` | Required Methods |
|------------------------|--------------------------------|------------------|
| `False` | No | `train`, `detect` |
| `True` | No | `train_multi_dimensional`, `detect_multi_dimensional` |
| Either | Yes | ALL four core methods |

### Example Implementations

**ZScore (Single-Dimensional Only):**
```python
@register_algorithm
@dataclass
class ZScoreAlgorithm:
    @property
    def name(self) -> str:
        return "zscore"
    
    @property
    def is_multi_dimensional(self) -> bool:
        return False  # Always single-dimensional
    
    def train(self, values: List[float], **kwargs) -> Dict:
        # ... existing implementation
    
    def detect(self, value: float, baseline: Dict) -> Dict:
        # ... existing implementation
```

**KMeans (Multi-Dimensional Only):**
```python
@register_algorithm
@dataclass
class KMeansAlgorithm:
    @property
    def name(self) -> str:
        return "kmeans"
    
    @property
    def is_multi_dimensional(self) -> bool:
        return True  # Always multi-dimensional
    
    def train_multi_dimensional(self, observations, parameters, **kwargs) -> Dict:
        dimensions = [p["dimension"] for p in parameters if p.get("is_active", True)]
        # Build vectors, train KMeans
        ...
    
    def detect_multi_dimensional(self, observation, model, parameters) -> Dict:
        # Check distance to nearest centroid
        ...
```

**Isolation Forest (Supports Both - Dynamic):**
```python
@register_algorithm
@dataclass
class IsolationForestAlgorithm:
    @property
    def name(self) -> str:
        return "isolation_forest"
    
    @property
    def is_multi_dimensional(self) -> bool:
        return True  # Default mode
    
    def resolve_multi_dimensional(self, parameters: List[Dict]) -> bool:
        """Algorithm decides based on its own metadata."""
        for param in parameters:
            for meta in param.get("metadata", []):
                if meta.get("key") == "mode":
                    return meta.get("value") != "univariate"
        return True  # Default to multi-dimensional
    
    # Must implement ALL four methods since it supports both
    def train(self, values, **kwargs) -> Dict: ...
    def detect(self, value, baseline) -> Dict: ...
    def train_multi_dimensional(self, observations, parameters, **kwargs) -> Dict: ...
    def detect_multi_dimensional(self, observation, model, parameters) -> Dict: ...
```

### Why Keep Deferred Items

| Item | Future Use | Who Owns It |
|------|------------|-------------|
| `load_detection_observations` (Line 775) | Aggregates multi-dim observations for KMeans | Orchestrator |
| `detect_batch` methods | Optional batch processing optimization | Algorithm (optional method) |
| `percentile` hardcode (Line 175) | Each algorithm reads from its parameter's metadata | Algorithm (via `parameter.metadata`) |
| `min_points` hardcode (Line 230) | Algorithm-specific validation threshold | Algorithm (via `__algorithm_meta__` or metadata) |

### Key Takeaway: Separation of Concerns

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ORCHESTRATOR LAYER                                 │
│                                                                             │
│   Responsibilities:                                                          │
│   - Bucket grouping (by time context)                                       │
│   - Data preparation (per-dimension vs all-together based on mode)          │
│   - Calling correct algorithm method (train vs train_multi_dimensional)      │
│   - Storing baselines/models in correct format                               │
│                                                                             │
│   Does NOT know about:                                                       │
│   - percentile, multiplier, n_clusters, max_iterations, etc.                │
│   - Algorithm-specific parameters (each algorithm handles its own)           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            ALGORITHM LAYER                                   │
│                                                                             │
│   Responsibilities:                                                          │
│   - Declare is_multi_dimensional property                                    │
│   - Extract own metadata from parameters                                     │
│   - Implement train/detect (or train_multi_dimensional/detect_multi_dim)     │
│   - Return consistent result format (always include 'is_anomaly')            │
│                                                                             │
│   Owns:                                                                      │
│   - All algorithm-specific parameters (percentile, multiplier, etc.)         │
│   - Default values for missing metadata                                      │
│   - Validation of its own configuration                                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### What's Currently Missing in Orchestrator

The current `training_orchestrator.py` does NOT support the design above. Here's the gap analysis:

| Feature | Current State | Required for Part 7 |
|---------|---------------|---------------------|
| Check `is_multi_dimensional` property | ❌ Missing | ✅ At `__post_init__` |
| Check `resolve_multi_dimensional()` | ❌ Missing | ✅ Via `hasattr()` |
| Branch training logic by mode | ❌ Always calls same path | ✅ If/else based on mode |
| Branch detection logic by mode | ❌ Always calls same path | ✅ If/else based on mode |
| `_train_single_dimensional()` helper | ❌ Missing | ✅ New method |
| `_detect_single_dimensional()` helper | ❌ Missing | ✅ New method |
| Exploit algorithm's `detect_batch()` | ❌ Just loops internally | ✅ Check via `hasattr()` |

**Current state of orchestrator:**
```python
# training_orchestrator.py (today)
def train(self, observations, timestamp_field, percentile):
    # ALWAYS calls algorithm.train_multi_dimension() 
    # regardless of algorithm type - this is WRONG naming, 
    # it actually loops internally (single-dimensional behavior)
    ...
```

---

### Critical Design Clarification: Metadata is Algorithm's Responsibility

**WRONG approach (orchestrator handles metadata):**
```python
# ❌ DON'T DO THIS - orchestrator should not know about "percentile", "multiplier", etc.
def _train_single_dimensional(self, algorithm, bucket_obs, percentile):
    baseline = algorithm.train(values, percentile=percentile)  # Bad!
```

**CORRECT approach (algorithm reads its own metadata):**
```python
# ✅ DO THIS - orchestrator passes parameters, algorithm extracts what it needs
def _train_single_dimensional(self, algorithm, observations) -> Dict:
    """Train each dimension independently.
    
    Algorithm is responsible for:
    - Reading its own metadata from parameters
    - Extracting algorithm-specific settings (percentile, multiplier, etc.)
    """
    result = {}
    for param in self.parameters:
        if not param.get("is_active", True):
            continue
        dimension = param["dimension"]
        values = [obs[dimension] for obs in observations if obs.get(dimension) is not None]
        if len(values) >= 3:
            # Algorithm receives the FULL parameter dict, extracts its own metadata
            result[dimension] = algorithm.train(values, parameter=param)
    return result
```

**Algorithm implementation reads metadata:**
```python
# zscore.py
def train(self, values: List[float], parameter: Dict = None, **kwargs) -> Dict:
    # Algorithm extracts what it needs from metadata
    percentile = 99.5  # Default
    if parameter:
        for meta in parameter.get("metadata", []):
            if meta.get("key") == "percentile":
                percentile = float(meta.get("value", 99.5))
    
    # Now use percentile in training logic
    ...

# iqr.py  
def train(self, values: List[float], parameter: Dict = None, **kwargs) -> Dict:
    # IQR algorithm extracts multiplier
    multiplier = 1.5  # Default
    if parameter:
        for meta in parameter.get("metadata", []):
            if meta.get("key") == "multiplier":
                multiplier = float(meta.get("value", 1.5))
    
    # Now use multiplier in training logic
    ...
```

**Why this is better:**
1. Orchestrator doesn't need to know algorithm-specific parameters
2. New algorithms can add any metadata they need without orchestrator changes
3. Single source of truth: algorithm defines AND consumes its metadata
4. Clear responsibility boundary: orchestrator prepares data, algorithm processes it

---

### Critical Design Clarification: Data Preparation Responsibility

The Dispatcher/Orchestrator has ONE critical job before calling algorithm methods: **prepare the data correctly based on algorithm mode**.

**For Single-Dimensional Algorithms (ZScore, IQR):**
```
Observations: [{"ts": ..., "dim_A": 10, "dim_B": 20}, {"ts": ..., "dim_A": 15, "dim_B": 25}]
                                    ↓
                    Orchestrator extracts per dimension
                                    ↓
            dim_A → [10, 15]  (sent to algorithm.train())
            dim_B → [20, 25]  (sent to algorithm.train())
```

**For Multi-Dimensional Algorithms (KMeans, Isolation Forest):**
```
Observations: [{"ts": ..., "dim_A": 10, "dim_B": 20}, {"ts": ..., "dim_A": 15, "dim_B": 25}]
                                    ↓
                    Orchestrator keeps together as vectors
                                    ↓
            ALL → [[10, 20], [15, 25]]  (sent to algorithm.train_multi_dimensional())
```

**Orchestrator responsibilities:**
| Responsibility | Single-Dimensional | Multi-Dimensional |
|----------------|-------------------|-------------------|
| Group by bucket | ✅ Yes | ✅ Yes |
| Extract dimension values | ✅ Per-dimension loop | ❌ Algorithm handles |
| Filter by `is_active` | ✅ Per-dimension | ✅ Pass full parameters |
| Call algorithm method | `algorithm.train(values, parameter)` | `algorithm.train_multi_dimensional(observations, parameters)` |
| Store baseline | Per-dimension in result dict | Single model for all dimensions |

**The orchestrator MUST prepare data differently based on mode:**
```python
def train(self, observations: List[Dict], timestamp_field: str) -> Dict:
    algorithm = get_algorithm(self.algorithm_name)
    groups = self.group_by_bucket(observations, timestamp_field)
    
    buckets = {}
    for bucket_key, bucket_obs in groups.items():
        if self.is_multi_dimensional:
            # Multi-dim: Pass all observations, algorithm builds vectors internally
            baseline = algorithm.train_multi_dimensional(
                observations=bucket_obs,
                parameters=self.parameters
            )
        else:
            # Single-dim: Orchestrator extracts per-dimension, calls train() for each
            baseline = self._train_single_dimensional(algorithm, bucket_obs)
        
        buckets[bucket_key] = {"baselines": baseline, "n_observations": len(bucket_obs)}
    
    return {"algorithm": self.algorithm_name, "is_multi_dimensional": self.is_multi_dimensional, "buckets": buckets}
```

---

### Mode Must Be Known at Dispatcher Level

The **DADispatcher** itself needs to know the mode BEFORE calling orchestrators, because it determines the control flow:

**Current Detection Code (only works for single-dimensional):**
```python
# DADispatcher.detect_anomaly() - line ~443
for obs in observed_values:
    result = orchestrator.detect(observation=obs, ...)
```

**Required for Multi-Dimensional Support:**
```python
def detect_anomaly(config_id, serie_to_detect):
    ...
    # Resolve mode ONCE at dispatcher level
    algorithm = get_algorithm(alg_name)
    
    if hasattr(algorithm, 'resolve_multi_dimensional'):
        is_multi_dim = algorithm.resolve_multi_dimensional(alg_params)
    else:
        is_multi_dim = algorithm.is_multi_dimensional
    
    # Control flow depends on mode
    if is_multi_dim:
        # Multi-dimensional: pass ALL observations at once
        results = orchestrator.detect_batch_multi_dimensional(
            observations=observed_values,
            timestamp_field=timestamp_field
        )
        anomalies = [r for r in results if r.get("is_anomaly")]
    else:
        # Single-dimensional: loop through observations
        anomalies = []
        for obs in observed_values:
            result = orchestrator.detect(observation=obs, timestamp_field=timestamp_field)
            if result.get("is_anomaly"):
                anomalies.append(result)
```

**Same applies to training:**
```python
def run_training(config_id, observed_values, ...):
    ...
    algorithm = get_algorithm(alg_name)
    
    if hasattr(algorithm, 'resolve_multi_dimensional'):
        is_multi_dim = algorithm.resolve_multi_dimensional(alg_params)
    else:
        is_multi_dim = algorithm.is_multi_dimensional
    
    # Pass mode to orchestrator (it caches for internal use)
    orchestrator = TrainingOrchestrator(
        algorithm_name=alg_name,
        parameters=alg_params,
        bucket_profile=bucket_profile,
        is_multi_dimensional=is_multi_dim  # <-- NEW
    )
```

**Why Dispatcher must know:**
| Decision | Made By | Reason |
|----------|---------|--------|
| Loop vs batch call | Dispatcher | Control flow structure |
| Data preparation | Orchestrator | Extract per-dim vs pass all |
| Actual computation | Algorithm | Domain logic |

---

### Metadata Field Name Consistency

**Important:** The metadata field name varies by source:

| Data Flow | Source Collection | Field Name |
|-----------|-------------------|------------|
| Training | `anomaly_detection.training_config` | `algorithm_metadata` |
| Detection | `knowledge_base.kb_configs` | `metadata` |

Algorithms must handle both:
```python
def resolve_multi_dimensional(self, parameters: List[Dict]) -> bool:
    for param in parameters:
        # Support both field names
        meta_list = param.get("metadata") or param.get("algorithm_metadata", [])
        for meta in meta_list:
            if meta.get("key") == "mode" and meta.get("value") == "univariate":
                return False
    return True
```

---

## Part 8: Multi-Worker Architecture & Data Consistency

> **Status:** Design Complete - Critical for Production Scaling

### Problem Statement

With multiple Dispatcher workers, how do we ensure:
1. Multi-dimensional algorithms get COMPLETE data (all observations together)
2. No duplicate processing of the same observations
3. Data consistency across workers

### Design: One KB Config = One Worker (Option A + D Hybrid)

**Core Principle:** Parallelization happens at TWO levels with clear separation:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         HORIZONTAL SCALING                                   │
│                    (Dispatcher/Scheduler Layer)                              │
│                                                                             │
│   Parallelization by KB Config:                                             │
│   ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐                       │
│   │Worker 1 │  │Worker 2 │  │Worker 3 │  │Worker N │                       │
│   │ KB-001  │  │ KB-002  │  │ KB-003  │  │ KB-00N  │                       │
│   └─────────┘  └─────────┘  └─────────┘  └─────────┘                       │
│                                                                             │
│   - Each KB config assigned to exactly ONE worker                           │
│   - Workers claim configs, not individual observations                      │
│   - Load scales with number of KB configs                                   │
│   - One slow config doesn't block others                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         VERTICAL SCALING                                     │
│                        (Algorithm Layer)                                     │
│                                                                             │
│   Internal Parallelization (Algorithm decides):                             │
│   ┌─────────────────────────────────────────────────────────────────┐      │
│   │ ZScore Algorithm                                                 │      │
│   │ - Can parallelize across dimensions (thread pool)                │      │
│   │ - Can parallelize across buckets                                 │      │
│   │ - Each dimension independent → embarrassingly parallel           │      │
│   └─────────────────────────────────────────────────────────────────┘      │
│   ┌─────────────────────────────────────────────────────────────────┐      │
│   │ KMeans Algorithm                                                 │      │
│   │ - Cannot split dimensions (need vectors)                         │      │
│   │ - Can parallelize distance calculations internally               │      │
│   │ - Can use numpy/sklearn vectorized operations                    │      │
│   └─────────────────────────────────────────────────────────────────┘      │
│                                                                             │
│   Algorithm owns its internal performance optimization!                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Why This Design Works

**1. Data Consistency Guaranteed**
```python
# Worker claims ALL observations for a KB config
series = mongo.series.find({
    "metadata.kb_id": config_id,
    "metadata.mode": 1  # detection
})
# Worker processes complete dataset - no splits, no gaps
```

**2. Load Distribution is Natural**
- More KB configs = more parallelism
- Each KB config is independent workload unit
- No coordination needed between workers for same config

**3. Algorithm Performance is Algorithm's Responsibility**
```python
class ZScoreAlgorithm:
    def train(self, values: List[float], parameter: Dict) -> Dict:
        # Algorithm can use numpy vectorization
        # Algorithm can use multiprocessing for large datasets
        # Dispatcher doesn't care HOW, just calls train()
        ...

class KMeansAlgorithm:
    def train_multi_dimensional(self, observations, parameters) -> Dict:
        # Algorithm uses sklearn's parallel_backend
        # Algorithm optimizes its own computation
        ...
```

**4. Future: Algorithm Can Declare Partition Strategy**
```python
class AnomalyAlgorithm(Protocol):
    @property
    def partition_strategy(self) -> str:
        """How this algorithm can be partitioned across workers.
        
        Returns:
            - "none": Cannot partition, need all data (KMeans, DBSCAN)
            - "by_dimension": Can process dimensions independently (ZScore, IQR)
            - "by_time_window": Can process time buckets independently
        """
        ...
```

This is OPTIONAL and for future optimization. Default is "none" (safest).

### Worker Assignment Strategies

**Strategy 1: Static Assignment (Simplest)**
```python
# Config in environment or config file
WORKER_ID = os.environ.get("WORKER_ID", "0")
TOTAL_WORKERS = int(os.environ.get("TOTAL_WORKERS", "1"))

# Worker only processes configs where hash(config_id) % TOTAL_WORKERS == WORKER_ID
def should_process(config_id: str) -> bool:
    return hash(config_id) % TOTAL_WORKERS == int(WORKER_ID)
```

**Strategy 2: Dynamic Claiming (More Flexible)**
```python
# Worker claims config by setting a lock in MongoDB
def claim_config(config_id: str, worker_id: str) -> bool:
    result = mongo.config_locks.update_one(
        {"config_id": config_id, "locked_by": None},
        {"$set": {"locked_by": worker_id, "locked_at": datetime.utcnow()}},
        upsert=True
    )
    return result.modified_count > 0 or result.upserted_id is not None
```

**Strategy 3: Message Queue (Production Ready)**
```python
# Scheduler publishes config_ids to queue
# Workers consume from queue - exactly-once delivery
# RabbitMQ, Redis Streams, or Kafka
```

### Implications for Current Code

**No changes needed for single-worker deployment** - current code works.

**For multi-worker deployment, add:**
1. Worker ID configuration
2. Config claiming/assignment logic
3. Ensure change stream watchers don't duplicate across workers

### Summary Table

| Concern | Handled By | Strategy |
|---------|------------|----------|
| Which configs to process | Dispatcher/Scheduler | Static hash or dynamic claim |
| Complete data per config | MongoDB query | Filter by `config_id` |
| Internal parallelism | Algorithm | Thread pool, numpy, sklearn |
| Duplicate detection | Worker assignment | One worker per config |
| Slow config blocking | Worker isolation | Each worker independent |

---

### Deferred Reason

- Requires KMeans implementation (another team member)
- Current single-dimensional algorithms work fine
- Changes to orchestrator and interface should be done together with first multi-dimensional algorithm
- Multi-worker deployment not yet required
