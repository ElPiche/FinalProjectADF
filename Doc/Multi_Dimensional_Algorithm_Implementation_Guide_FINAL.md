# Multi-Dimensional Algorithm Implementation Guide (FINAL)

> **Created**: December 3, 2025  
> **Status**: ✅ Design Complete - Ready for Implementation  
> **Scope**: Prepare codebase for KMeans and future multi-dimensional algorithms

---

## 1. Goal

Enable the anomaly detection system to support **multi-dimensional algorithms** (KMeans, DBSCAN) alongside existing **single-dimensional algorithms** (ZScore, IQR).

| Type | How It Works | Examples |
|------|--------------|----------|
| **Single-Dimensional** | Each dimension has its own baseline | ZScore, IQR |
| **Multi-Dimensional** | All dimensions form vectors → single model | KMeans, DBSCAN |

---

## 2. Algorithm Interface

### 2.1 Required Properties

```
Every algorithm MUST have:
├── name: str              → "zscore", "kmeans", etc.
└── is_multi_dimensional: bool → False for ZScore, True for KMeans
```

### 2.2 Required Methods

```
IF is_multi_dimensional = False:
├── train(values: List[float], parameter: Dict) → baseline
└── detect(value: float, baseline: Dict, parameter: Dict) → result

IF is_multi_dimensional = True:
├── train_multi_dimensional(observations: List[Dict], parameters: List[Dict]) → model
└── detect_multi_dimensional(observation: Dict, model: Dict, parameters: List[Dict]) → result
```

### 2.3 Bucketing Properties (New)

```
Optional properties (with defaults):
├── supports_bucketing: bool = True    → Train per time-bucket? (False for KMeans)
└── min_training_samples: int = 3      → Minimum data for training (50 for KMeans)
```

**Note:** Algorithm parameters are USER-OVERRIDABLE via parameter metadata.
This pattern applies to ALL algorithm-specific settings (`min_training_samples`, `percentile`, `n_clusters`, etc.):

```
Resolution order (same for all parameters):
├── 1. Check parameter.metadata for key (e.g., "min_training_samples", "percentile")
│      └── IF found → use user's value
└── 2. ELSE → use algorithm's default
```

### 2.4 Registration Validation (Fail-Fast)

```
ON ALGORITHM REGISTRATION:
├── Check name exists
├── Check is_multi_dimensional exists
├── IF multi-dimensional:
│   └── REQUIRE train_multi_dimensional, detect_multi_dimensional
├── ELSE:
│   └── REQUIRE train, detect
└── IF has resolve_multi_dimensional():
    └── REQUIRE ALL four methods
```

---

## 3. Metadata Handling

### Core Principle: Algorithm Reads Its Own Metadata

```
┌─────────────────────────────────────────────────────────────┐
│  Orchestrator does NOT extract algorithm-specific params    │
│  Orchestrator passes full `parameter` dict to algorithm     │
│  Algorithm extracts what it needs (percentile, n_clusters)  │
└─────────────────────────────────────────────────────────────┘
```

**Example:**
```
ZScore.train(values, parameter):
    percentile = 99.5  # default
    FOR meta IN parameter.metadata:
        IF meta.key == "percentile":
            percentile = meta.value
    # use percentile...
```

**Field Name Varies by Source:**
| Source | Field Name |
|--------|------------|
| training_config | `algorithm_metadata` |
| kb_configs | `metadata` |

→ Always check: `param.get("metadata") or param.get("algorithm_metadata", [])`

**User-Overridable Parameters:**
| Parameter | Algorithm Default | User Override Key |
|-----------|-------------------|-------------------|
| `min_training_samples` | ZScore: 3, KMeans: 50 | `"min_training_samples"` |
| `percentile` | 99.5 | `"percentile"` |
| `n_clusters` | 5 | `"n_clusters"` |

---

## 4. Control Flow

