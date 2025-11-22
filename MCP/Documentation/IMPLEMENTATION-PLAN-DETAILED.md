# Detailed Implementation Plan: KB-MCP High-Priority Fixes & Configuration Name Uniqueness

**Date**: November 21, 2025  
**Target**: Complete high-priority fixes (1–3) and medium-priority fix (Configuration Name Uniqueness)  
**Status**: Ready for Implementation

---

## Executive Summary

This document provides a step-by-step implementation plan for:
1. **Window Size Validation** (High Priority) – Enforce `training_window > 0` and `detection_window > 0`
2. **Request/Validation Timeouts** (High Priority) – Prevent long-running operations
3. **Hanging Operation Handling** (High Priority) – Add structured logging and confirm no blocking ETL
4. **Configuration Name Uniqueness** (Medium Priority) – Warn on duplicate names, soft enforcement

**Total Estimated Effort**: ~16–20 hours of implementation + testing  
**Phase**: Phase 1 (Weeks 1–2): Items 1 & 4 (safer, isolated changes)  
**Phase**: Phase 2 (Weeks 2–3): Items 2 & 3 (timeout infrastructure, requires more integration testing)

## Implementation Status (Nov 22, 2025)

- ✅ `validation.py` now exposes `validate_window_size`, `validate_cron_expression`, and advisory logging. Tests live in `tests/test_validation.py`.
- ✅ `create_da_config.py` and `modify_kb_config.py` enforce window limits, log per-step durations, warn (or block) duplicate names, and rely on the new dict-based `elasticsearch_sql` response.
- ✅ `query_validator.py` + `elasticsearch_sql.py` use configurable timeouts sourced from Dockerfile `ENV` defaults with actionable error messages.
- ✅ Added regression tests for duplicate-name warnings, timeout handling (`tests/test_timeouts.py`), and updated existing fixtures to the new return contracts.
- ✅ Dockerfile exports the new timeout/window environment variables to document defaults for deployments.

---

## Phase 1: Window Size Validation & Configuration Name Uniqueness

### Fix 1.1: Add Window Size Validation Constants & Utility

**Location**: `MCP/KB-MCP/validation.py`  
**Goal**: Create reusable validation helpers for window sizes.

Notes: per client request, the minimum allowed window is now 1 second and there is no maximum cap enforced by the MCP tools (training and detection windows may be arbitrarily large). **However**, to mitigate operational risk, add advisory warnings when windows exceed a configurable large-window threshold (default: 30 days). Downstream systems (ETL/dispatcher) should implement pagination, range-splitting, or rate-limiting for very large windows.

**Changes**:
```python
# Add at the top of validation.py after imports
import logging
import os

logger = logging.getLogger(__name__)

VALIDATION_CONSTANTS = {
    "MIN_TRAINING_WINDOW_SECONDS": 1,           # Minimum 1 second
    "MIN_DETECTION_WINDOW_SECONDS": 1,          # Minimum 1 second
    "LARGE_WINDOW_THRESHOLD_DAYS": int(os.getenv("LARGE_WINDOW_THRESHOLD_DAYS", 30)),  # Advisory threshold
}


def validate_window_size(window_seconds, window_type="training"):
    """
    Validate that a window size meets the minimum bound (no maximum enforced).
    Issues a WARNING if the window exceeds the large-window threshold.
    
    Args:
        window_seconds (int): The window size in seconds.
        window_type (str): Either 'training' or 'detection' (used in error messages).
    
    Returns:
        dict: {"valid": bool, "warning": optional str}
    
    Raises:
        ValueError: If the window is invalid.
    """
    min_key = f"MIN_{window_type.upper()}_WINDOW_SECONDS"
    min_val = VALIDATION_CONSTANTS.get(min_key)

    if not isinstance(window_seconds, int):
        raise ValueError(f"{window_type.capitalize()} window must be an integer (got {type(window_seconds).__name__}).")

    if window_seconds < min_val:
        # Human-friendly message: show seconds for small mins, minutes if >= 60
        if min_val >= 60:
            human = f"{min_val // 60} minute(s)"
        else:
            human = f"{min_val} second(s)"

        raise ValueError(
            f"{window_type.capitalize()} window must be >= {min_val} seconds ({human}); got {window_seconds}."
        )
    
    # Check for large windows and emit advisory warning
    threshold_seconds = VALIDATION_CONSTANTS["LARGE_WINDOW_THRESHOLD_DAYS"] * 86400
    warning = None
    
    if window_seconds > threshold_seconds:
        threshold_days = VALIDATION_CONSTANTS["LARGE_WINDOW_THRESHOLD_DAYS"]
        window_days = window_seconds / 86400
        warning = (
            f"Large {window_type} window requested: {window_days:.1f} days (threshold: {threshold_days} days). "
            f"Very large windows may cause: slow Elasticsearch queries, high memory/CPU usage, large MongoDB series documents, "
            f"and operational impact on ETL/dispatcher systems. Confirm this is intentional."
        )
        logger.warning(warning)
    
    return {"valid": True, "warning": warning}
```

