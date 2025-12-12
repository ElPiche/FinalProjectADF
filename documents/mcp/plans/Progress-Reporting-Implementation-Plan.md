# Progress Reporting & Timeout Implementation Plan
**Date:** November 22, 2025  
**Target:** KB-MCP Tool Hanging Issue Resolution

---

## Problem Statement

### Critical Issue
AI clients (Copilot, Claude Desktop) experience **perceived tool hangs** when using KB-MCP tools:
- Tools complete server-side but clients appear stuck for 30+ minutes
- No feedback during MongoDB/Elasticsearch operations
- No timeout enforcement (operations should complete in <60 seconds)
- Warnings/structured responses may confuse MCP clients

### Root Causes Identified
1. **No Progress Reporting**: AI clients have no indication of ongoing work
2. **No Timeout Enforcement**: Operations can theoretically run indefinitely
3. **Unclear Response Structure**: Warnings and multi-step responses delay client rendering
4. **Missing Context Injection**: Tools don't use FastMCP `Context` for progress updates

---

## Research Findings: FastMCP Progress API

### Key Capabilities Discovered

#### 1. **Progress Reporting via Context**
FastMCP provides `ctx.report_progress()` for real-time updates:
```python
@mcp.tool()
async def process_items(items: list[str], ctx: Context) -> dict:
    total = len(items)
    for i, item in enumerate(items):
        await ctx.report_progress(progress=i, total=total)
        # ... work ...
    return {"processed": len(items)}
```

**Three Progress Modes:**
- **Percentage-based**: `ctx.report_progress(progress=50, total=100)` → 50% complete
- **Absolute**: `ctx.report_progress(progress=3, total=5)` → "3 of 5 items"
- **Indeterminate**: `ctx.report_progress(progress=files_found)` → spinner with count

#### 2. **Logging Levels**
Context provides structured logging visible to AI clients:
```python
await ctx.info("Starting MongoDB validation")
await ctx.debug("Query result: 42 rows")
await ctx.warning("⚠️ Duplicate name detected")
await ctx.error("Connection failed")
```

#### 3. **Client-Side Timeout Handling**
Clients can enforce timeouts when calling tools:
```python
# Client-side timeout (2 seconds max)
result = await client.call_tool(
    "create_da_config", 
    {"name": "test"}, 
    timeout=2.0
)
```

#### 4. **Progress Handlers**
Clients can register custom progress handlers:
```python
async def my_progress_handler(progress: float, total: float | None, message: str | None):
    print(f"Progress: {progress}/{total} - {message}")

result = await client.call_tool(
    "long_running_task",
    progress_handler=my_progress_handler
)
```

---

## Implementation Plan

### Phase 1: Add Context Injection (High Priority)
**Goal:** Enable progress reporting in all KB-MCP tools  
**Timeline:** Immediate (next deployment)

#### Changes Required

1. **Update Tool Signatures**
   ```python
   # BEFORE (current)
   def create_da_config(
       name: str,
       description: str,
       # ... other params
   ) -> str:
   
   # AFTER
   async def create_da_config(
       name: str,
       description: str,
       # ... other params
       ctx: Context  # Add context parameter
   ) -> str:
   ```

2. **Convert to Async**
   - Change all tool functions from `def` → `async def`
   - Add `await` to MongoDB/Elasticsearch calls
   - Use `asyncio.sleep()` instead of `time.sleep()` if needed

3. **Add Progress Reporting Points**
   ```python
   async def create_da_config(..., ctx: Context) -> str:
       total_steps = 5
       
       # Step 1: Window validation
       await ctx.info("Step 1/5: Validating window sizes")
       await ctx.report_progress(progress=1, total=total_steps)
       # ... validation logic ...
       
       # Step 2: Schema validation
       await ctx.info("Step 2/5: Validating configuration payload")
       await ctx.report_progress(progress=2, total=total_steps)
       # ... schema logic ...
       
       # Step 3: Query validation (Elasticsearch)
       await ctx.info("Step 3/5: Validating queries against Elasticsearch")
       await ctx.report_progress(progress=3, total=total_steps)
       # ... query validation ...
       
       # Step 4: MongoDB duplicate check
       await ctx.info("Step 4/5: Checking for duplicate names")
       await ctx.report_progress(progress=4, total=total_steps)
       # ... duplicate check ...
       
       # Step 5: Save to MongoDB
       await ctx.info("Step 5/5: Saving configuration to MongoDB")
       await ctx.report_progress(progress=5, total=total_steps)
       # ... save ...
       
       await ctx.info("✅ Configuration created successfully")
       return result_message
   ```

