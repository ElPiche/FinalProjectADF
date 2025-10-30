# KBConfig MCP Update Plan

## Overview
This document outlines the comprehensive plan to update the KB-MCP server to conform to the new `KBConfigTemplate.json` specification. The template introduces snake_case field naming, optional mode fields, and a new algorithm parameter structure.

## Key Changes Identified

1. **Field Naming**: Template uses snake_case (`change_flag`, `training_config`, etc.) vs MCP's camelCase
2. **Algorithm Structure**: Template uses `dimension` + `algorithm_metadata` vs MCP's `observedValue`
3. **Query Fields**: Template uses `training_query`/`detection_query` vs MCP's `trainingQuery`/`detectionQuery`
4. **MongoDB Storage Structure**: **CRITICAL** - MCP currently wraps configs in `{"kbConfig": {...}}` but template should be stored directly as the final structure
5. **ID Field**: Template shows `"id": "1fbb07a4-..."` but this is just an example - MongoDB will auto-generate `_id`, we don't set `id` field
6. **KB Directory**: Currently empty (no JSON files) - MCP now stores directly in MongoDB instead of file system
7. **Mode Fields**: Commented out in template - not implementing at this time
8. **Function Parameters**: Remove Optional[KBConfig] and Optional[DaAlgParameters] - function must receive required parameters

## Detailed Action Plan

### 1. Update Function Signature - Remove Optional Parameters
**Current:**
```python
@mcp.tool()
def create_da_config(
    kb_config: Optional[KBConfig] = None,
    da_alg_parameters: Optional[DaAlgParameters] = None
) -> str:
```

**Updated:**
```python
@mcp.tool()
def create_da_config(
    kb_config: KBConfig,
    da_alg_parameters: DaAlgParameters
) -> str:
    """
    Create a Data Analytics (DA) algorithm configuration for the Knowledge Base system.

    This function validates all input parameters and stores the configuration directly
    in MongoDB matching the KBConfigTemplate.json structure.

    Args:
        kb_config (KBConfig): Required configuration containing name, description, change_flag, scheduling, and da_alg_parameters
        da_alg_parameters (DaAlgParameters): Required data analytics algorithm parameters

    Returns:
        str: Validation success message with configuration preview, or detailed error message

    Example:
        kb_config = KBConfig(
            name="HTTP Monitoring",
            description="Monitor HTTP status codes",
            change_flag=0,
            scheduling={
                "training_config": {
                    "training_query": "SELECT ... FROM ...",
                    "from": "2025-10-01T00:00:00Z",
                    "to": "2025-10-09T23:59:59Z",
                    "training_window": 3600,
                    "is_active": True
                },
                "detection_config": {
                    "detection_query": "SELECT ... FROM ...",
                    "from": "2025-10-10T00:00:00Z",
                    "frequency": "*/15 * * * *",
                    "detection_window": 3600,
                    "is_active": False
                }
            },
            da_alg_parameters={
                "zscore": [{"dimension": "status_code_200_counter"}]
            }
        )
        da_params = DaAlgParameters(algorithms=[ZScore(observed_value="status_code_200_counter")])
        result = create_da_config(kb_config, da_params)
    """
```

### 2. Update KBConfig Class (Lines 34-52)
**Current:**
```python
class KBConfig(BaseModel):
    id: str
    name: str
    description: str
    changeFlag: int
    scheduling: dict
    daAlgParameters: dict
```

**Updated:**
```python
class KBConfig(BaseModel):
    # No id field - MongoDB will auto-generate _id
    name: str
    description: str
    change_flag: int  # snake_case
    scheduling: dict
    da_alg_parameters: dict  # snake_case
```

### 3. Update Scheduling Validation Logic (Lines 712-736)
**Current:**
```python
training_config = kb_config.scheduling.get('trainingConfig', {})
if training_config.get('from') >= training_config.get('to'):
    validation_errors.append("Training 'from' must be before 'to'")
if training_config.get('mode') not in ["training", "batch", "streaming"]:
    validation_errors.append("Training mode must be 'training', 'batch', or 'streaming'")
if not isinstance(training_config.get('trainingWindow'), int) or training_config.get('trainingWindow') <= 0:
    validation_errors.append("Training window must be a positive integer")
```