**Tests** (in `MCP/KB-MCP/tests/test_validation.py`):
```python
import pytest
from validation import validate_window_size

def test_validate_window_size_valid():
    """Test that valid window sizes pass (no warning)."""
    result = validate_window_size(3600, "training")
    assert result["valid"] is True
    assert result["warning"] is None
    
    result = validate_window_size(7200, "detection")
    assert result["valid"] is True
    assert result["warning"] is None

def test_validate_window_size_too_small():
    """Test that windows < 1 second are rejected."""
    with pytest.raises(ValueError, match="must be >= 1 second"):
        validate_window_size(0, "training")

def test_validate_window_size_non_integer():
    """Test that non-integer windows are rejected."""
    with pytest.raises(ValueError, match="must be an integer"):
        validate_window_size(3600.5, "training")

def test_validate_window_size_large_window_warning():
    """Test that very large windows emit a warning (default threshold: 30 days)."""
    # 60 days in seconds = 5184000
    result = validate_window_size(5184000, "training")
    assert result["valid"] is True
    assert result["warning"] is not None
    assert "Large" in result["warning"]

def test_validate_window_size_at_threshold():
    """Test that windows at exactly threshold do not emit a warning."""
    # 30 days in seconds = 2592000
    result = validate_window_size(2592000, "detection")
    assert result["valid"] is True
    assert result["warning"] is None
```

---

### Fix 1.2: Integrate Window Validation into `create_da_config.py`

**Location**: `MCP/KB-MCP/mcp_tools_pkg/create_da_config.py`  
**Goal**: Validate windows early, before SQL validation.

**Changes**:
1. Import the `validate_window_size` function.
2. Call it for both `training_window` and `detection_window` early in the function, **before** SQL validation.
3. On error, raise `ToolError` with a user-friendly message.

```python
# At the top of create_da_config.py
from validation import validate_window_size

def create_da_config(
    name: str,
    description: str,
    training_query: str,
    detection_query: str,
    training_from: str,
    training_to: str,
    training_is_active: bool,
    detection_is_active: bool,
    training_window: int,
    detection_window: int,
    detection_frequency: str,
    detection_start: str,
    algorithms: list,
) -> dict:
    """Create a new anomaly detection configuration."""
    
    try:
        # ===== STEP 1: Window Size Validation (Early Fail) =====
        logger.info("Validating window sizes...")
        training_result = validate_window_size(training_window, "training")
        detection_result = validate_window_size(detection_window, "detection")
        
        # Collect warnings to include in success message
        warnings = []
        if training_result.get("warning"):
            warnings.append(training_result["warning"])
        if detection_result.get("warning"):
            warnings.append(detection_result["warning"])
        
        if warnings:
            logger.warning("\n".join(warnings))
        
        logger.info("✓ Window sizes valid")
        
        # ===== STEP 2: SQL Query Validation =====
        logger.info("Validating training query...")
        # ... existing validation logic ...
        
        # ===== STEP 3: CRON Validation =====
        # ... existing validation logic ...
        
        # ===== STEP 4: MongoDB Insert & Check Uniqueness =====
        # ... see Fix 1.3 below ...
        
    except ValueError as e:
        raise ToolError(f"Invalid window size: {str(e)}")
```

**Error Response Example**:
```
ToolError: Invalid window size: training window must be >= 1 second; got 0.
```

---

### Fix 1.3: Integrate Configuration Name Uniqueness Check

**Location**: `MCP/KB-MCP/mcp_tools_pkg/create_da_config.py`  
**Goal**: Warn on duplicate config names, but allow insertion (soft enforcement by default; optional strict mode).

**Strict Mode Note**: Add environment variable `ENFORCE_UNIQUE_CONFIG_NAMES` (default: false). If set to `true`, reject configs with duplicate names. This allows production deployments to enforce uniqueness while keeping flexibility for testing and migration scenarios. Also ensure MongoDB has an index on `name` field for fast lookup.

**Changes**:
1. Import the `os` module to read env variables.
2. Before inserting into MongoDB, query for existing configs with the same name.
3. If found:
   - If `ENFORCE_UNIQUE_CONFIG_NAMES=true`: raise `ToolError` (strict mode).
   - If `ENFORCE_UNIQUE_CONFIG_NAMES=false` (default): add warning to success message (permissive mode).
4. Ensure the config is inserted regardless (in permissive mode).

```python
# In create_da_config(), after all validations pass
def create_da_config(...) -> dict:
    try:
        # ... (window validation, SQL validation, CRON validation) ...
        
        # ===== STEP 4: Check for Duplicate Names (Warning or Error) =====
        logger.info(f"Checking for existing config with name '{name}'...")
        db = connect_mongodb()
        existing = db.anomaly_detection.train_config.find_one({"name": name})
        
        warning_msg = ""
        enforce_unique = os.getenv("ENFORCE_UNIQUE_CONFIG_NAMES", "false").lower() == "true"
        
        if existing:
            msg = f"Configuration with name '{name}' already exists (ID: {existing.get('_id')})."
            if enforce_unique:
                logger.error(f"Duplicate name rejected (strict mode): {name}")
                raise ToolError(
                    f"Duplicate configuration name: {msg} Strict mode is enabled. "
                    f"Use a unique name or set ENFORCE_UNIQUE_CONFIG_NAMES=false to allow duplicates."
                )
            else:
                warning_msg = f"\n⚠️  Warning: {msg} Consider using a unique name to avoid confusion."
                logger.warning(f"Duplicate name allowed (permissive mode): {name}")
        
        # ===== STEP 5: Insert into MongoDB =====
        logger.info("Inserting configuration into MongoDB...")
        config_doc = {
            "name": name,
            "description": description,
            "training_query": training_query,
            "detection_query": detection_query,
            # ... other fields ...
        }
        result = db.anomaly_detection.train_config.insert_one(config_doc)
        inserted_id = str(result.inserted_id)
        logger.info(f"✓ Configuration created with ID: {inserted_id}")
        
        # ===== Return Success Message =====
        success_msg = f"✓ Configuration '{name}' created successfully (ID: {inserted_id})."
        return {
            "status": "success",
            "message": success_msg + warning_msg,
            "config_id": inserted_id,
        }
        
    except Exception as e:
        logger.error(f"Error creating configuration: {str(e)}")
        raise ToolError(f"Failed to create configuration: {str(e)}")
```