4. **Replace Print/Log Statements**
   ```python
   # BEFORE
   log_message("Validating windows", "info", ...)
   
   # AFTER
   await ctx.info("Validating windows")
   await ctx.debug(f"training_window={training_window}")
   ```

5. **Warning Handling**
   ```python
   # BEFORE
   warnings.append("⚠️ Large window size")
   
   # AFTER
   await ctx.warning("⚠️ Large window size detected (>30 days)")
   warnings.append("⚠️ Large window size")  # Still include in final response
   ```

---

### Phase 2: Add Timeout Enforcement (High Priority)
**Goal:** Prevent operations from running >60 seconds  
**Timeline:** Immediate (next deployment)

#### Changes Required

1. **Add Timeout Constants**
   ```python
   # mcp_tools_pkg/config.py
   import os
   
   # Server-side timeouts (fail-fast)
   MAX_TOOL_EXECUTION_TIME = int(os.getenv("MAX_TOOL_EXECUTION_TIME", "60"))  # 60s
   MONGODB_OPERATION_TIMEOUT = int(os.getenv("MONGODB_OPERATION_TIMEOUT", "10"))  # 10s
   ELASTICSEARCH_QUERY_TIMEOUT = int(os.getenv("ELASTICSEARCH_QUERY_TIMEOUT", "15"))  # 15s
   EXTRACTOR_VALIDATION_TIMEOUT = int(os.getenv("EXTRACTOR_VALIDATION_TIMEOUT", "20"))  # 20s
   ```

2. **Wrap Operations with asyncio.timeout**
   ```python
   import asyncio
   from mcp.server.fastmcp.exceptions import ToolError
   
   async def create_da_config(..., ctx: Context) -> str:
       try:
           async with asyncio.timeout(MAX_TOOL_EXECUTION_TIME):
               # All tool logic here
               await ctx.info("Starting configuration creation")
               # ... steps ...
               return result
       except TimeoutError:
           await ctx.error(f"❌ Operation timed out after {MAX_TOOL_EXECUTION_TIME}s")
           raise ToolError(
               f"Configuration creation exceeded timeout ({MAX_TOOL_EXECUTION_TIME}s). "
               "Check MongoDB/Elasticsearch connectivity."
           )
   ```

3. **Add MongoDB Timeout**
   ```python
   # db.py
   def connect_mongodb():
       return MongoClient(
           mongo_connection_string,
           serverSelectionTimeoutMS=MONGODB_OPERATION_TIMEOUT * 1000,
           connectTimeoutMS=5000,
           socketTimeoutMS=MONGODB_OPERATION_TIMEOUT * 1000
       )
   ```

4. **Add Elasticsearch Timeout**
   ```python
   # mcp_tools_pkg/elasticsearch_sql.py
   async def elasticsearch_sql(query: str, ctx: Context = None) -> dict:
       try:
           async with asyncio.timeout(ELASTICSEARCH_QUERY_TIMEOUT):
               response = requests.post(
                   f"{ELASTICSEARCH_HOST}/_sql",
                   json={"query": query},
                   timeout=ELASTICSEARCH_QUERY_TIMEOUT  # HTTP-level timeout too
               )
               # ...
       except TimeoutError:
           if ctx:
               await ctx.error(f"Elasticsearch query timed out after {ELASTICSEARCH_QUERY_TIMEOUT}s")
           raise ToolError("Elasticsearch query timeout")
   ```

---

### Phase 3: Improve Response Structure (Medium Priority)
**Goal:** Make success/warning/error states clearer to AI clients  
**Timeline:** Next iteration

#### Changes Required

1. **Structured Response Format**
   ```python
   # Return consistent JSON structure
   return json.dumps({
       "status": "success",  # or "warning" or "error"
       "message": "Configuration created successfully",
       "config_id": str(result.inserted_id),
       "warnings": warnings,  # List of warning strings
       "duration_ms": int((time.time() - total_start) * 1000),
       "metadata": {
           "config_name": name,
           "algorithm_count": len(algorithms)
       }
   }, indent=2)
   ```

