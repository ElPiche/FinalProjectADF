# Session Bug Fixes & Improvements - November 28, 2025

**Date:** November 28, 2025  
**Branch:** `feature/big-bucketing-feature`  
**Author:** GitHub Copilot & Elinzar  

---

## Executive Summary

This document details the bug fixes and improvements made during the development session on November 28, 2025. The session focused on fixing critical bugs related to field naming consistency, dashboard naming, anomaly index derivation, and metadata structure across the multi-service anomaly detection framework.

---

## Table of Contents

1. [Issues Addressed](#1-issues-addressed)
2. [Source Index Field Rename](#2-source-index-field-rename)
3. [Dashboard Naming Fix](#3-dashboard-naming-fix)
4. [Anomaly Index Naming Fix](#4-anomaly-index-naming-fix)
5. [Metadata Field Name Fix](#5-metadata-field-name-fix)
6. [Schema Changes](#6-schema-changes)
7. [End-to-End Verification](#7-end-to-end-verification)
8. [File Changes Summary](#8-file-changes-summary)
9. [Docker Commands](#9-docker-commands)

---

## 1. Issues Addressed

| Issue | Severity | Status |
|-------|----------|--------|
| Confusing `database_index` field name | Medium | ✅ Fixed |
| Dashboard named after anomaly index instead of source | High | ✅ Fixed |
| Redundant anomaly index suffix (`_anomalies_result_anomalies`) | High | ✅ Fixed |
| Dispatcher `KeyError: 'value'` crash | Critical | ✅ Fixed |

---

## 2. Source Index Field Rename

### Problem

The field `database_index` was confusingly named and its purpose was unclear. It was meant to identify the source Elasticsearch index being monitored for anomalies (e.g., `app-logs`), but the name suggested it might be related to database operations.

### Solution

Renamed the field from `database_index` to `source_index` across all services for clarity.

### Changes by Service

#### KB-MCP (Python)

**`MCP/KB-MCP/models.py`:**
```python
# Before
database_index: Optional[str] = Field(default=None, description="...")

# After
source_index: Optional[str] = Field(
    default=None, 
    description="Source Elasticsearch index being monitored (e.g., 'app-logs'). Required."
)
```

**`MCP/KB-MCP/mcp_tools.py`:**
```python
# Updated function signatures
async def create_da_config(
    ...
    source_index: str = Field(description="Source Elasticsearch index being monitored"),
    ...
)

async def modify_kb_config(
    ...
    source_index: Optional[str] = None,
    ...
)
```

#### Extractor (Java Spring Boot)

**`extractor/.../entity/kb/KbMongo.java`:**
```java
// Before
@Field("database_index")
private String databaseIndex;

// After
@Field("source_index")
private String sourceIndex;
```

**`extractor/.../dto/CreateMappingRequestDto.java`:**
```java
// Simplified DTO
public class CreateMappingRequestDto {
    @JsonProperty("kbId")
    private String kbId;
    
    @JsonProperty("sourceIndex")
    private String sourceIndex;
}
```

#### Anomalies Insights Module (Java Spring Boot)

**`anomalies-insights-module/.../entity/IndexKbIdMapping.java`:**
```java
// Before
@Field(name = "indexName")
private String indexName;

// After
@Field(name = "sourceIndex")
private String sourceIndex;

@Field(name = "anomalyIndex")
private String anomalyIndex;  // NEW: Stores derived anomaly index
```

---

## 3. Dashboard Naming Fix

### Problem

Dashboards were being named after the anomaly result index instead of the source Elasticsearch index being monitored.

**Before:**
```
Dashboard - app-logs_anomalies_result_anomalies
SavedSearch - app-logs_anomalies_result_anomalies
```

**Expected:**
```
Dashboard - app-logs
SavedSearch - app-logs
```

### Solution

Updated the dashboard creation logic to use the source index name for the dashboard title.

**`anomalies-insights-module/.../service/InsightsService.java`:**
```java
public void createKbMapping(IndexKbIdMapping kbIdMapping) throws Exception {
    // Source index (e.g., "app-logs") - used for dashboard naming
    String sourceIndex = kbIdMapping.getSourceIndex();
    
    // Derive anomaly output index from source
    String anomalyIndex = sanitizeIndexName(sourceIndex) + "_anomalies";
    kbIdMapping.setAnomalyIndex(anomalyIndex);

    // Create dashboard with SOURCE index name (what we're monitoring)
    String dashId = kibanaService.createDashboardWithEmbeddedLens(
        "Dashboard - " + sourceIndex,  // ← Uses source index
        dataViewId, 
        ssId
    );
    
    // Create saved search with SOURCE index name
    String ssId = kibanaService.createSavedSearch(
        dataViewId, 
        "SavedSearch - " + sourceIndex  // ← Uses source index
    );
}
```

### Result

| Component | Before | After |
|-----------|--------|-------|
| Dashboard Title | `Dashboard - app-logs_anomalies_result_anomalies` | `Dashboard - app-logs` |
| SavedSearch Title | `SavedSearch - app-logs_anomalies_result_anomalies` | `SavedSearch - app-logs` |

---

## 4. Anomaly Index Naming Fix

### Problem

The anomaly output index was being named with redundant suffixes due to the `normalizeIndexName()` method automatically appending `_anomalies_result`, and then additional code appending `_anomalies`.

**Before:**
```
app-logs_anomalies_result_anomalies
```

**Expected:**
```
app-logs_anomalies
```

### Root Cause

```java
// Old normalizeIndexName() method
private String normalizeIndexName(String rawName) {
    // ... sanitization ...
    
    // f) agregar sufijo _anomalies_result si no lo tiene
    if (!normalized.endsWith("_anomalies_result")) {
        normalized = normalized + "_anomalies_result";  // ← Problem!
    }
    
    return normalized;
}

// Then in createKbMapping():
String anomalyIndex = normalizeIndexName(sourceIndex) + "_anomalies";  // ← Double suffix!
```

### Solution

Created a new `sanitizeIndexName()` method that only performs name sanitization without adding any suffix.

**`anomalies-insights-module/.../service/InsightsService.java`:**
```java
/**
 * Sanitize an index name for Elasticsearch without adding any suffix.
 * Used for preparing source index names before appending _anomalies.
 */
private String sanitizeIndexName(String rawName) {
    if (rawName == null || rawName.isBlank()) {
        throw new IllegalArgumentException("Index name cannot be null or empty");
    }

    // a) minúsculas
    String normalized = rawName.toLowerCase(Locale.ROOT);

    // b) reemplazar espacios y separadores peligrosos por guion
    normalized = normalized.replaceAll("[\\s,:*?\"<>|/\\\\]+", "-");

    // c) quitar caracteres no permitidos (solo a-z0-9-_)
    normalized = normalized.replaceAll("[^a-z0-9-_]", "");

    // d) evitar prefijos reservados
    if (normalized.startsWith("-") || normalized.startsWith("+") || normalized.startsWith("_")) {
        normalized = "idx" + normalized;
    }

    // e) evitar nombres reservados
    if (normalized.equals(".") || normalized.equals("..")) {
        normalized = "idx-" + normalized;
    }

    // f) limitar longitud (leave room for _anomalies suffix)
    if (normalized.length() > 245) {
        normalized = normalized.substring(0, 245);
    }

    return normalized;  // NO suffix added!
}
```

### Result

| Source Index | Before | After |
|--------------|--------|-------|
| `app-logs` | `app-logs_anomalies_result_anomalies` | `app-logs_anomalies` |
| `My Index!` | `my-index_anomalies_result_anomalies` | `my-index_anomalies` |

---

## 5. Metadata Field Name Fix

### Problem

The dispatcher was crashing with `KeyError: 'value'` when parsing algorithm metadata.

**Error:**
```
[watch_kb_changes] Unexpected error: 'value'

Traceback (most recent call last):
  File "/MotorDA/Dispatcher/DADispatcher.py", line 173, in <dictcomp>
    ov["dimension"]: {am["key"]: am["value"]
                                 ~~^^^^^^^^^
KeyError: 'value'
```

### Root Cause

Field name mismatch across services:

| Service | Field Name | Status |
|---------|------------|--------|
| KB-MCP (Python) | `values` (plural) | Source of truth |
| Extractor (Java) | `value` (singular) | ❌ Mismatch |
| Dispatcher (Python) | `value` (singular) | ❌ Mismatch |

**KB-MCP stored:**
```json
{"key": "percentile", "values": "99.5"}
```

**Dispatcher expected:**
```json
{"key": "percentile", "value": "99.5"}
```

### Solution

Updated both Java extractor and Python dispatcher to use `values` (plural).

**`extractor/.../entity/KeyValuePair.java`:**
```java
// Before
@NoArgsConstructor
@Getter
@Setter
@AllArgsConstructor
public class KeyValuePair{
    String key;
    Object value;  // ← Wrong
}

// After
@NoArgsConstructor
@Getter
@Setter
@AllArgsConstructor
public class KeyValuePair{
    String key;
    Object values;  // ← Fixed
}
```

**`MotorDA/Dispatcher/DADispatcher.py`:**
```python
# Before
observed_values={
    ov["dimension"]: {am["key"]: am["value"]  # ← Crashed
                      for am in ov["algorithm_metadata"]}
    for ov in a["parameters"]["observed_values"]
},

# After (with backward compatibility)
observed_values={
    ov["dimension"]: {am["key"]: am.get("values", am.get("value"))  # ← Fixed
                      for am in ov["algorithm_metadata"]}
    for ov in a["parameters"]["observed_values"]
},
```

### Result

Training config now correctly stores and reads:
```json
{
  "algorithm_metadata": [
    {"key": "percentile", "values": "99.5"}
  ]
}
```

---

## 6. Schema Changes

### 6.1 KBConfig (MongoDB: `knowledge_base.kb_configs`)

**Field Renamed:**
```json
{
  // Before
  "database_index": "app-logs",
  
  // After
  "source_index": "app-logs"
}
```

### 6.2 Index Mapping (Elasticsearch: `index_kb_id_mappings`)

**Updated Structure:**
```json
{
  "kbId": "69290ae45626b2766dce5f47",
  "sourceIndex": "app-logs",
  "anomalyIndex": "app-logs_anomalies",
  "dataViewId": "b5b3c8f0-ae10-4c57-934d-d8fb718d46d0",
  "savedSearchId": "258b5cd0-1859-4c06-8bb8-290e6a348e51",
  "dashboardId": "2a98eed0-da6d-495a-a3a3-f684e82e7652"
}
```

**Key Changes:**
- `indexName` → `sourceIndex`
- Added `anomalyIndex` field (derived as `{sourceIndex}_anomalies`)

### 6.3 Training Config (MongoDB: `anomaly_detection.training_config`)

**Metadata Field:**
```json
{
  "algorithms": [{
    "parameters": {
      "observed_values": [{
        "dimension": "status_5xx_count",
        "algorithm_metadata": [
          {"key": "percentile", "values": "99.5"}  // ← Was "value"
        ]
      }]
    }
  }]
}
```

---

## 7. End-to-End Verification

### Test Steps

1. **Create KB Config with `source_index`:**
   ```bash
   # Via MCP tool
   create_da_config(
       name="App Logs Anomaly Monitor",
       source_index="app-logs",
       ...
   )
   ```

2. **Verify Mapping Created:**
   ```bash
   curl -s "localhost:9201/index_kb_id_mappings/_search?pretty"
   ```
   
   **Expected Response:**
   ```json
   {
     "sourceIndex": "app-logs",
     "anomalyIndex": "app-logs_anomalies",
     "dashboardId": "..."
   }
   ```

3. **Verify Dashboard Title:**
   ```bash
   curl -s "localhost:5602/api/saved_objects/dashboard/{dashboardId}"
   ```
   
   **Expected:** `"title": "Dashboard - app-logs"`

4. **Verify Anomaly Index:**
   ```bash
   curl -s "localhost:9201/_cat/indices?v" | grep app-logs
   ```
   
   **Expected:** `app-logs_anomalies` (not `app-logs_anomalies_result_anomalies`)

5. **Verify Dispatcher Starts Without Error:**
   ```bash
   docker logs da-dispatcher --tail 30
   ```
   
   **Expected:** No `KeyError: 'value'` errors

### Results

| Verification | Status |
|--------------|--------|
| KB config created with `source_index: "app-logs"` | ✅ |
| Extractor sent mapping with `sourceIndex` | ✅ |
| Mapping stored with correct `anomalyIndex` | ✅ |
| Dashboard title: "Dashboard - app-logs" | ✅ |
| Anomaly index: `app-logs_anomalies` | ✅ |
| Dispatcher parses metadata without crash | ✅ |
| Training series loaded (960+ items) | ✅ |

---

## 8. File Changes Summary

| File | Type | Description |
|------|------|-------------|
| `MCP/KB-MCP/models.py` | MODIFIED | Renamed `database_index` → `source_index` |
| `MCP/KB-MCP/mcp_tools.py` | MODIFIED | Updated parameter names |
| `MCP/KB-MCP/mcp_tools_pkg/create_da_config.py` | MODIFIED | Updated parameter handling |
| `MCP/KB-MCP/mcp_tools_pkg/modify_kb_config.py` | MODIFIED | Updated parameter handling |
| `extractor/.../entity/kb/KbMongo.java` | MODIFIED | Renamed `databaseIndex` → `sourceIndex` |
| `extractor/.../dto/CreateMappingRequestDto.java` | MODIFIED | Simplified to `kbId` + `sourceIndex` |
| `extractor/.../service/BatchModeService.java` | MODIFIED | Uses `sourceIndex` |
| `extractor/.../entity/KeyValuePair.java` | MODIFIED | Changed `value` → `values` |
| `anomalies-insights-module/.../dto/CreateMappingRequestDto.java` | MODIFIED | Uses `sourceIndex` |
| `anomalies-insights-module/.../entity/IndexKbIdMapping.java` | MODIFIED | Added `sourceIndex`, `anomalyIndex` |
| `anomalies-insights-module/.../repository/IndexKbIdMappingRepo.java` | MODIFIED | Updated query methods |
| `anomalies-insights-module/.../controller/InsightsController.java` | MODIFIED | Extracts `sourceIndex` |
| `anomalies-insights-module/.../service/InsightsService.java` | MODIFIED | New `sanitizeIndexName()`, dashboard naming |
| `MotorDA/Dispatcher/DADispatcher.py` | MODIFIED | Uses `values` with fallback |

---

## 9. Docker Commands

### Rebuild and Restart Services

```bash
# Rebuild all modified services
docker-compose build extractor anomalies-insights dispatcher

# Restart services
docker-compose up -d extractor anomalies-insights dispatcher
```

### Verify Service Health

```bash
# Check all containers
docker ps

# View extractor logs
docker logs etl-app --tail 50

# View dispatcher logs
docker logs da-dispatcher --tail 50

# View anomalies-insights logs
docker logs anomalies-insights --tail 50
```

### Verify MongoDB Data

```bash
# Check KB config
docker exec mongodb mongosh -u admin -p '1q2w3E*' --quiet --eval "
  db = db.getSiblingDB('knowledge_base');
  db.kb_configs.findOne({}, {name: 1, source_index: 1})
"

# Check training config metadata
docker exec mongodb mongosh -u admin -p '1q2w3E*' --quiet --eval "
  db = db.getSiblingDB('anomaly_detection');
  db.training_config.findOne().algorithms[0].parameters.observed_values
"
```

### Verify Elasticsearch Mapping

```bash
# Check mapping document
curl -s "localhost:9201/index_kb_id_mappings/_search?pretty"

# Check indices
curl -s "localhost:9201/_cat/indices?v" | grep anomalies
```

### Trigger KB Config Reprocessing

```bash
# Update change_flag to trigger ETL
docker exec mongodb mongosh -u admin -p '1q2w3E*' --quiet --eval "
  db = db.getSiblingDB('knowledge_base');
  db.kb_configs.updateOne({name: 'Your Config Name'}, {\$set: {change_flag: 999}})
"
```

---

**End of Session Bug Fixes Documentation**