**MongoDB Index** (to optimize duplicate name lookup):
```javascript
// Run in MongoDB shell to create index
db.train_config.createIndex({ "name": 1 })
```

**Success Response Examples**:

**Case 1: Unique name**:
```json
{
  "status": "success",
  "message": "✓ Configuration 'web-traffic-anomalies' created successfully (ID: 507f1f77bcf86cd799439011).",
  "config_id": "507f1f77bcf86cd799439011"
}
```

**Case 2: Duplicate name** (with warning):
```json
{
  "status": "success",
  "message": "✓ Configuration 'web-traffic-anomalies' created successfully (ID: 507f1f88bcf86cd799439012).\n⚠️  Warning: A configuration with name 'web-traffic-anomalies' already exists (ID: 507f1f77bcf86cd799439011). Consider using a unique name to avoid confusion.",
  "config_id": "507f1f88bcf86cd799439012"
}
```

---

### Fix 1.4: Extend Tests for Configuration Name Uniqueness

**Location**: `MCP/KB-MCP/tests/test_create_modify_validation.py`  
**Goal**: Verify warning message appears for duplicate names.

**Changes**:
```python
import pytest
from unittest.mock import patch, MagicMock

def test_create_config_duplicate_name_shows_warning(mock_mongodb):
    """Test that creating a config with a duplicate name shows a warning."""
    # Mock MongoDB to return existing config
    existing_config = {
        "_id": ObjectId("507f1f77bcf86cd799439011"),
        "name": "duplicate-config",
    }
    mock_mongodb.anomaly_detection.train_config.find_one.return_value = existing_config
    mock_mongodb.anomaly_detection.train_config.insert_one.return_value.inserted_id = ObjectId("507f1f88bcf86cd799439012")
    
    # Call create_da_config with a duplicate name
    result = create_da_config(
        name="duplicate-config",
        description="Test config",
        training_query="SELECT ... WHERE @timestamp >= '$from' AND @timestamp < '$to'",
        detection_query="SELECT ... WHERE @timestamp >= '$from' AND @timestamp < '$to'",
        training_from="2025-11-01T00:00:00Z",
        training_to="2025-11-30T00:00:00Z",
        training_is_active=True,
        detection_is_active=True,
        training_window=3600,
        detection_window=3600,
        detection_frequency="*/5 * * * *",
        detection_start="2025-11-21T00:00:00Z",
        algorithms=[{"alg_name": "zscore", "alg_parameters": [{"dimension": "status_code"}]}],
    )
    
    # Verify warning is in the message
    assert "already exists" in result["message"]
    assert "507f1f77bcf86cd799439011" in result["message"]
    assert result["status"] == "success"

def test_create_config_unique_name_no_warning(mock_mongodb):
    """Test that creating a config with a unique name shows no warning."""
    # Mock MongoDB to return no existing config
    mock_mongodb.anomaly_detection.train_config.find_one.return_value = None
    mock_mongodb.anomaly_detection.train_config.insert_one.return_value.inserted_id = ObjectId("507f1f88bcf86cd799439012")
    
    result = create_da_config(
        name="unique-config",
        description="Test config",
        training_query="SELECT ... WHERE @timestamp >= '$from' AND @timestamp < '$to'",
        detection_query="SELECT ... WHERE @timestamp >= '$from' AND @timestamp < '$to'",
        training_from="2025-11-01T00:00:00Z",
        training_to="2025-11-30T00:00:00Z",
        training_is_active=True,
        detection_is_active=True,
        training_window=3600,
        detection_window=3600,
        detection_frequency="*/5 * * * *",
        detection_start="2025-11-21T00:00:00Z",
        algorithms=[{"alg_name": "zscore", "alg_parameters": [{"dimension": "status_code"}]}],
    )
    
    # Verify no warning in the message
    assert "already exists" not in result["message"]
    assert result["status"] == "success"
```

---

### Fix 1.5: Apply Same Window Validation to `modify_kb_config.py`

**Location**: `MCP/KB-MCP/mcp_tools_pkg/modify_kb_config.py`  
**Goal**: Validate windows only if they are being updated.

