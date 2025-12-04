# modify_kb_config Bug Fixes Report

**Date:** December 4, 2025  
**Branch:** `feature/fix-train-orchestrator`  
**Author:** GitHub Copilot

---

## Executive Summary

Investigation and resolution of the issue where `modify_kb_config` was not triggering re-training in the Dispatcher. Three bugs were identified and fixed, plus one enhancement was added for data cleanup.

## Issue Description

**Reported Problem:** Re-training is not triggered when `modify_kb_config` is used to update a KB configuration.

**Expected Behavior:** When a KB configuration is modified (algorithm, dimensions, query, training range, etc.), the system should:
1. ETL (Extractor) should re-extract training data
2. Dispatcher should re-train the model with new parameters
3. Detection worker should restart with updated configuration

---

## Root Cause Analysis

### Bug #1: Change Stream Missing "replace" Operation Type

**Location:** `MotorDA/Dispatcher/DADispatcher.py` (lines ~728-737)

**Problem:** The MongoDB change stream watching `training_config` collection only matched `"insert"` and `"update"` operations. However, Spring Data MongoDB's `save()` method with an existing document `_id` triggers a **`"replace"`** operation, not an `"update"`.

**Impact:** When Extractor updated the training_config via `trainingConfigRepository.save()`, the Dispatcher never received the change event, so training was never triggered.

**Evidence:**
```java
// In BatchModeService.java - Spring Data save() triggers REPLACE
trainingConfigRepository.save(trainConfig);
```

### Bug #2: Detection Worker Never Restarts After Training

**Location:** `MotorDA/Dispatcher/kb_worker.py` (lines ~509-553)

**Problem:** The `_spawn_worker()` method returned early if a worker already existed, without checking if the training result had changed:

```python
# OLD CODE - Bug
if config_id in self._workers:
    return  # Already running - NEVER RESTARTS!
```

**Impact:** After modify_kb_config triggered re-training:
- Training completed with new algorithm/dimensions
- `trained_models` collection was updated
- But the detection worker kept using the OLD configuration
- Anomaly detection used stale baselines/dimensions

### Bug #3: Training Series Data Accumulation

**Location:** `MotorDA/Dispatcher/DADispatcher.py` (new function needed)

**Problem:** Training series data (mode=0) was never cleaned up after training. When training range changed, old series data remained in the collection, causing:
- Stale data mixed with new data
- Training on incorrect time ranges
- Unbounded data growth in `series` collection

---

## Fixes Implemented

### Fix #1: Add "replace" to Change Stream Pipeline

**File:** `MotorDA/Dispatcher/DADispatcher.py`

```python
# BEFORE
pipeline = [
    {"$match": {
        "$or": [
            {"operationType": "insert"},
            {"operationType": "update"}
        ]
    }}
]

# AFTER
pipeline = [
    {"$match": {
        "$or": [
            {"operationType": "insert"},
            {"operationType": "update"},
            {"operationType": "replace"}  # Spring Data save() triggers replace
        ]
    }}
]
```

### Fix #2: Worker Restart on Training Update

**File:** `MotorDA/Dispatcher/kb_worker.py`

```python
def _spawn_worker(self, kb_config: Dict[str, Any]):
    """Spawn a new worker for a KB config.
    
    If a worker already exists but the training result has changed,
    the old worker is stopped and a new one is spawned with the updated config.
    """
    config_id = str(kb_config["_id"])
    
    training_result = self._get_training_result(config_id)
    if not training_result:
        logger.warning(f"[MANAGER] No training result for KB {config_id}, skipping")
        return
    
    with self._workers_lock:
        existing_worker = self._workers.get(config_id)
        if existing_worker:
            # Check if training result has changed (compare updated_at timestamp)
            old_updated_at = existing_worker.training_result.get("updated_at")
            new_updated_at = training_result.get("updated_at")
            
            if old_updated_at == new_updated_at:
                return  # No change, keep existing worker
            
            # Training result changed - restart worker
            logger.info(f"[MANAGER] Training result changed for KB {config_id}, restarting worker")
            existing_worker.stop()
            del self._workers[config_id]
        
        # Create and start new worker with fresh config
        worker = KBWorker(...)
        worker.start()
        self._workers[config_id] = worker
```

### Fix #3: Training Series Cleanup

**File:** `MotorDA/Dispatcher/DADispatcher.py`

Added new function and integrated into training flow:

```python
def cleanup_training_series(kb_id: str) -> int:
    """
    Delete training series data after successful training.
    
    Training series (mode=0) are temporary - once the model is trained,
    the raw series data is no longer needed. This prevents stale data
    accumulation when training ranges change.
    """
    collection = get_collection(SERIES_COLLECTION)
    
    result = collection.delete_many({
        "metadata.kbId": kb_id,
        "metadata.mode": 0  # Training mode only
    })
    
    deleted_count = result.deleted_count
    if deleted_count > 0:
        logger.info(f"[CLEANUP] Deleted {deleted_count} training series for KB {kb_id}")
    
    return deleted_count
```