### 4.1 Mode Resolution (Dispatcher Level)

```
┌─────────────────────────────────────────────────────────────┐
│                    DISPATCHER                                │
├─────────────────────────────────────────────────────────────┤
│  1. Get algorithm by name                                   │
│  2. IF algorithm has resolve_multi_dimensional():           │
│        is_multi_dim = algorithm.resolve_multi_dimensional() │
│     ELSE:                                                   │
│        is_multi_dim = algorithm.is_multi_dimensional        │
│  3. Pass is_multi_dim to Orchestrator                       │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Training Flow (Orchestrator Level)

```
TRAINING ORCHESTRATOR:
┌─────────────────────────────────────────────────────────────┐
│  INPUT: observations, is_multi_dimensional, parameters      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  0. Resolve min_training_samples:                           │
│     ├── Check parameters metadata for override              │
│     └── Else use algorithm.min_training_samples             │
│                                                             │
│  1. Train GLOBAL model (all data)                           │
│                                                             │
│  2. IF algorithm.supports_bucketing AND bucket_profile:     │
│     ├── Group observations by bucket                        │
│     └── FOR each bucket:                                    │
│         ├── IF len(bucket) >= min_training_samples:         │
│         │   └── Train bucket-specific model                 │
│         └── ELSE:                                           │
│             └── Use global model as fallback                │
│     ELSE:                                                   │
│     └── Store global model in "global" bucket               │
│                                                             │
│  3. RETURN {buckets, global_fallback, metadata}             │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 Detection Flow (Orchestrator Level)

```
DETECTION ORCHESTRATOR:
┌─────────────────────────────────────────────────────────────┐
│  INPUT: observation, is_multi_dimensional, trained_model    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Resolve bucket_context from timestamp (ALWAYS)          │
│                                                             │
│  2. IF supports_bucketing:                                  │
│        baseline = model.buckets[bucket_context]             │
│     ELSE:                                                   │
│        baseline = model.buckets["global"]                   │
│                                                             │
│  3. IF is_multi_dimensional:                                │
│        result = algorithm.detect_multi_dimensional(...)     │
│     ELSE:                                                   │
│        result = algorithm.detect(...) per dimension         │
│                                                             │
│  4. Tag result with bucket_context (for Kibana analysis)    │
│                                                             │
│  5. RETURN result                                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. Bucketing System

### Three Separate Concerns

```
┌─────────────────────────────────────────────────────────────┐
│  1. MODELING (algorithm decides via supports_bucketing)     │
│     ├── True:  Train separate model per bucket (ZScore)     │
│     └── False: Train single global model (KMeans)           │
├─────────────────────────────────────────────────────────────┤
│  2. CONTEXT (always on)                                     │
│     └── Every detection tagged with bucket_context          │
│         "This anomaly happened during workday_14"           │
├─────────────────────────────────────────────────────────────┤
│  3. PARALLELIZATION (when bucketing enabled)                │
│     └── Orchestrator can parallelize bucket training        │
└─────────────────────────────────────────────────────────────┘
```

### Storage Format

**With bucketing (ZScore):**
```json
{
  "supports_bucketing": true,
  "buckets": {
    "workday_14": {"baselines": {"dim_A": {...}}, "n_observations": 150},
    "weekend_10": {"baselines": {"dim_A": {...}}, "n_observations": 45}
  },
  "global_fallback": {"dim_A": {...}}
}
```

**Without bucketing (KMeans):**
```json
{
  "supports_bucketing": false,
  "buckets": {
    "global": {"baselines": {"centroids": [...]}, "n_observations": 1000}
  },
  "global_fallback": {"centroids": [...]}
}
```

---

## 6. Multi-Worker Architecture

### 6.1 Core Principle: One KB Config = One Worker

```
┌─────────────────────────────────────────────────────────────┐
│                   DISPATCHER MANAGER                         │
│  ├── Watches kb_configs for active configurations           │
│  ├── Spawns one KBWorker per active KB config               │
│  └── Stops workers when KB config becomes inactive          │
└─────────────────────────────────────────────────────────────┘
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌──────────┐    ┌──────────┐    ┌──────────┐
    │ KBWorker │    │ KBWorker │    │ KBWorker │
    │  KB-001  │    │  KB-002  │    │  KB-003  │
    │          │    │          │    │          │
    │ Filtered │    │ Filtered │    │ Filtered │
    │ Change   │    │ Change   │    │ Change   │
    │ Stream   │    │ Stream   │    │ Stream   │
    └──────────┘    └──────────┘    └──────────┘
