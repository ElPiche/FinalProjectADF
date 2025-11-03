# KB-MCP Refactor Plan (no-git)

## ⚠️ CRITICAL REQUIREMENTS

**KB-MCP MUST RUN IN DOCKER** - This is a non-negotiable requirement for production deployment and MCP integration. The modular architecture is designed specifically for containerized execution with proper network isolation and service dependencies.

- **Deployment**: Always use `docker-compose.yml` kb-mcp service
- **MCP Integration**: Use Docker exec commands in `.kilocode/mcp.json`
- **Network**: Container-to-container communication via Docker networks
- **No Direct Execution**: Do not run `python kb-mcp.py` directly on host

## Summary
- Goal: split monolithic [`MCP/KB-MCP/kb-mcp.py`](MCP/KB-MCP/kb-mcp.py:1) into small modules without behavior change.
- Constraint: no git; track progress inside this file and small backup files.

## High-level decisions
- Keep original entrypoint [`MCP/KB-MCP/kb-mcp.py`](MCP/KB-MCP/kb-mcp.py:1) as façade while refactoring.
- Minimal instrumentation only (timers, logs, optional timeouts).

## Initial analysis tasks (order)
1. Inspect top-level imports and globals in [`MCP/KB-MCP/kb-mcp.py`](MCP/KB-MCP/kb-mcp.py:1).
2. List @mcp.tool() functions and their dependencies.
3. Identify heavy imports: fastmcp, pydantic, pymongo, elasticsearch, croniter.
4. Find blocking calls: connect_mongodb(), Elasticsearch calls, mcp.run(), any long loops.

## Minimal module layout (filenames and concrete items to move)
- MCP/KB-MCP/models.py
  - KBConfig, ZScoreConfig, scheduling* Pydantic models and CRON/UUID/SQL wrapper classes.
- MCP/KB-MCP/validation.py
  - extract_sql_output_fields, extract_sql_select_fields, _split_eval_assignments, _split_stats_fields, validate_algorithms, SQL._is_valid_sql.
- MCP/KB-MCP/db.py
  - connect_mongodb(), MongoClient wrappers, configurable timeouts, safe close helpers.
- MCP/KB-MCP/mcp_tools.py
  - create_da_config, modify_kb_config, list_kb_configurations, describe_mcp_server, list_available_algorithms, elasticsearch_sql (tool handlers).
- MCP/KB-MCP/utils.py
  - log_message wrapper, StructuredLogger class (or keep StructuredLogger but move gradually), simple file helpers.
- MCP/KB-MCP/instrumentation.py
  - timed decorator, watch decorator, small helper to run functions with timeout wrapper (only if needed).

## Incremental refactor workflow (preserve behavior at every step)
1) Baseline capture (do not modify files)
   - Commands:
     - python MCP/KB-MCP/kb-mcp.py --server
     - python -m cProfile -o profile.before MCP/KB-MCP/kb-mcp.py
     - python -m trace --trace MCP/KB-MCP/kb-mcp.py > trace.before.log
   - Save outputs to docs/refactor/profiles/.
2) Create module skeletons (create files listed above with stubs) and update [`MCP/KB-MCP/kb-mcp.py`](MCP/KB-MCP/kb-mcp.py:1) to import from them (stubs return original behavior).
   - Verify startup command still works.
3) Move pure data classes to models.py, keep original definitions in kb-mcp.py as short forwarding aliases (compat shims).
   - Add small unit tests for Pydantic validation (tests/test_models.py).
4) Move deterministic parsing/validation functions to validation.py and adjust imports. Add tests for representative SQL strings.
5) Move DB wrappers to db.py; change connect_mongodb() implementation to call db.connect_mongodb() while keeping the original name in kb-mcp.py (shim).
   - Add serverSelectionTimeoutMS/socketTimeoutMS defaults to 2000ms.
6) Move one MCP tool function at a time to mcp_tools.py, re-export the decorated function in kb-mcp.py (from mcp_tools import create_da_config as create_da_config).
   - After each move: run the server and call a simple tool (describe_mcp_server or list_available_algorithms).