**Changes**:
```python
from validation import validate_window_size

def modify_kb_config(config_id: str, **kwargs) -> dict:
    """Modify an existing anomaly detection configuration."""
    
    try:
        # ===== STEP 1: Window Size Validation (if present) =====
        if "training_window" in kwargs and kwargs["training_window"] is not None:
            logger.info("Validating updated training_window...")
            validate_window_size(kwargs["training_window"], "training")
            logger.info("✓ Updated training_window is valid")
        
        if "detection_window" in kwargs and kwargs["detection_window"] is not None:
            logger.info("Validating updated detection_window...")
            validate_window_size(kwargs["detection_window"], "detection")
            logger.info("✓ Updated detection_window is valid")
        
        # ===== STEP 2: Other Validations =====
        # ... existing validation logic ...
        
        # ===== STEP 3: Update MongoDB =====
        db = connect_mongodb()
        update_result = db.anomaly_detection.train_config.update_one(
            {"_id": ObjectId(config_id)},
            {"$set": kwargs}
        )
        
        if update_result.matched_count == 0:
            raise ToolError(f"Configuration ID '{config_id}' not found.")
        
        return {
            "status": "success",
            "message": f"✓ Configuration '{config_id}' updated successfully.",
            "config_id": config_id,
        }
        
    except ValueError as e:
        raise ToolError(f"Invalid window size: {str(e)}")
    except Exception as e:
        raise ToolError(f"Failed to modify configuration: {str(e)}")
```

---

## Phase 2: Request/Validation Timeouts & Hanging Operation Handling

### Fix 2.1: Add Timeout Configuration Constants

**Location**: `MCP/KB-MCP/mcp_tools_pkg/query_validator.py`  
**Goal**: Define timeout constants and make them configurable via environment variables. Document defaults and expose for tuning.

**Changes**:
```python
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Timeout configuration (in seconds)
# These are tunable via environment variables for different cluster speeds/workloads.
# Default values are conservative and can be increased if queries are legitimate and need more time.
VALIDATION_TIMEOUTS = {
    "EXTRACTOR_VALIDATION_TIMEOUT": int(os.getenv("EXTRACTOR_VALIDATION_TIMEOUT_SECONDS", 10)),
    "ELASTICSEARCH_SQL_PREVIEW_TIMEOUT": int(os.getenv("ELASTICSEARCH_SQL_PREVIEW_TIMEOUT_SECONDS", 5)),
    "ELASTICSEARCH_SQL_QUERY_TIMEOUT": int(os.getenv("ELASTICSEARCH_SQL_QUERY_TIMEOUT_SECONDS", 30)),
}

logger.info(
    f"Timeout configuration loaded. "
    f"Extractor: {VALIDATION_TIMEOUTS['EXTRACTOR_VALIDATION_TIMEOUT']}s, "
    f"ES SQL preview: {VALIDATION_TIMEOUTS['ELASTICSEARCH_SQL_PREVIEW_TIMEOUT']}s, "
    f"ES SQL query: {VALIDATION_TIMEOUTS['ELASTICSEARCH_SQL_QUERY_TIMEOUT']}s. "
    f"Tune via env vars: EXTRACTOR_VALIDATION_TIMEOUT_SECONDS, ELASTICSEARCH_SQL_PREVIEW_TIMEOUT_SECONDS, ELASTICSEARCH_SQL_QUERY_TIMEOUT_SECONDS."
)
```

**Environment Variables** (add to `Dockerfile` or `.env`):
```dockerfile
ENV EXTRACTOR_VALIDATION_TIMEOUT_SECONDS=10
ENV ELASTICSEARCH_SQL_PREVIEW_TIMEOUT_SECONDS=5
ENV ELASTICSEARCH_SQL_QUERY_TIMEOUT_SECONDS=30
```

---

### Fix 2.2: Update `QueryValidator.validate()` to Use Timeouts

**Location**: `MCP/KB-MCP/mcp_tools_pkg/query_validator.py`  
**Goal**: Wrap Elasticsearch validation calls with explicit timeouts.

**Changes**:
```python
import requests
from requests.exceptions import Timeout, ConnectionError, RequestException
import time

class QueryValidator:
    def validate(self, query: str, timeout: int = None) -> dict:
        """
        Validate a Elasticsearch SQL query.
        
        Args:
            query (str): The SQL query to validate.
            timeout (int, optional): Timeout in seconds. Uses EXTRACTOR_VALIDATION_TIMEOUT if not provided.
        
        Returns:
            dict: Validation result with 'valid' and 'columns' keys.
        
        Raises:
            ValueError: If the query is invalid or validation times out.
        """
        if timeout is None:
            timeout = VALIDATION_TIMEOUTS["EXTRACTOR_VALIDATION_TIMEOUT"]
        
        start_time = time.time()
        logger.info(f"Starting query validation (timeout: {timeout}s)...")
        
        try:
            # Make request with explicit timeout
            response = requests.post(
                "http://elasticsearch-extractor:9200/_sql",  # Adjust endpoint as needed
                json={"query": query},
                headers={"Content-Type": "application/json"},
                timeout=timeout,
            )
            
            elapsed = time.time() - start_time
            logger.info(f"Query validation completed in {elapsed:.2f}s")
            
            if response.status_code != 200:
                raise ValueError(f"Query validation failed: {response.text}")
            
            result = response.json()
            return {"valid": True, "columns": result.get("columns", [])}
            
        except Timeout:
            elapsed = time.time() - start_time
            logger.error(f"Query validation timed out after {elapsed:.2f}s (timeout: {timeout}s)")
            raise ValueError(
                f"Query validation timed out after {timeout} seconds. The query may be too complex, "
                f"the Elasticsearch cluster may be slow, or the time range may be too large. "
                f"Next steps: (1) simplify the query (fewer columns, smaller time range), "
                f"(2) test with the 'elasticsearch_sql' tool directly to debug, or "
                f"(3) increase EXTRACTOR_VALIDATION_TIMEOUT_SECONDS if the query is legitimate. "
                f"Current timeout config: EXTRACTOR_VALIDATION_TIMEOUT_SECONDS={timeout}."
            )
        except (ConnectionError, RequestException) as e:
            elapsed = time.time() - start_time
            logger.error(f"Query validation failed after {elapsed:.2f}s: {str(e)}")
            raise ValueError(f"Query validation failed: {str(e)}")
```