2. **Early Returns for Errors**
   ```python
   # Instead of collecting errors, fail fast
   if not training_window > 0:
       await ctx.error("❌ training_window must be positive")
       raise ToolError("Invalid training_window: must be > 0")
   ```

3. **Final Status Message**
   ```python
   # Always end with clear completion signal
   if warnings:
       await ctx.warning(f"⚠️ Completed with {len(warnings)} warning(s)")
   else:
       await ctx.info("✅ All checks passed")
   
   await ctx.report_progress(progress=total_steps, total=total_steps)
   ```

---

### Phase 4: Add Notifications (Low Priority)
**Goal:** Notify clients about resource changes  
**Timeline:** Future enhancement

#### Changes Required
```python
# After creating/modifying a config
await ctx.session.send_resource_list_changed()

# After updating a specific config
from urllib.parse import AnyUrl
await ctx.session.send_resource_updated(
    AnyUrl(f"kb://config/{config_id}")
)
```

---

## Docker Environment Variables

Add to `docker-compose.yml`:
```yaml
services:
  kb-mcp:
    environment:
      # Timeout configurations (seconds)
      - MAX_TOOL_EXECUTION_TIME=60
      - MONGODB_OPERATION_TIMEOUT=10
      - ELASTICSEARCH_QUERY_TIMEOUT=15
      - EXTRACTOR_VALIDATION_TIMEOUT=20
      
      # Progress reporting
      - ENABLE_PROGRESS_REPORTING=true
      - LOG_LEVEL=info
```

---

## Testing Strategy

### Unit Tests
```python
# tests/test_progress_reporting.py
import pytest
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_create_config_reports_progress():
    mock_ctx = AsyncMock()
    
    result = await create_da_config(
        name="test",
        # ... other params
        ctx=mock_ctx
    )
    
    # Verify progress was reported 5 times (5 steps)
    assert mock_ctx.report_progress.call_count == 5
    
    # Verify final progress = 100%
    mock_ctx.report_progress.assert_any_call(progress=5, total=5)
```

### Integration Tests
```python
@pytest.mark.asyncio
async def test_timeout_enforcement():
    mock_ctx = AsyncMock()
    
    # Mock MongoDB to hang indefinitely
    with patch("db.connect_mongodb") as mock_mongo:
        mock_mongo.return_value.anomaly_detection.train_config.insert_one = AsyncMock(
            side_effect=lambda x: asyncio.sleep(100)  # Hang for 100s
        )
        
        with pytest.raises(ToolError, match="timed out"):
            await create_da_config(..., ctx=mock_ctx)
        
        # Verify error was logged
        mock_ctx.error.assert_called()
```

### End-to-End Test (Claude Desktop)
1. Configure Claude Desktop with KB-MCP
2. Create a config with verbose logging
3. Observe progress messages in Claude UI:
   - "Step 1/5: Validating window sizes"
   - "Step 2/5: Validating configuration payload"
   - etc.
4. Verify completion within 60s

---

## Migration Checklist

### Files to Modify

- [ ] **mcp_tools_pkg/create_da_config.py**
  - Add `ctx: Context` parameter
  - Convert to `async def`
  - Add 5 progress reporting points
  - Add timeout wrapper
  - Replace log_message with ctx.info/debug/warning

- [ ] **mcp_tools_pkg/modify_kb_config.py**
  - Same changes as create_da_config.py

- [ ] **mcp_tools_pkg/list_kb_configurations.py**
  - Add `ctx: Context` parameter
  - Report progress for each config loaded
  - Add timeout for MongoDB query

- [ ] **mcp_tools_pkg/elasticsearch_sql.py**
  - Add `ctx: Context` parameter
  - Add timeout wrapper
  - Report query execution progress

- [ ] **mcp_tools_pkg/query_validator.py**
  - Add `ctx: Context` parameter
  - Report validation progress

- [ ] **mcp_tools.py** (shim layer)
  - Update tool decorators to pass `ctx`
  - Ensure all delegated calls include context