**Updated:**
```python
training_config = kb_config.scheduling.get('training_config', {})  # snake_case
if training_config.get('from') >= training_config.get('to'):
    validation_errors.append("Training 'from' must be before 'to'")
# Mode validation removed - not implementing at this time
if not isinstance(training_config.get('training_window'), int) or training_config.get('training_window') <= 0:  # snake_case
    validation_errors.append("Training window must be a positive integer")
```

### 4. Update SQL Query Validation (Lines 750-821)
**Current:**
```python
training_query = kb_config.scheduling.get('trainingConfig', {}).get('trainingQuery')
detection_query = kb_config.scheduling.get('detectionConfig', {}).get('detectionQuery')
```

**Updated:**
```python
training_query = kb_config.scheduling.get('training_config', {}).get('training_query')  # snake_case
detection_query = kb_config.scheduling.get('detection_config', {}).get('detection_query')  # snake_case
```

### 5. Update MongoDB Storage Structure (Lines 834-887)
**Current:**
```python
config_preview = {
    "kbConfig": {
        "id": kb_config.id,
        "name": kb_config.name,
        "description": kb_config.description,
        "changeFlag": kb_config.changeFlag,
        "scheduling": kb_config.scheduling,
        "daAlgParameters": kb_config.daAlgParameters
    }
}

result = collection.insert_one(config_preview)
```

**Updated:**
```python
config_to_store = {
    # NO id field - MongoDB auto-generates _id
    "name": kb_config.name,
    "description": kb_config.description,
    "change_flag": kb_config.change_flag,  # snake_case
    "scheduling": {
        "training_config": {  # snake_case
            "training_query": kb_config.scheduling["training_config"]["training_query"],  # snake_case
            "from": kb_config.scheduling["training_config"]["from"],
            "to": kb_config.scheduling["training_config"]["to"],
            "training_window": kb_config.scheduling["training_config"]["training_window"],  # snake_case
            "is_active": kb_config.scheduling["training_config"]["is_active"]  # snake_case
        },
        "detection_config": {  # snake_case
            "detection_query": kb_config.scheduling["detection_config"]["detection_query"],  # snake_case
            "from": kb_config.scheduling["detection_config"]["from"],
            "frequency": kb_config.scheduling["detection_config"]["frequency"],
            "detection_window": kb_config.scheduling["detection_config"]["detection_window"],  # snake_case
            "is_active": kb_config.scheduling["detection_config"]["is_active"]  # snake_case
        }
    },
    "da_alg_parameters": {
        "zscore": [
            {"dimension": "status_code_200_counter"}  # NEW: dimension instead of observedValue
        ]
    }
}

result = collection.insert_one(config_to_store)  # Store directly, no wrapper
```

### 6. Update Algorithm Parameter Extraction (Lines 665-697)
**Current:**
```python
da_alg_params = kb_config.daAlgParameters
zscore_configs = da_alg_params.get("zscore", [])
for alg_dict in zscore_configs:
    if isinstance(alg_dict, dict) and "observedValue" in alg_dict:
        custom_algs.append(ZScore(observed_value=alg_dict["observedValue"]))
```

**Updated:**
```python
da_alg_params = kb_config.da_alg_parameters  # snake_case
zscore_configs = da_alg_params.get("zscore", [])
for alg_dict in zscore_configs:
    if isinstance(alg_dict, dict) and "dimension" in alg_dict:  # NEW: dimension
        custom_algs.append(ZScore(observed_value=alg_dict["dimension"]))  # Map dimension to observed_value
```

### 7. Remove Default Configuration Generation
**REMOVED**: Since we removed Optional parameters, there's no need for default configuration generation. The function now requires both `kb_config` and `da_alg_parameters` to be provided by the caller.

### 8. Update modify_kb_config Tool (Lines 893-1031)
**Current:**
```python
config_doc = collection.find_one({"kbConfig.id": config_id})
updates = {}
if description is not None:
    updates["kbConfig.description"] = description
if training_query is not None:
    updates["kbConfig.scheduling.trainingConfig.trainingQuery"] = training_query
```

**Updated:**
```python
config_doc = collection.find_one({"_id": ObjectId(config_id)})  # Use MongoDB _id
updates = {}
if description is not None:
    updates["description"] = description  # Direct field access
if training_query is not None:
    updates["scheduling.training_config.training_query"] = training_query  # snake_case, no wrapper
```

