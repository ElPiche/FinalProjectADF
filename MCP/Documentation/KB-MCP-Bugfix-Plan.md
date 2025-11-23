# KB-MCP Bugfixes & Hardening Plan

Date: 2025-11-21  
Based on: KB-MCP Comprehensive Testing Report (2025-11-21)  
Status: Draft for Implementation

---

## Overview

This plan addresses the key issues identified in the comprehensive testing report for the KB-MCP (Knowledge Base Model Context Protocol) server. The system is broadly production-ready, but requires fixes for input validation gaps, long-running/hanging behaviors, and security clarifications. The plan prioritizes high-severity items first, with clear implementation steps per affected module.

### Key Themes Addressed
- **Input Validation Gaps**: Window sizes, configuration names, and timeouts.
- **Performance & Hanging**: Explicit timeouts for validation steps to prevent user-perceived hangs.
- **Security & Documentation**: Clarify Elasticsearch SQL injection risks and provide caller guidance.
- **Robustness**: Better error handling and logging for complex operations.

### Assumptions
- **Uniqueness Policy**: Keep configuration names permissive (allow duplicates) but add a warning in success messages when a name already exists. Document this behavior clearly.
- **ETL Triggers**: No synchronous ETL or training work should be triggered from MCP tools. If any downstream processes are invoked, they must be asynchronous or fire-and-forget to avoid blocking the MCP response.
- **Elasticsearch SQL Security**: Confirmed that Elasticsearch SQL is a parameterized API over indexed documents, not a classic RDBMS. "Injection" risk is limited to logical query manipulation (e.g., broadening WHERE clauses), not arbitrary code execution or DDL. MCP relays full SQL from callers, so upstream applications must sanitize inputs.

---

## Implementation Steps

### 1. Add Window Size Validation (High Priority)
**Severity**: High (prevents nonsensical configs; low risk to existing good configs).  
**Necessity**: Must-fix now to enforce positive window values.

**Affected Files**:
- `mcp_tools_pkg/create_da_config.py`
- `mcp_tools_pkg/modify_kb_config.py`
- `validation.py` (optional: add shared helper)

**Changes**:
- Enforce `training_window > 0` and `detection_window > 0`.
- Optionally cap windows (e.g., max 86400 seconds / 24 hours) via constants or env vars.
- Return clear `ToolError` messages like "training_window must be > 0 and <= MAX_TRAINING_WINDOW_SECONDS".
- Add validation early in the function, before heavy SQL checks, to fail fast.

**Tests**:
- Extend `tests/test_create_modify_validation.py`:
  - Add cases where negative/zero windows are rejected with specific error messages.
  - Verify in-range windows are accepted.

**Implementation Notes**:
- Use constants like `MAX_TRAINING_WINDOW_SECONDS = 86400` at the top of each file.
- For `modify_kb_config`, only validate if the window is being updated (check if parameter is not None).

### 2. Introduce Request/Validation Timeouts (High Priority)
**Severity**: High (directly addresses hanging reports and improves UX).  
**Necessity**: Must-fix now to prevent long-running operations.

**Affected Files**:
- `mcp_tools_pkg/query_validator.py`
- `mcp_tools_pkg/elasticsearch_sql.py` (if timeouts are set there)
- `mcp_tools_pkg/create_da_config.py`
- `mcp_tools_pkg/modify_kb_config.py`

**Changes**:
- Make timeouts configurable via env vars (e.g., `EXTRACTOR_VALIDATION_TIMEOUT_SECONDS=10`).
- Default to conservative values (e.g., 10s for extractor, 5s for ES SQL previews).
- On timeout, raise a clear `ToolError` like "Validation timed out; query may be too complex or cluster too slow. Test with elasticsearch_sql directly."
- Ensure `requests.post` in `QueryValidator` uses the timeout.
- For `elasticsearch_sql` calls in create/modify, wrap with try/except for timeouts.

**Tests**:
- Use monkeypatch to simulate slow responses (e.g., sleep > timeout).
- Assert that the tool fails fast with a timeout error message.

**Implementation Notes**:
- Update `QueryValidator.validate` to accept a `timeout` parameter (already exists; make it configurable).
- Add logging for timeout events to aid debugging.

### 3. Clarify Configuration Name Uniqueness (Medium Priority)
**Severity**: Medium (not correctness-critical, but improves operability).  
**Necessity**: Important hardening; implement as soft enforcement.