```

### 6.2 Per-KB Change Stream Filter

```
MongoDB Change Stream Pipeline:
{
  "$match": {
    "operationType": "insert",
    "fullDocument.kbId": <this_worker's_kb_id>,
    "fullDocument.mode": 1  // detection mode
  }
}
```

**Why filtered streams?**
- Prevents duplicate processing across workers
- Each worker gets ONLY its KB's data
- No race conditions or coordination needed

---

## 7. Observation Buffering (Multi-Dimensional Detection)

### 7.1 The Problem

```
Extractor writes per-dimension documents:
┌─────────────────────────────────────────────┐
│  {kbId, timestamp: T1, dim: "cpu", value: 45}      │
│  {kbId, timestamp: T1, dim: "memory", value: 78}   │
│  {kbId, timestamp: T1, dim: "requests", value: 120}│
└─────────────────────────────────────────────┘

KMeans needs complete vectors:
┌─────────────────────────────────────────────┐
│  observation T1: {cpu: 45, memory: 78, requests: 120}  │
└─────────────────────────────────────────────┘
```

### 7.2 Buffering Solution

```
KBWorker Buffer:
┌─────────────────────────────────────────────────────────────┐
│  buffer = {                                                  │
│    timestamp_T1: {                                          │
│      "_first_seen": 1701619200.0,                           │
│      "_dims": {"cpu": 45, "memory": 78}  // incomplete      │
│    },                                                        │
│    timestamp_T2: {                                          │
│      "_first_seen": 1701619200.1,                           │
│      "_dims": {"cpu": 50, "memory": 80, "requests": 115}    │
│    }                                                         │
│  }                                                           │
└─────────────────────────────────────────────────────────────┘

ON EACH INCOMING DOCUMENT:
├── Add dimension value to buffer[timestamp]
├── IF buffer[timestamp] has ALL expected dimensions:
│   ├── Extract complete observation
│   ├── Delete from buffer
│   └── Run detection
└── ELSE: wait for more dimensions
```

### 7.3 ⚠️ CRITICAL: Discard Incomplete Observations

```
┌─────────────────────────────────────────────────────────────┐
│  SAFETY RULE: NEVER process partial vectors                  │
│                                                             │
│  IF buffer entry age > 500ms:                               │
│  ├── Log warning with missing dimensions                    │
│  └── DELETE from buffer (do NOT process)                    │
│                                                             │
│  WHY: Partial vectors cause FALSE POSITIVES                 │
│  - Missing dims → vector looks abnormal                      │
│  - KMeans distance inflated by zeros/defaults               │
│  - Better to miss anomaly than report false one             │
└─────────────────────────────────────────────────────────────┘
```

### 7.4 Why 500ms Timeout Works

```
Timeline:
├── 0ms:   Extractor starts page insert (3000 docs)
├── 50ms:  Page insert complete
├── 100ms: Worker receives all events for page
├── ...
├── 500ms: Timeout - any incomplete observation is orphaned
           (indicates bug, not normal operation)