### 9. Update list_kb_configurations Tool (Lines 1034-1097)
**Current:**
```python
for config_doc in configs:
    kb_config = config_doc.get("kbConfig", {})
    scheduling = kb_config.get("scheduling", {})
    training_config = scheduling.get("trainingConfig", {})
    detection_config = scheduling.get("detectionConfig", {})
    da_params = kb_config.get("daAlgParameters", {})
    if "zscore" in da_params:
        algorithms = [f"ZScore({alg.get('observedValue', 'unknown')})" for alg in da_params["zscore"]]
```

**Updated:**
```python
for config_doc in configs:
    kb_config = config_doc  # Direct access, no kbConfig wrapper
    scheduling = kb_config.get("scheduling", {})
    training_config = scheduling.get("training_config", {})  # snake_case
    detection_config = scheduling.get("detection_config", {})  # snake_case
    da_params = kb_config.get("da_alg_parameters", {})  # snake_case
    if "zscore" in da_params:
        algorithms = [f"ZScore({alg.get('dimension', 'unknown')})" for alg in da_params["zscore"]]  # NEW: dimension
```

### 10. Update Documentation Examples (Lines 1183-1271)
**Current Example:**
```json
{
  "kbConfig": {
    "id": "unique-uuid",
    "description": "Human-readable description",
    "changeFlag": 0,
    "scheduling": {
      "trainingConfig": {
        "trainingQuery": "SELECT ... FROM ...",
        "from": "2025-09-01T00:00:00Z",
        "to": "2025-09-30T23:59:59Z",
        "mode": "training",
        "trainingWindow": 60,
        "isActive": false
      }
    },
    "daAlgParameters": {
      "zscore": [{"observedValue": "field_name"}]
    }
  }
}
```

**Updated Example:**
```json
{
  "name": "HTTP Monitoring Config",
  "description": "Monitor HTTP status codes for anomalies",
  "change_flag": 0,
  "scheduling": {
    "training_config": {
      "training_query": "SELECT ... FROM ...",
      "from": "2025-09-01T00:00:00Z",
      "to": "2025-09-30T23:59:59Z",
      "training_window": 60,
      "is_active": false
    },
    "detection_config": {
      "detection_query": "SELECT ... FROM ...",
      "from": "2025-10-10T00:00:00Z",
      "frequency": "*/15 * * * *",
      "detection_window": 60,
      "is_active": false
    }
  },
  "da_alg_parameters": {
    "zscore": [{"dimension": "status_code_200_counter"}]
  }
}
```

### 11. Update Command Line Argument Parsing (Lines 1475-1510)
**REMOVED**: Since we removed Optional parameters and default configuration generation, command line argument parsing for defaults is no longer needed. The function now requires explicit KBConfig and DaAlgParameters objects to be passed.

### 12. Update ZScore.to_dict() Method
**Current:**
```python
def to_dict(self):
    return {
        "observedValue": self.observed_value
    }
```

**Updated:**
```python
def to_dict(self):
    return {
        "dimension": self.observed_value  # Map to dimension for template compatibility
    }
```

## Function Parameter Changes
- **Removed Optional[KBConfig]**: Function now requires `kb_config: KBConfig` parameter
- **Removed Optional[DaAlgParameters]**: Function now requires `da_alg_parameters: DaAlgParameters` parameter
- **No Default Configurations**: Caller must provide complete configuration objects
- **ID Field**: MongoDB auto-generates `_id` - no manual `id` field in configurations

## Algorithm Structure Migration

**Current MCP expects:**
```json
{"observedValue": "status_code_200_counter"}
```

**Template specifies:**
```json
{
  "zscore": [
    {"dimension": "status_code_200_counter"}
  ],
  "arma": [
    {
      "dimension": "status_code_200_counter",
      "algorithm_metadata": [
        {"key": "p", "value": 2},
        {"key": "d", "value": 1},
        {"key": "q", "value": 2}
      ]
    }
  ]
}
```

## Testing Strategy
1. Test with template-compliant JSON input (including optional modes)
2. Verify validation passes with snake_case fields
3. Test algorithm parameter extraction from new grouped structure
4. Test MongoDB storage and retrieval with snake_case fields
5. Test modify_kb_config with snake_case field updates
6. Test backward compatibility with existing configs

## Implementation Notes
- All changes maintain backward compatibility where possible
- Framework remains ready for future algorithm implementations
- MongoDB field paths updated to match new snake_case structure
- Validation logic updated to handle optional mode fields correctly

This plan ensures the MCP fully conforms to the `KBConfigTemplate.json` specification while maintaining the framework for future algorithm and mode support.