**Affected Files**:
- `mcp_tools_pkg/create_da_config.py`
- `mcp_tools_pkg/modify_kb_config.py` (if names can be changed)
- `mcp_tools.py` (update `describe_mcp_server` docstring)

**Changes**:
- Before insert in `create_da_config`, query MongoDB for existing docs with the same `name`.
- If found, add a warning to the success message: "Warning: Configuration name 'X' already exists; consider using a unique name."
- Document this behavior in `describe_mcp_server` and README.md.
- Do not enforce hard uniqueness (keep permissive to avoid breaking existing workflows).

**Tests**:
- Extend `tests/test_create_modify_validation.py`:
  - Mock MongoDB to simulate existing names.
  - Verify warning appears in success message.

**Implementation Notes**:
- Use `connect_mongodb()` and query on `{"name": name}`.
- Run this check early, before SQL validation, to fail fast if needed (but since it's permissive, it's just a warning).

### 4. Improve Handling of Hanging Operations (High Priority for UX)
**Severity**: High for user experience, Medium for correctness.  
**Necessity**: Must-fix now to address hanging reports.

**Affected Files**:
- `mcp_tools_pkg/create_da_config.py`
- `mcp_tools_pkg/modify_kb_config.py`
- `mcp_tools_pkg/query_validator.py`
- `mcp_tools_pkg/elasticsearch_sql.py`

**Changes**:
- Ensure all validation paths use timeouts (see Step 2).
- Add structured logging for start/end of operations, including durations of each step (e.g., "SQL validation took 2.5s").
- Confirm no synchronous ETL/triggering happens in MCP tools (if it does, make it async or remove).
- If complex queries still hang, consider adding a "complexity heuristic" (e.g., reject queries with >N JOINs or subqueries).

**Tests**:
- Add performance-oriented tests (manual/skipped-by-default) that simulate slow validations and verify timeouts trigger.

**Implementation Notes**:
- Use `time.time()` to measure durations and log them.
- If ETL is triggered, wrap it with a timeout or convert to a job queue pattern (out of scope for this plan).

### 5. Security Posture: Elasticsearch SQL Guidance (Medium Priority)
**Severity**: Medium (implementation is constrained; main risk is upstream misuse).  
**Necessity**: Important for documentation and defense.

**Affected Files**:
- `mcp_tools.py` (update `_elasticsearch_sql_docstring()`)
- `mcp_tools_pkg/describe_mcp_server.py`
- `README.md`

**Changes**:
- Add a "Security" subsection to docstrings and docs:
  - Explain that Elasticsearch SQL is not classic RDBMS SQL; no stored procedures/DDL, but queries can over-select or expose data.
  - Callers must treat SQL text as privileged; do not accept arbitrary end-user SQL without a policy layer.
- Optional: Add index-allowlist checks (e.g., reject queries not matching `.ds-kibana_sample_data_logs-*`).

**Tests**:
- No new tests needed; document in README.

**Implementation Notes**:
- Update docstrings to include security notes.

### 6. Performance & Stress Tests (Lower Priority)
**Severity**: Low–Medium (helps future regressions).  
**Necessity**: Follow-up; not blocking.

**Affected Files**:
- `tests/` (new file like `test_performance.py`)
- `KB-MCP-SQL-Migration-Report.md` (add section)

**Changes**:
- Add a small performance test suite to reproduce complex queries.
- Document scenarios and expectations.

**Tests**:
- Mock slow responses and verify handling.

---

## Severity & Necessity Summary

- **High Priority / Must-Fix Now**:
  - Window validation.
  - Explicit timeouts for validations.
  - Hanging operation handling (via timeouts and logging).

- **Medium Priority / Important Hardening**:
  - Configuration name uniqueness (soft).
  - Security documentation for Elasticsearch SQL.

- **Lower Priority / Strategic**:
  - Performance tests.
  - Additional algorithms (out of scope).

---

## Next Steps

1. Confirm any adjustments to the plan (e.g., uniqueness policy or ETL handling).
2. Implement changes in order: Start with window validation and timeouts.
3. Run tests after each change to ensure no regressions.
4. Update the comprehensive testing report with fix status.
5. Rebuild and re-test the MCP container.

If ready, I can begin implementing the high-priority fixes (e.g., window validation in `create_da_config.py`).