```

---

## 8. Implementation Checklist

### Phase 1: Algorithm Interface
- [ ] Add `is_multi_dimensional` property to Protocol
- [ ] Add `supports_bucketing` property (default: True)
- [ ] Add `min_training_samples` property (default: 3)
- [ ] Update `register_algorithm` with validation

### Phase 2: Update Existing Algorithms
- [ ] `zscore.py`: Add properties, update train/detect to accept `parameter`
- [ ] `iqr.py`: Same changes
- [ ] `mock.py`: Same changes

### Phase 3: Orchestrator Changes
- [ ] Add `is_multi_dimensional` field
- [ ] Add `_train_single_dimensional()` method
- [ ] Check `supports_bucketing` and `min_training_samples`
- [ ] Always tag detections with `bucket_context`

### Phase 4: Dispatcher Changes
- [ ] Resolve mode ONCE before orchestrator
- [ ] Pass `is_multi_dimensional` to orchestrator

### Phase 5: Unit Testing
- [ ] Registration validation tests
- [ ] Single-dimensional flow tests
- [ ] Bucket context tagging tests

### Phase 6: Per-KB Worker Architecture
- [ ] Create `KBWorker` class with filtered change stream
- [ ] Create `DispatcherManager` for worker lifecycle
- [ ] Implement worker spawn/stop on config changes

### Phase 7: Observation Buffering
- [ ] Add buffer dict indexed by timestamp
- [ ] Implement dimension collection and completeness check
- [ ] **CRITICAL**: Implement discard for incomplete observations
- [ ] Add cleanup loop (100ms interval, 500ms timeout)

### Phase 8: Integration Testing
- [ ] Multi-dimensional detection with buffering
- [ ] Incomplete observation discard behavior
- [ ] Multiple KBWorkers in parallel

---

## 9. Algorithm Examples

### ZScore (Single-Dimensional, Supports Bucketing)

```
ZScoreAlgorithm:
├── name = "zscore"
├── is_multi_dimensional = False
├── supports_bucketing = True
├── min_training_samples = 3
├── train(values, parameter):
│   ├── Extract percentile from parameter.metadata
│   ├── Calculate mean, std, threshold
│   └── Return baseline dict
└── detect(value, baseline, parameter):
    ├── Calculate z_score
    ├── Compare to threshold
    └── Return {is_anomaly, z_score, ...}
```

### KMeans (Multi-Dimensional, No Bucketing)

```
KMeansAlgorithm:
├── name = "kmeans"
├── is_multi_dimensional = True
├── supports_bucketing = False
├── min_training_samples = 50
├── train_multi_dimensional(observations, parameters):
│   ├── Extract n_clusters from parameters metadata
│   ├── Build feature vectors from observations
│   ├── Fit KMeans model
│   ├── Calculate distance threshold
│   └── Return {centroids, threshold, dimensions}
└── detect_multi_dimensional(observation, model, parameters):
    ├── Build vector from observation
    ├── Calculate distance to nearest centroid
    ├── Compare to threshold
    └── Return {is_anomaly, distance, nearest_cluster}
```

---

## 10. Key Design Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Mode resolution | Dispatcher level | Single point, before control flow branching |
| Metadata extraction | Algorithm responsibility | Algorithms know their own parameters |
| Bucketing opt-in | `supports_bucketing` property | KMeans needs all data, not sparse buckets |
| Worker model | One KB = One Worker | Data consistency for multi-dimensional |
| Change stream | Filtered per KB | No duplicates, no coordination |
| Incomplete observations | DISCARD | Avoid false positives from partial vectors |
| Buffer timeout | 500ms | Batches arrive in milliseconds |

---

## References

- Detailed implementation: `Doc/Multi_Dimensional_Algorithm_Implementation_Guide.md`
- Design rationale: `Doc/TODO_Implementation_Plan.md` Parts 5-8
- Algorithm interface: `MotorDA/Dispatcher/algorithm_interface.py`
- Orchestrators: `MotorDA/Dispatcher/training_orchestrator.py`
- Dispatcher: `MotorDA/Dispatcher/DADispatcher.py`
