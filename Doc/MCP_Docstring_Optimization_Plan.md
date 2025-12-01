# MCP Docstring Optimization Plan

## Executive Summary

Optimize KB-MCP tool docstrings for LLM consumption: reduce from **~11,700 tokens to ~1,930 tokens (83% reduction)** while improving clarity. Leverage existing **programmatic description generation** in `description_utils.py`.

---

## Programmatic Generation Strategy

### Existing Infrastructure (description_utils.py)

```python
# Available constants and functions to leverage:
SUPPORTED_ALGORITHMS_LIST = list(SUPPORTED_ALGORITHMS)  # ["zscore"]
SUPPORTED_ALGORITHMS_INLINE = ", ".join(SUPPORTED_ALGORITHMS_LIST)  # "zscore"

def get_supported_algorithms_list() -> str:
    """Returns: 'Currently supported: zscore'"""

def generate_algorithm_config_description() -> str:
    """Generates algorithm config docs from SUPPORTED_ALGORITHMS"""

def generate_tool_list_for_describe_mcp(tools: List[str]) -> str:
    """Generates numbered tool list for describe_mcp_server"""
```

### Implementation Pattern

All docstrings will use f-strings with programmatic insertions:

```python
def _create_da_config_docstring() -> str:
    return f"""Create anomaly detection config.
Algorithms: {SUPPORTED_ALGORITHMS_INLINE}
..."""
```

This ensures algorithm lists **auto-update** when `SUPPORTED_ALGORITHMS` in `models.py` changes.

---

## Tool Disposition (10 → 8 Tools)

| Tool | Action | Rationale |
|------|--------|-----------|
| `create_da_config` | KEEP | Core functionality |
| `modify_kb_config` | KEEP | Core functionality |
| `list_kb_configurations` | KEEP | Essential for workflow |
| `elasticsearch_sql` | KEEP | Query validation critical |
| `describe_mcp_server` | KEEP + MERGE | Absorb algorithm list |
| `create_bucket_profile` | KEEP | Time-context feature |
| `list_bucket_profiles` | KEEP | Profile discovery |
| `delete_bucket_profile` | KEEP | Profile management |
| `list_available_algorithms` | **REMOVE** | Merge into describe_mcp_server |
| `ping_elasticsearch` | **REMOVE** | Errors provide same info |

---

## Optimized Docstrings

### 1. create_da_config (~380 tokens)

```python
def _create_da_config_docstring() -> str:
    return f"""Create anomaly detection configuration.

**Pre-flight:** Validate query with elasticsearch_sql tool first.

**Required:**
- name: Unique config identifier
- description: What this monitors
- source_index: ES index being monitored (e.g., 'app-logs')
- elasticsearch_sql_query: SQL with $from/$to placeholders
- query_mode: {{"type": "raw"|"aggregated", "timestamp_field": "<column>"}}
- training_from/to: ISO 8601 timestamps for training period
- detection_frequency: CRON (5-field or 6-field with seconds)
- detection_window: Seconds per detection cycle
- detection_start: When detection begins (ISO 8601)
- algorithm: {{"name": "{SUPPORTED_ALGORITHMS_INLINE}", "parameters": [{{"dimension": "<column>", "is_active": true}}]}}

**Optional:**
- bucket_profile_id: Link to time-context profile
- anomaly_config: {{"user_emails": ["email@example.com"]}}

**Frequency Limits:** raw mode ≥60s, aggregated ≥10s

ETL triggers on every save. Set is_active=false to pause."""
```

### 2. modify_kb_config (~200 tokens)

```python
def _modify_kb_config_docstring() -> str:
    return f"""Update existing anomaly detection configuration.

**Required:** config_id (MongoDB ObjectId from list_kb_configurations)

**Optional (only specify fields to change):**
- description, elasticsearch_sql_query, query_mode
- training_from/to, training_is_active
- detection_frequency/window/start, detection_is_active
- algorithm, bucket_profile_id, anomaly_config, source_index

**Note:** ETL re-triggers on any change. Use is_active flags to pause.
Use list_kb_configurations first to get config_id and current state."""
```

### 3. list_kb_configurations (~100 tokens)

```python
def _list_kb_configurations_docstring() -> str:
    return """List all saved anomaly detection configurations.

Returns per config: name, ID, description, query summary, training/detection ranges, 
frequency (CRON), algorithm dimensions.

Use to find config_id for modify_kb_config."""
```

### 4. elasticsearch_sql (~450 tokens)

```python
def _elasticsearch_sql_docstring() -> str:
    return """Execute Elasticsearch SQL query and return columns + sample rows.

**CRITICAL:** Always list_indices BEFORE querying. Never assume index exists.

**ES SQL Syntax (differs from standard SQL):**
- Identifiers: Double quotes → "field-name", "@timestamp"
- Strings: Single quotes → 'value'
- FROM: Double-quoted index → FROM "my-index-*"
- GROUP BY: Use aliases or positional (1, 2) or repeat expression
- Date truncation: DATE_TRUNC('hour', "@timestamp") AS bucket
- Conditionals: CASE WHEN condition THEN x ELSE y END
- Pivot counts: SUM(CASE WHEN status=200 THEN 1 ELSE 0 END) AS status_200
- Time filter: WHERE "@timestamp" >= '2025-01-01T00:00:00Z'
- Nested fields: Double quotes for dots → "http.status"

**Config queries must use:** $from and $to placeholders (replaced at runtime)

**Returns:** {"columns": [{"name": "...", "type": "..."}], "rows": [[...]]}

Validate column names match algorithm dimensions exactly."""
```