**Test** (in `tests/test_query_validator.py`):
```python
import pytest
from unittest.mock import patch, MagicMock
from requests.exceptions import Timeout

def test_query_validator_timeout():
    """Test that validation timeouts are handled gracefully."""
    validator = QueryValidator()
    
    # Mock requests.post to raise Timeout
    with patch("requests.post") as mock_post:
        mock_post.side_effect = Timeout("Connection timeout")
        
        with pytest.raises(ValueError, match="timed out after"):
            validator.validate("SELECT * FROM logs", timeout=5)

def test_query_validator_custom_timeout():
    """Test that custom timeout is respected."""
    validator = QueryValidator()
    
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"columns": []}
        
        result = validator.validate("SELECT * FROM logs", timeout=15)
        
        # Verify timeout was passed to requests.post
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[1]["timeout"] == 15
        assert result["valid"] is True
```

---

### Fix 2.3: Add Timeout Handling to `elasticsearch_sql.py`

**Location**: `MCP/KB-MCP/mcp_tools_pkg/elasticsearch_sql.py`  
**Goal**: Wrap Elasticsearch SQL queries with explicit timeouts and duration logging.

**Changes**:
```python
import time
import logging
from requests.exceptions import Timeout, ConnectionError

logger = logging.getLogger(__name__)

def elasticsearch_sql(query: str) -> dict:
    """
    Execute an Elasticsearch SQL query.
    
    Args:
        query (str): The SQL query to execute.
    
    Returns:
        dict: Query result with columns and rows.
    
    Raises:
        ToolError: If the query fails or times out.
    """
    start_time = time.time()
    timeout = VALIDATION_TIMEOUTS["ELASTICSEARCH_SQL_QUERY_TIMEOUT"]
    
    logger.info(f"Executing Elasticsearch SQL query (timeout: {timeout}s)...")
    
    try:
        # Execute query with timeout
        response = requests.post(
            "http://elasticsearch-dataset:9200/_sql",  # Adjust endpoint as needed
            json={"query": query},
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )
        
        elapsed = time.time() - start_time
        
        if response.status_code != 200:
            logger.error(f"SQL query failed after {elapsed:.2f}s: {response.text}")
            raise ToolError(f"Elasticsearch SQL query failed: {response.text}")
        
        result = response.json()
        logger.info(f"✓ SQL query completed in {elapsed:.2f}s")
        
        return {
            "columns": result.get("columns", []),
            "rows": result.get("rows", []),
            "duration_ms": int(elapsed * 1000),
        }
        
    except Timeout:
        elapsed = time.time() - start_time
        logger.error(f"SQL query timed out after {elapsed:.2f}s (timeout: {timeout}s)")
        raise ToolError(
            f"Elasticsearch SQL query timed out after {timeout} seconds. "
            "Next steps: (1) simplify the query (fewer columns/aggregations, smaller time range), "
            "(2) reduce window size if applicable, (3) try again later if cluster is slow, or "
            f"(4) increase ELASTICSEARCH_SQL_QUERY_TIMEOUT_SECONDS (currently {timeout}s) if query is legitimate."
        )
    except (ConnectionError, RequestException) as e:
        elapsed = time.time() - start_time
        logger.error(f"SQL query failed after {elapsed:.2f}s: {str(e)}")
        raise ToolError(
            f"Elasticsearch SQL connection failed: {str(e)}. "
            f"Check that the Elasticsearch cluster is healthy and reachable. "
            f"Verify connection string and credentials."
        )
```

---

### Fix 2.4: Add Structured Logging for Operation Duration

**Location**: `MCP/KB-MCP/mcp_tools_pkg/create_da_config.py` and `modify_kb_config.py`  
**Goal**: Log the duration of each validation step to help diagnose hanging operations.