- [ ] **db.py**
  - Add timeout configurations to MongoDB client
  - Add async wrappers if needed

- [ ] **requirements.txt**
  - Verify `mcp>=1.0.0` supports Context injection
  - Add `asyncio` if not already present

- [ ] **tests/**
  - Update all tests to use `AsyncMock`
  - Add progress reporting assertions
  - Add timeout tests

- [ ] **docker-compose.yml**
  - Add environment variables for timeouts

- [ ] **Dockerfile.kb-mcp**
  - Copy updated tests/ directory
  - Add pytest to requirements.txt

---

## Rollback Plan

If issues arise:
1. Revert to commit before Context injection
2. Keep timeout constants but remove `async with asyncio.timeout()`
3. Keep structured logging in utils.py as fallback

---

## Expected Outcomes

### Before (Current State)
- AI client calls `create_da_config`
- 0-30+ seconds: No feedback, appears hung
- Client may timeout or wait indefinitely
- No visibility into MongoDB/Elasticsearch operations

### After (Phase 1 + Phase 2)
- AI client calls `create_da_config`
- 0s: "Step 1/5: Validating window sizes" (20% progress)
- 2s: "Step 2/5: Validating configuration payload" (40% progress)
- 5s: "Step 3/5: Validating queries against Elasticsearch" (60% progress)
- 7s: "Step 4/5: Checking for duplicate names" (80% progress)
- 9s: "Step 5/5: Saving configuration to MongoDB" (100% progress)
- 10s: "✅ Configuration created successfully"
- **OR** if timeout: "❌ Operation timed out after 60s" with ToolError

### User Experience Improvement
- **Real-time feedback**: AI sees progress messages immediately
- **No hangs**: Maximum 60s wait (configurable)
- **Clear errors**: Timeout errors explain what failed
- **Confidence**: Users know the tool is working

---

## Performance Considerations

### Overhead of Progress Reporting
- Each `ctx.report_progress()` call: ~1-5ms (negligible)
- Each `ctx.info()` call: ~1-3ms
- **Total overhead per tool call**: <50ms

### Network Latency
- MongoDB operations: 10-500ms
- Elasticsearch queries: 50-2000ms
- Extractor validation: 500-5000ms
- **Total typical execution**: 2-10s (well within 60s limit)

### Edge Cases
- **MongoDB down**: Timeout after 10s, fail with clear error
- **Elasticsearch down**: Timeout after 15s, fail with clear error
- **Extractor slow**: Timeout after 20s, warn user to check service
- **Network partition**: Master timeout (60s) catches all

---

## Documentation Updates

### Update README.md
```markdown
## Progress Reporting

All KB-MCP tools now support real-time progress reporting:
- Step-by-step updates visible in AI client
- Configurable timeouts (default 60s)
- Structured error messages

### Environment Variables
- `MAX_TOOL_EXECUTION_TIME`: Master timeout (default 60s)
- `MONGODB_OPERATION_TIMEOUT`: MongoDB timeout (default 10s)
- `ELASTICSEARCH_QUERY_TIMEOUT`: Elasticsearch timeout (default 15s)
```

### Update MCP/Documentation/KB-MCP-Usage-Guide.md
- Add section on progress reporting
- Add troubleshooting for timeout errors
- Add examples of progress messages

---

## Metrics & Monitoring

### Add Structured Logs
```python
await ctx.debug(json.dumps({
    "event": "tool_execution",
    "tool": "create_da_config",
    "duration_ms": 2345,
    "steps_completed": 5,
    "warnings": len(warnings),
    "success": True
}))
```

### MongoDB Logging
- Track average execution time per tool
- Track timeout occurrences
- Track warning frequency

---

## Conclusion

This plan addresses the **perceived hanging issue** by:
1. **Adding real-time progress reporting** so AI clients see activity
2. **Enforcing strict timeouts** so operations fail fast (max 60s)
3. **Improving response structure** so success/warning/error states are clear
4. **Maintaining backward compatibility** via the mcp_tools.py shim

**Priority:** Implement Phase 1 + Phase 2 immediately to resolve user-reported hangs.

**Estimated Implementation Time:** 4-6 hours for Phase 1+2, 2 hours for testing.

**Risk Level:** Low (FastMCP Context API is stable, timeouts are defensive)