### 5. describe_mcp_server (~150 tokens)

```python
def _describe_mcp_server_docstring() -> str:
    tools = generate_tool_list_for_describe_mcp([
        "create_da_config", "modify_kb_config", "list_kb_configurations",
        "describe_mcp_server", "elasticsearch_sql",
        "create_bucket_profile", "list_bucket_profiles", "delete_bucket_profile"
    ])
    return f"""Get KB-MCP usage guide and tool documentation.

**Available Tools:**
{tools}

**Supported Algorithms:** {get_supported_algorithms_list()}

Call first when starting KB-MCP work or encountering errors."""
```

### 6. create_bucket_profile (~280 tokens)

```python
def _create_bucket_profile_docstring() -> str:
    return """Create time-context bucket profile for context-aware anomaly detection.

Enables separate baselines for different periods (business hours, holidays, weekends).

**Required:**
- profile_id: Unique identifier (e.g., "business_hours_v1")
- timezone: IANA timezone (e.g., "America/New_York")

**Optional:**
- exceptions: Holiday rules → {"bucket_base_key": "holiday", "rule": {"month": 12, "day": 25}, "granularity": "block"|"hourly"}
- schedule: Recurring patterns → {"bucket_base_key": "workday", "days": [1-5], "time_range": {"start": "09:00", "end": "17:00"}, "granularity": "hourly"}
- fallback: Default bucket → {"bucket_base_key": "off_hours", "granularity": "hourly"}

**Priority:** exceptions → schedule (first match) → fallback

Link to configs via bucket_profile_id in create_da_config."""
```

### 7. list_bucket_profiles (~70 tokens)

```python
def _list_bucket_profiles_docstring() -> str:
    return """List all bucket profiles with usage metadata.

Returns: profile_id, timezone, exception/schedule counts, KB reference count.

Check usage count before deleting (referenced profiles cannot be deleted)."""
```

### 8. delete_bucket_profile (~60 tokens)

```python
def _delete_bucket_profile_docstring() -> str:
    return """Delete bucket profile by profile_id.

**Constraint:** Cannot delete if referenced by any KB configuration.
First update those KBs to remove bucket_profile_id reference."""
```

---

## Token Analysis

| Tool | Original | Optimized | Reduction |
|------|----------|-----------|-----------|
| create_da_config | ~3,500 | ~380 | 89% |
| modify_kb_config | ~2,800 | ~200 | 93% |
| list_kb_configurations | ~800 | ~100 | 88% |
| elasticsearch_sql | ~900 | ~450 | 50% |
| describe_mcp_server | ~1,200 | ~150 | 88% |
| create_bucket_profile | ~1,100 | ~280 | 75% |
| list_bucket_profiles | ~600 | ~70 | 88% |
| delete_bucket_profile | ~500 | ~60 | 88% |
| list_available_algorithms | ~300 | 0 | 100% |
| ping_elasticsearch | ~400 | 0 | 100% |
| **TOTAL** | **~11,700** | **~1,930** | **83%** |

---

## Implementation Checklist

### Phase 1: Code Changes
- [ ] Update `description_utils.py`:
  - [ ] Add `TOOL_LIST` constant for describe_mcp_server
  - [ ] Ensure `generate_tool_list_for_describe_mcp()` works with 8-tool list
- [ ] Update `mcp_tools.py`:
  - [ ] Replace all docstring functions with optimized versions
  - [ ] Use f-strings with `{SUPPORTED_ALGORITHMS_INLINE}` 
  - [ ] Remove `list_available_algorithms` tool registration
  - [ ] Remove `ping_elasticsearch` tool registration
- [ ] Update `mcp_tools_pkg/__init__.py`: Remove deleted tool imports

### Phase 2: Testing
- [ ] Run: `docker exec kb-mcp python -m pytest tests/ -v`
- [ ] Verify describe_mcp_server includes algorithm list
- [ ] Test all 8 tools via Claude Desktop
- [ ] Validate ES SQL queries work with new docstring guidance

### Phase 3: Documentation
- [ ] Update `MCP/claude-config/README.md` with 8-tool list
- [ ] Archive removed tool documentation

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| LLM misunderstands terse docs | ES SQL section kept detailed; examples preserved |
| Algorithm list becomes stale | Programmatic generation from SUPPORTED_ALGORITHMS |
| ping_elasticsearch needed for debugging | Error messages from elasticsearch_sql provide equivalent info |
| Breaking change for Claude configs | describe_mcp_server auto-documents available tools |

---

## Appendix: Removed Tools Justification

### list_available_algorithms → Merged
- **Current:** Separate tool returning algorithm list
- **After:** `describe_mcp_server` includes `{get_supported_algorithms_list()}`
- **Benefit:** One less tool call, same information

### ping_elasticsearch → Removed
- **Current:** Returns `{ping_success: bool, duration_ms: float}`
- **After:** Any elasticsearch_sql call provides connectivity status via success/failure
- **Benefit:** Reduces tool count; connectivity issues surface naturally in workflow
