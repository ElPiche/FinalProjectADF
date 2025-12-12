## KB-MCP Improvements Plan

Date: 2025-11-02

Purpose: keep a single tracked plan describing improvements to the KB-MCP API and tools so automated clients (including Model Context Protocol callers) and human operators can work reliably and with minimal trial-and-error.

Summary of changes from the earlier report
- The `describe_mcp` (server description) must include concrete, testable plain-text examples of valid create and modify inputs for KB configs so callers can exercise the MCP endpoints reliably.
- Testing policy updated: the only accepted functional verification method is calling the MCP server directly via the Model Context Protocol (MCP). Other 'smoke tests' are optional; the canonical verification is an MCP call with the tool and confirming the returned response and context.

High-level action items (prioritized)

1) Audit tool descriptions (in-progress)
- Add accurate, human-readable descriptions to all MCP tool metadata so runtime warnings like "Tool X does not have a description" disappear. Tools to cover include: create_da_config, modify_kb_config, list_kb_configurations, describe_mcp_server, list_available_algorithms, ping_elasticsearch, elasticsearch_sql.
- Deliverable: updated tool manifest and service registration with a summary, inputs/outputs overview, and a short example (plain text) for each tool.

2) Publish canonical algorithm schema
- Create and publish a single canonical description of the algorithm object (fields, types, required/optional, meaning). Ensure the canonical field name for the metric is documented as "dimension" and list synonyms (observedValue -> dimension).

3) Make API examples authoritative
- Ensure examples returned by the API match the canonical schema exactly (no ambiguous names). Add an automated check to compare example output to the canonical schema.

4) Add validate-only (dry-run) mode
- Implement a validation-only option for create/modify endpoints that runs schema validation, parses ES-SQL against the configured dialect, resolves index patterns, and returns diagnostic details without persisting data.

5) Improve error responses with hints
- Enrich validation and SQL parse errors with structured, machine-friendly information: field path, short human reason, a plain-text `hint` recommending fixes, and whether the error is client-fixable.

6) Index/table discovery helper
- Add an index discovery helper that accepts an index pattern or proposed table name and returns exact matches, fuzzy suggestions and an explicit 'no-match' result with alternatives.

7) Echo canonical resource on create/modify
- Change create/modify endpoints to return the fully-normalized saved resource in the response body (canonical names, defaults applied), or a direct pointer to it.

8) Document ES-SQL dialect constraints
- Add a short, human-readable section to the API docs summarizing the supported ES-SQL subset (INTERVAL formats, LIMIT placement, supported aggregates) and include common pitfalls.

9) Update CLI/UI to show plain-text form examples
- Change interactive create/modify flows to show a labelled Key: Value form (no JSON by default) and include a "validate" toggle which calls the validate-only mode.

10) Tests and CI (MCP-focused)
- Tests must call the MCP server via the Model Context Protocol for functional verification. The repository may include unit tests for pure library functions, but functional acceptance requires an MCP call to the tool and validation of the returned context.

11) Rollout plan
- Incremental rollout with feature flags or query params to avoid breaking changes. Start with docs and tool descriptions, then canonical schema, then validate-only, then hints and discovery, then echo-on-create.

Testing policy (MCP-first)
- The only authoritative functional test for the MCP tools is to call them via the Model Context Protocol and validate the response and returned context. Any automated test that does not exercise the MCP endpoint directly is considered incomplete for acceptance.
- For each functional change, create a single MCP call sequence demonstrating:
  - A dry-run (where implemented) showing validation diagnostics for an intentionally-bad payload.
  - A valid create/modify call executed through MCP and the returned canonical resource/context.
  - A list operation (list_kb_configurations) executed through MCP that shows the created/modified config present and normalized.

How `describe_mcp` should behave and examples it must provide
- `describe_mcp` must return not only API surface metadata but also a short, plain-text labelled form example demonstrating how to write and modify a valid KB config. The example must be written in Key: Value form (no JSON) and must use canonical field names. The server's `describe_mcp` output should also: list known synonyms and map them to canonical fields; show a brief example of a valid ES-SQL snippet (annotated); and point to the index discovery helper.

Canonical, plain-text labelled form example (must appear in docs and `describe_mcp` output)
- Name: A short name for the KB config (required)
- Description: Short description (optional)
- Algorithm:
  - name: Algorithm identifier (for example: zscore)
  - dimension: Canonical metric field to evaluate (preferred name; synonyms: observedValue, metric)
  - parameters: Optional tuning parameters (list by plain name and short meaning)
- Training period:
  - from: ISO timestamp for training start
  - to: ISO timestamp for training end
- Detection schedule: A cron-like expression or schedule description
- Index/Table: Name of the Elasticsearch table or index to query. Use the index discovery helper if unsure.

Notes on the example
- This example is intentionally non-code and labelled so both humans and automated MCP clients can present the form to users and validate entries. When `create_da_config` or `modify_kb_config` is called through MCP, the server must accept canonical keys (e.g., dimension) and also return a validation hint if synonyms were used.

Acceptance criteria (practical)
- `describe_mcp` returns API metadata and a plain-text labelled form example (canonical field names + synonyms). The example must be sufficient for an MCP caller to construct a valid create/modify payload.
- The tool manifest contains human-readable descriptions for the listed tools and the runtime warnings about missing tool descriptions no longer appear.
- Validate-only/dry-run returns field-level diagnostics and SQL parse hints for bad payloads.
- Create/modify responses contain the canonical saved resource in the response body (or a pointer to it) when not a dry-run.

Next steps (immediate)
- Update tool metadata and `describe_mcp` output to include the plain-text form example and synonyms mapping. This is the fastest way to remove the logged warnings and reduce friction for automated clients.
- After that, implement validate-only and enriched hints in the validation layer.

Owner: KB-MCP team

Revision history
- 2025-11-02 — Initial plan and MCP-only testing policy added.
