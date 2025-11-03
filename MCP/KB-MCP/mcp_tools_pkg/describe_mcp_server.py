"""Provide a human-readable description for MCP callers describing available tools and how to use them.

This module returns plain instructions and copy/pasteable examples the AI caller can use
to call the MCP tools. It intentionally avoids internal-only language and focuses on the
exact inputs each tool needs.
"""

import time
import uuid
from utils import log_message as _utils_log_message


def log_message(message: str, level: str = "info", component: str = "mcp_tools", method: str = "entry", **kwargs):
    return _utils_log_message(message, level, component, method, **kwargs)


def describe_mcp_server() -> str:
    """Return human-readable instructions for using KB-MCP tools.

    The returned text lists each exposed tool, required inputs, example payloads (labelled
    and JSON), and common validation error modes. This is intended for external callers
    (AIs and humans) and avoids internal-only implementation details.
    """
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    log_message("Tool execution started", "info", "describe_mcp_server", "entry",
                request_id=request_id)

    text = """
KB-MCP: How to use the tools

Purpose
Return human-readable instructions for using KB-MCP tools. The text below lists each
tool, the inputs it requires, common return shapes, and copy/pasteable examples you can
use directly.

Tools

1) create_da_config
- Inputs:
  - name (string) — configuration name (required)
  - description (string) — short human description (optional)
  - scheduling.training_query (string) — SQL or ES-SQL that returns the columns you will monitor (required)
  - scheduling.detection_query (string) — SQL/ES-SQL for detection runs (required)
  - scheduling.training_from, scheduling.training_to (ISO timestamps)
  - scheduling.detection_frequency (cron string)
  - algorithms (array) — list of algorithm objects; each must include:
    - alg_name (string)
    - alg_parameters (array of objects) where each object includes at least a 'dimension' field naming a column from your query output
- Return: success message and the stored configuration id or a validation error describing the failing field.

2) modify_kb_config
- Inputs: config_id (string) and any create fields to update (all optional)
- Return: confirmation or validation error.

3) list_kb_configurations
- Inputs: none
- Return: Markdown listing saved configurations with name, id, scheduling summary, and algorithms.

4) list_available_algorithms
- Inputs: none
- Return: Markdown showing implemented algorithms and a JSON example showing how to fill the 'algorithms' array.
  - Note: current implemented algorithms: zscore

5) ping_elasticsearch
- Inputs: none
- Return: JSON with ping_success (boolean) and duration_ms (float).

6) elasticsearch_sql
- Inputs: query (string) — the SQL/ES-SQL to run
- Return: JSON with columns and rows so you can confirm which column names your queries produce.

Common notes for callers
- Use `elasticsearch_sql` to validate your queries and inspect column names before using them in `algorithms`.
- The `algorithms` array must use objects like { "alg_name": "zscore", "alg_parameters": [ { "dimension": "your_field" } ] }.
- Timestamps must be ISO 8601 strings.

Plain labelled example (easy to paste):
Name: Geographic Traffic Pattern Analysis
Description: Monitor hourly status code counts and detect spikes in 5xx errors.
scheduling.training_query: SELECT DATE_TRUNC('HOUR', "@timestamp") AS es_timestamp, SUM(CASE WHEN response = '200' THEN 1 ELSE 0 END) AS status_code_200_counter, SUM(CASE WHEN CAST(response AS INTEGER) >= 500 AND CAST(response AS INTEGER) < 600 THEN 1 ELSE 0 END) AS status_code_5xx_counter FROM ".ds-kibana_sample_data_logs-*" WHERE "@timestamp" >= '$from' AND "@timestamp" < '$to' GROUP BY es_timestamp ORDER BY es_timestamp
scheduling.training_from: 2025-10-01T00:00:00Z
scheduling.training_to: 2025-10-09T23:59:59Z
scheduling.detection_query: FROM .ds-kibana_sample_data_logs-* | WHERE @timestamp >= $from AND @timestamp < $to | STATS status_code_200_counter = COUNT(*) WHERE response == "200", status_code_5xx_counter = COUNT(*) WHERE response >= "500" AND response < "600" BY es_timestamp | SORT es_timestamp
scheduling.detection_frequency: */15 * * * *
algorithms:
  - alg_name: zscore
    alg_parameters:
      - dimension: status_code_200_counter
      - dimension: status_code_5xx_counter

JSON example (algorithms only):
```json
{
  "algorithms": [
    {
      "alg_name": "zscore",
      "alg_parameters": [
        { "dimension": "status_code_200_counter" },
        { "dimension": "status_code_5xx_counter" }
      ]
    }
  ]
}
```

"""

    duration_ms = (time.time() - start_time) * 1000
    log_message("Server description generated successfully", "info",
                "describe_mcp_server", "completion", request_id=request_id,
                duration_ms=duration_ms)
    return text