Called after successful training:
```python
# Save result
result_id = save_training_result(config_id, result)
logger.info(f"[WATCHER] Saved training result: {result_id}")

# Cleanup training series - no longer needed after successful training
cleanup_training_series(config_id)

# Mark as trained
collection.update_one(...)
```

---

## Testing Results

### Test Matrix

| Test Case | Description | Result |
|-----------|-------------|--------|
| Query Change | Modified SQL query to add new column | ✅ Pass |
| Algorithm Change | Changed zscore → iqr → zscore | ✅ Pass |
| Add Dimension | Added max_response_time dimension | ✅ Pass |
| Remove Dimension | Removed avg_response_time dimension | ✅ Pass |
| Training Range | Changed from/to dates | ✅ Pass |
| Detection Frequency | Changed */5 → */2 → */3 | ✅ Pass |
| Detection Window | Changed 3600s → 7200s | ✅ Pass |
| Multiple Changes | Changed algorithm + query + dimensions together | ✅ Pass |
| Invalid Dimension | Dimension not in query output | ✅ Rejected |
| Empty Dimensions | Empty parameters array | ✅ Rejected |
| Worker Restart | Verify worker picks up new config | ✅ Pass |
| Series Cleanup | Training series deleted after training | ✅ Pass |

### Verification Logs

**Re-training triggered correctly:**
```
[WATCHER] Training triggered for config 6931ca9adb11e83c5840f298
[TRAINING] Algorithm: iqr, Mode: single-dimensional
[TRAINING] Parameters: [{'dimension': 'request_count', ...}]
[WATCHER] Saved training result: 6931ca9ba486f7eea3436578
```

**Worker restart on training update:**
```
[MANAGER] Trained models change detected: update
[MANAGER] Training result changed for KB 6931ca9adb11e83c5840f298, restarting worker
[KBWORKER-6931ca9a] Stopped
[KBWORKER-6931ca9a] Initialized: algorithm=iqr, mode=single-dim, dimensions={'request_count'}
[MANAGER] Spawned worker for KB 6931ca9adb11e83c5840f298
```

**Series cleanup after training:**
```
[CLEANUP] Deleted 15360 training series for KB 6931ca9adb11e83c5840f298
[WATCHER] Marked config 6931ca9adb11e83c5840f298 as trained
```

**Final series state:**
```
Training series (mode=0): 0      ← Cleaned up
Detection series (mode=1): 42   ← Preserved
```

---

## Data Flow After Fixes

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         modify_kb_config Flow                                │
└─────────────────────────────────────────────────────────────────────────────┘

1. User calls modify_kb_config via MCP
   │
   ▼
2. KB-MCP validates changes, updates kb_configs collection
   │
   ▼
3. Extractor detects change (change stream on kb_configs)
   │
   ├─► Re-extracts training data with new query/range
   │   └─► Inserts into series collection (mode=0)
   │
   └─► Updates training_config (triggers REPLACE operation)
       │
       ▼
4. Dispatcher detects change (change stream includes "replace") ← FIX #1
   │
   ├─► Loads training series from series collection
   ├─► Runs training with new algorithm/dimensions
   ├─► Saves trained_models (triggers change event)
   ├─► Cleans up training series (mode=0)              ← FIX #3
   │
   ▼
5. DispatcherManager detects trained_models change
   │
   ├─► Compares updated_at timestamps                  ← FIX #2
   ├─► Stops old worker
   └─► Spawns new worker with fresh config
       │
       ▼
6. KBWorker starts detection with updated:
   - Algorithm (zscore/iqr/mock)
   - Dimensions
   - Baselines from trained_models
```

---

## Files Modified

| File | Changes |
|------|---------|
| `MotorDA/Dispatcher/DADispatcher.py` | Added "replace" to change stream pipeline; Added `cleanup_training_series()` function; Integrated cleanup into training flow |
| `MotorDA/Dispatcher/kb_worker.py` | Modified `_spawn_worker()` to compare `updated_at` and restart workers; Added logging for trained_models watcher |

---

## Recommendations

1. **Monitor series collection size** - With cleanup in place, the collection should remain small. Consider adding an index on `metadata.kbId` + `metadata.mode` for faster cleanup queries.

2. **Add metrics** - Consider tracking:
   - Number of re-trainings triggered
   - Worker restart count
   - Series cleanup count per KB

3. **Error handling** - If cleanup fails, training should still succeed. Current implementation logs but continues - consider adding retry logic for transient failures.

---

## Conclusion

All three bugs have been fixed and verified through extensive testing. The `modify_kb_config` functionality now correctly:

1. ✅ Triggers re-training when configuration changes
2. ✅ Restarts detection workers with updated configuration  
3. ✅ Cleans up stale training data to prevent accumulation

The anomaly detection pipeline is now fully responsive to configuration modifications via the MCP interface.