**Changes**:
```python
import time
import logging

logger = logging.getLogger(__name__)

def create_da_config(...) -> dict:
    """Create a new anomaly detection configuration."""
    
    total_start = time.time()
    logger.info(f"=== Starting create_da_config: name={name} ===")
    
    try:
        # ===== STEP 1: Window Size Validation =====
        step_start = time.time()
        logger.info("Step 1/5: Validating window sizes...")
        validate_window_size(training_window, "training")
        validate_window_size(detection_window, "detection")
        step_elapsed = time.time() - step_start
        logger.info(f"✓ Step 1 completed in {step_elapsed:.2f}s")
        
        # ===== STEP 2: SQL Query Validation =====
        step_start = time.time()
        logger.info("Step 2/5: Validating training query...")
        query_validator = QueryValidator()
        query_validator.validate(training_query)
        step_elapsed = time.time() - step_start
        logger.info(f"✓ Step 2 completed in {step_elapsed:.2f}s")
        
        # ===== STEP 3: Check for Duplicate Names =====
        step_start = time.time()
        logger.info("Step 3/5: Checking for duplicate configuration names...")
        db = connect_mongodb()
        existing = db.anomaly_detection.train_config.find_one({"name": name})
        step_elapsed = time.time() - step_start
        logger.info(f"✓ Step 3 completed in {step_elapsed:.2f}s")
        
        warning_msg = ""
        if existing:
            warning_msg = f"\n⚠️  Warning: A configuration with name '{name}' already exists."
        
        # ===== STEP 4: CRON Validation =====
        step_start = time.time()
        logger.info("Step 4/5: Validating detection frequency (CRON)...")
        validate_cron_expression(detection_frequency)
        step_elapsed = time.time() - step_start
        logger.info(f"✓ Step 4 completed in {step_elapsed:.2f}s")
        
        # ===== STEP 5: Insert into MongoDB =====
        step_start = time.time()
        logger.info("Step 5/5: Inserting configuration into MongoDB...")
        config_doc = {
            "name": name,
            "description": description,
            # ... other fields ...
        }
        result = db.anomaly_detection.train_config.insert_one(config_doc)
        inserted_id = str(result.inserted_id)
        step_elapsed = time.time() - step_start
        logger.info(f"✓ Step 5 completed in {step_elapsed:.2f}s")
        
        total_elapsed = time.time() - total_start
        logger.info(f"=== create_da_config completed in {total_elapsed:.2f}s ===")
        
        return {
            "status": "success",
            "message": f"✓ Configuration '{name}' created successfully (ID: {inserted_id})." + warning_msg,
            "config_id": inserted_id,
        }
        
    except Exception as e:
        total_elapsed = time.time() - total_start
        logger.error(f"=== create_da_config failed after {total_elapsed:.2f}s: {str(e)} ===")
        raise ToolError(str(e))
```

**Log Output Example**:
```
2025-11-21 14:23:45.123 INFO  === Starting create_da_config: name=web-traffic-anomalies ===
2025-11-21 14:23:45.456 INFO  Step 1/5: Validating window sizes...
2025-11-21 14:23:45.500 INFO  ✓ Step 1 completed in 0.04s
2025-11-21 14:23:45.501 INFO  Step 2/5: Validating training query...
2025-11-21 14:23:47.234 INFO  ✓ Step 2 completed in 1.73s
2025-11-21 14:23:47.235 INFO  Step 3/5: Checking for duplicate configuration names...
2025-11-21 14:23:47.501 INFO  ✓ Step 3 completed in 0.27s
2025-11-21 14:23:47.502 INFO  Step 4/5: Validating detection frequency (CRON)...
2025-11-21 14:23:47.605 INFO  ✓ Step 4 completed in 0.10s
2025-11-21 14:23:47.606 INFO  Step 5/5: Inserting configuration into MongoDB...
2025-11-21 14:23:47.890 INFO  ✓ Step 5 completed in 0.28s
2025-11-21 14:23:47.891 INFO  === create_da_config completed in 2.77s ===
```

---

### Fix 2.5: Verify No Blocking ETL Triggers in MCP Tools

**Location**: `MCP/KB-MCP/mcp_tools_pkg/create_da_config.py`, `modify_kb_config.py`  
**Goal**: Audit code to ensure no synchronous ETL or training is triggered.

**Verification Checklist**:
- [ ] `create_da_config()` does NOT call any external APIs synchronously (only MongoDB insert).
- [ ] `modify_kb_config()` does NOT call any external APIs synchronously (only MongoDB update).
- [ ] No `subprocess.call()` or similar that waits for external processes.
- [ ] If any change streams or triggers are used, they are for MongoDB change events only (read-only from MCP perspective).

**Audit Steps**:
1. Search for `subprocess`, `requests.post` (without timeout), `time.sleep()` in both files.
2. Add comment confirmation: `# Verified: No blocking ETL triggers. Changes are fire-and-forget via MongoDB.`

---

### Fix 2.6: Extend Tests for Timeout Handling

**Location**: `MCP/KB-MCP/tests/test_timeouts.py` (new file)  
**Goal**: Test timeout behavior in create/modify operations.

**Changes**:
```python
import pytest
from unittest.mock import patch, MagicMock
from requests.exceptions import Timeout
import time

def test_create_config_handles_slow_extractor_validation():
    """Test that slow extractor validation triggers a timeout error."""
    with patch("mcp_tools_pkg.query_validator.QueryValidator.validate") as mock_validate:
        # Simulate a slow validation
        mock_validate.side_effect = ValueError(
            "Query validation timed out after 10 seconds. "
            "The query may be too complex or the Elasticsearch cluster may be slow. "
            "Try simplifying the query or testing with the 'elasticsearch_sql' tool directly."
        )
        
        with pytest.raises(Exception, match="timed out"):
            create_da_config(
                name="slow-config",
                description="Test",
                training_query="SELECT * FROM logs WHERE @timestamp >= '$from' AND @timestamp < '$to'",
                detection_query="SELECT * FROM logs WHERE @timestamp >= '$from' AND @timestamp < '$to'",
                training_from="2025-11-01T00:00:00Z",
                training_to="2025-11-30T00:00:00Z",
                training_is_active=True,
                detection_is_active=True,
                training_window=3600,
                detection_window=3600,
                detection_frequency="*/5 * * * *",
                detection_start="2025-11-21T00:00:00Z",
                algorithms=[{"alg_name": "zscore", "alg_parameters": [{"dimension": "status"}]}],
            )

def test_elasticsearch_sql_timeout():
    """Test that ES SQL queries timeout gracefully."""
    with patch("requests.post") as mock_post:
        mock_post.side_effect = Timeout("Connection timeout")
        
        with pytest.raises(Exception, match="timed out"):
            elasticsearch_sql("SELECT * FROM logs LIMIT 10")

def test_operation_duration_logging(caplog):
    """Test that operation durations are logged."""
    with patch("mcp_tools_pkg.create_da_config.connect_mongodb") as mock_db:
        with patch("mcp_tools_pkg.create_da_config.QueryValidator.validate") as mock_validate:
            # Setup mocks
            mock_db.return_value.anomaly_detection.train_config.find_one.return_value = None
            mock_db.return_value.anomaly_detection.train_config.insert_one.return_value.inserted_id = "507f1f77bcf86cd799439011"
            mock_validate.return_value = {"valid": True}
            
            # Call create_da_config
            result = create_da_config(...)
            
            # Verify duration logs appear
            assert "completed in" in caplog.text
            assert "Step 1/5" in caplog.text
            assert "Step 2/5" in caplog.text
```