7) Add instrumentation wrappers around heavy calls only after a tool is moved to isolate latency.
8) Replace kb-mcp.py internals with a minimal bootstrap that imports modules and re-exports names. Keep command-line behavior unchanged.
9) Remove obsolete code only after manual verification and passing smoke tests.

## Compatibility shims (pattern)
- While moving X -> module Y add in kb-mcp.py:
  - from .Y import X as X
  - optionally add warnings.warn("Moved, use MCP/KB-MCP/Y.py", DeprecationWarning)

## Validation and testing (lightweight)
- **CRITICAL**: All testing must be done within Docker containers using docker-compose services
- Smoke tests:
  - `docker-compose up kb-mcp` (watch container logs)
  - Use MCP client to call describe_mcp_server via Docker exec
- Unit tests (inside container):
  - `docker exec kb-mcp python test_models.py`
  - `docker exec kb-mcp python test_validation.py`
  - `docker exec kb-mcp python smoke_test.py`
- Hang detection:
  - Compare profile.before -> profile.after using snakeviz or pstats
  - Use trace logs to find last executed lines before hang
  - Container timeouts: Docker health checks and restart policies
  - Use pymongo timeouts (serverSelectionTimeoutMS) and Elasticsearch client timeout options
  - **Never run directly on host** - defeats the Docker requirement

## Exact VS Code integrated terminal commands (Docker-only)
- Baseline run: docker-compose up kb-mcp
- Profile: docker exec kb-mcp python -m cProfile -o profile.before kb-mcp.py
- Trace: docker exec kb-mcp python -m trace --trace kb-mcp.py > trace.before.log
- Unit tests: docker exec kb-mcp python test_models.py && docker exec kb-mcp python test_validation.py
- Smoke test: docker exec kb-mcp python smoke_test.py
- Quick import test: docker exec kb-mcp python -c "import kb_mcp; print('Imports OK')"
- **NEVER run directly**: python MCP/KB-MCP/kb-mcp.py (violates Docker requirement)

## Minimal instrumentation (low intrusion)
- instrumentation.py:
  - def timed(fn): logs start/end and elapsed using time.perf_counter
  - def watch(threshold_s): logs warning when execution exceeds threshold
- Wrap only: connect_mongodb, elasticsearch_sql query call, and heavy validation loops.

## Tracking & progress (no-git workflow)
- Update this file manually with checkboxes as you complete steps.
- Create incremental backups: docs/refactor/step-01-skeleton.md, step-02-models.md etc.
- Keep profiles under docs/refactor/profiles/.

## Estimated effort (per step)
- Baseline capture: 0.5–1h
- Skeleton creation: 0.5h
- Move models: 1–1.5h
- Move validators: 1–1.5h
- Move DB wrappers: 1–1.5h
- Move tools (per tool): 0.5h each
- Final bootstrap & cleanup: 1–2h

## Rollback criteria
- Any smoke test failure or new hang -> revert to the previous saved copy of files (use file system copies).
- Behavioral differences in tool outputs -> restore kb-mcp.py original content from backup.

## Acceptance criteria
- pytest passes: exit code 0
- Server starts with the same command and does not hang at previously observed points
- Tool outputs unchanged for describe_mcp_server and list_available_algorithms
- Profiling shows reduced blocking time or timeouts applied

## Next immediate actions (do now)
- Create these skeleton files: [`MCP/KB-MCP/models.py`](MCP/KB-MCP/models.py:1), [`MCP/KB-MCP/validation.py`](MCP/KB-MCP/validation.py:1), [`MCP/KB-MCP/db.py`](MCP/KB-MCP/db.py:1), [`MCP/KB-MCP/mcp_tools.py`](MCP/KB-MCP/mcp_tools.py:1), [`MCP/KB-MCP/utils.py`](MCP/KB-MCP/utils.py:1), [`MCP/KB-MCP/instrumentation.py`](MCP/KB-MCP/instrumentation.py:1)
- Run baseline profile commands and save outputs to docs/refactor/profiles/

----
Plan created and saved as this file. Follow the Next immediate actions checklist and update this file as you progress.