---

## Integration & Testing Strategy

### Phase 1 Testing (Weeks 1–2)

**Test Sequence**:
1. Run unit tests for window validation: `pytest tests/test_validation.py::test_validate_window_size_*`
2. Run unit tests for configuration name uniqueness: `pytest tests/test_create_modify_validation.py::test_create_config_*`
3. Run integration test (manual): Create config with valid windows, verify MongoDB insertion.
4. Run integration test (manual): Create config with duplicate name, verify warning appears.

**Success Criteria**:
- All window validation tests pass.
- All duplicate name tests pass.
- Manual integration tests produce expected output.

### Phase 2 Testing (Weeks 2–3)

**Test Sequence**:
1. Run unit tests for timeout handling: `pytest tests/test_timeouts.py`
2. Run unit tests for query validator: `pytest tests/test_query_validator.py`
3. Run integration test (manual): Create config with slow ES cluster (simulate via mock), verify timeout error.
4. Run integration test (manual): Verify duration logs appear in console.

**Success Criteria**:
- All timeout tests pass.
- Duration logs are clear and helpful.
- No regression in existing create/modify functionality.

---

## Docker Rebuild & Deployment

### After Phase 1 (Window Validation & Name Uniqueness)

```bash
# From project root
docker-compose down kb-mcp
docker build -f MCP/KB-MCP/Dockerfile -t kb-mcp:phase1 .
docker-compose up -d kb-mcp
docker logs -f kb-mcp
```

**Smoke Test**:
```bash
docker exec kb-mcp python -m tests.test_create_modify_validation
```

### After Phase 2 (Timeouts & Logging)

```bash
docker-compose down kb-mcp
docker build -f MCP/KB-MCP/Dockerfile -t kb-mcp:phase2 .
docker-compose up -d kb-mcp
docker logs -f kb-mcp
```

**Smoke Test**:
```bash
docker exec kb-mcp python -m tests.test_timeouts
```

---

## Risk Assessment & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| Very large windows cause downstream issues (ES queries, memory, ETL impact) | Medium | High | Add advisory warnings for windows > 30 days (configurable via LARGE_WINDOW_THRESHOLD_DAYS). Upstream systems (ETL/dispatcher) should enforce pagination/rate-limiting. Add monitoring/alerts for timeout hits and large window requests. |
| Window validation breaks existing configs | Medium | High | Run comprehensive smoke tests; check Docker logs for errors. Verify min=1 second doesn't break any CRON or UI components. |
| Timeouts too aggressive, blocking legitimate queries | Medium | High | Start with conservative values (10s extractor, 5s ES preview); document in `.env`. Add tunable env vars and startup logging showing current values. Add metrics to track timeout hits to tune against real workloads. |
| Duplicate name check adds latency | Low | Low | Index MongoDB on `name` field for fast lookup. Add optional strict mode (`ENFORCE_UNIQUE_CONFIG_NAMES=true`) for production. |
| Logs become too verbose | Low | Medium | Default LOG_LEVEL=INFO for production; allow DEBUG for dev. Step-by-step duration logs only at INFO level; detailed traces at DEBUG. |
| Large windows not handled by ETL/dispatcher | Medium | High | **OUT OF SCOPE for KB-MCP** – but ETL and dispatcher must implement range-splitting, pagination, or graceful rejection of very large series. Recommend reviewing DA job scheduler and downstream systems. |

---

## Rollback Plan

If any phase fails:
1. Revert changes: `git checkout <file>` for affected files.
2. Rebuild container: `docker-compose up --build kb-mcp`
3. Verify with smoke tests.

---

## Sign-Off

**Reviewed By**: [Your Name]  
**Approved By**: [Project Lead]  
**Implementation Start Date**: [To be filled]  
**Phase 1 Target Completion**: [+10 days from start]  
**Phase 2 Target Completion**: [+20 days from start]

---

## Appendix: Environment Variables

**Add to `MCP/KB-MCP/Dockerfile` or `.env`**:

```bash
# Timeout Configuration (seconds)
# These are conservative defaults; tune based on your ES cluster performance and workloads.
# Monitor for timeout errors and increase if queries are legitimate and need more time.
EXTRACTOR_VALIDATION_TIMEOUT_SECONDS=10           # Max time for extractor validation
ELASTICSEARCH_SQL_PREVIEW_TIMEOUT_SECONDS=5      # Max time for ES SQL preview checks
ELASTICSEARCH_SQL_QUERY_TIMEOUT_SECONDS=30       # Max time for actual ES SQL queries

# Window Constraints (seconds)
# Minimum windows enforced by MCP tools (per client request: minimum is 1 second, no maximum)
MIN_TRAINING_WINDOW_SECONDS=1
MIN_DETECTION_WINDOW_SECONDS=1

# Large Window Advisory Threshold (days)
# If training/detection window exceeds this, a warning is emitted.
# Helps catch accidental large requests that could impact downstream systems.
LARGE_WINDOW_THRESHOLD_DAYS=30

# Configuration Name Uniqueness Enforcement (optional strict mode)
# Set to 'true' to reject duplicate config names; default 'false' allows duplicates with warning.
# Useful for production deployments; flexibility for testing/migration scenarios.
ENFORCE_UNIQUE_CONFIG_NAMES=false

# Logging
# Use INFO for production (summary logs); DEBUG for dev/troubleshooting (step-by-step traces).
LOG_LEVEL=INFO
```

---

## Appendix: Updated Configuration Name Uniqueness Documentation

**Update in `describe_mcp_server` docstring**:

```
### Configuration Name Uniqueness

Configuration names are NOT enforced to be unique. You may create multiple 
configurations with the same name if needed. However, this is not recommended 
for clarity and to avoid confusion. When creating a configuration with a 
name that already exists, you will receive a warning message suggesting a 
unique name.

**Why permissive?**
- Allows flexibility for testing and migration scenarios.
- Reduces operational complexity.

**Best Practice**: Use descriptive, unique names like:
- `web-traffic-anomalies-prod-v1`
- `api-response-time-staging-v2`
- `db-query-latency-q4-2025`
```

---

## Appendix: Backward Compatibility & Additional Verification

**Before deploying**, verify:
1. **Minimum window = 1 second**: Run full KB-MCP unit test suite (`pytest tests/`). Confirm CRON parsing and scheduling still work with 1-second windows. Check any downstream UI/API components that might assume minute-level granularity.
2. **Large window warnings**: Test with 31+ day windows; confirm advisory logs appear without blocking insertion.
3. **Duplicate names (permissive mode)**: Verify two configs with same name can be created, each with a unique MongoDB ID.
4. **Optional strict mode**: Test with `ENFORCE_UNIQUE_CONFIG_NAMES=true`; confirm second insert is rejected with clear error.
5. **Timeout behavior**: Simulate slow ES queries (via mock); verify timeouts trigger gracefully with actionable error messages.

**Run**:
```bash
docker exec kb-mcp python -m pytest tests/ -v
docker exec kb-mcp python smoke_test.py
```

**Monitor**:
- Check KB-MCP logs for timeout hits, large window warnings, duplicate name events.
- If many timeouts, log the queries and consider increasing timeout env vars.
- If many large window warnings, evaluate whether users need guidance or if thresholds should change.

---

**Document Status**: Ready for implementation (amended per critiques)  
**Last Updated**: November 21, 2025  
**Version**: 1.1

---

**Critique & Recommendations** (Original; now addressed in amendments above)

- **Change summary**: This plan correctly implements a minimal server-side validation layer (minimum window sizes and timeouts) and adds useful duration logging and warning behavior for duplicate configuration names. It moves validation earlier (good for fast-fail) and introduces configurable timeouts.
- **Risk: Removing maximum windows**: Removing the maximum cap (allowing arbitrarily large training/detection windows) increases the risk that users accidentally request huge time ranges which could: cause long-running Elasticsearch queries, excessive memory/CPU usage, large MongoDB series documents, and negative operational impact on downstream ETL and DA systems. Recommendation: add an advisory and a soft guard — e.g., if requested window > X days (configurable, default e.g. 30 days), emit a prominent WARNING in the response and logs and require an explicit "confirm_large_window" flag for programmatic creation.
- **Operational mitigations**: Enforce upstream safeguards in the ETL/extractor/dispatcher chain (pagination, range-splitting, or rate-limiting). Add monitoring and alerts for slow queries and very large `training_window`/`detection_window` values.
- **Testing gaps**: The updated tests remove max-window checks — add tests covering very large windows to ensure the system behaves (logs a warning, doesn't crash, and ETL can handle large series). Add integration smoke-tests that simulate large windows against a mocked ES to ensure timeouts and graceful failures. (OUT OF SCOPE of the KB MCP!)
- **Duplicate-name behavior**: The plan uses a permissive model with a warning. This is fine for flexibility, but consider adding an optional strict mode (environment toggle) which enforces uniqueness for production deployments. Also ensure MongoDB has an index on `name` to keep the lookup cheap.
- **Timeout tunables**: The default timeouts (10s/5s/30s) are reasonable starting points, but document them and expose them in `.env` / Dockerfile as suggested. Recommend adding metrics for timeout hits so teams can tune them against real workloads.
- **Logging verbosity**: The step-by-step duration logs are invaluable for diagnosing hangs. Ensure log level defaults to `INFO` for production and allow `DEBUG` for deeper traces to avoid noisy logs at scale.
- **User messaging**: Update user-facing error messages to include actionable next steps (e.g., "try a smaller time range, or increase EXTRACTOR_VALIDATION_TIMEOUT_SECONDS"). The current plan includes good examples — keep those.
- **Backward compatibility**: Changing the minimum to 1 second is unlikely to break existing users, but confirm any callers that assumed minute granularity (CRON docs or UI components) still behave properly. Run the KB-MCP unit tests and the MCP client integration tests after making changes.


