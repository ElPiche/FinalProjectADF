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
  - name (string) — Unique configuration name (required)
  - description (string) — Human-readable description of what this monitors (optional)
  - scheduling.training_query (string) — SQL query for training data.
      This query should return historical data used to train the anomaly detection models.
      Timestamp values in the query should be filtered using placeholders `$from` and `$to` to define the training period.
      The query result must always include countable integer numeric columns for the algorithms to monitor which going to be the dimensions. (required)
  - scheduling.detection_query (string) — SQL query for detection
      This query should return recent or real-time data used for anomaly detection.
      Timestamp values in the query should be filtered using placeholders `$from` and `$to` and the extractor process will be the one to set these values based on the detection schedule. (required)
  - scheduling.training_from (ISO format) — Training start timestamp.
      Defines the beginning of the historical data period used for training the models.
      Will be substituted for `$from` in the training_query during model training. (required)
  - scheduling.training_to (ISO format) — Training end timestamp.
      Defines the end of the historical data period used for training the models.
      Will be substituted for `$to` in the training_query during model training. (required)
  - scheduling.training_is_active (boolean) — Flag to indicate if training is active.
      If training is not active, the extractor process will skip the training phase. (required)
  - scheduling.detection_is_active (boolean) — Flag to indicate if detection is active.
      If detection is not active, the extractor process will skip the detection phase. (required)
  - scheduling.training_window (integer, seconds) — Training window in seconds.
      Defines the time window size for training data aggregation.
      This value helps the algorithms to process data points within the specified window. (required)
  - scheduling.detection_window (integer, seconds) — Detection window in seconds.
      Defines the time window size for detection data aggregation.
      The extractor process will take this value to extract the last N seconds of data for anomaly detection. (required)
  - scheduling.detection_frequency (cron string) — Detection frequency (CRON format)
      Defines how often the anomaly detection process should run.
      The extractor process will use this CRON expression to schedule detection runs.
      Make sure to provide a valid CRON expression to ensure proper scheduling.
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
- Inputs: query (string) — the SQL query to run
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
scheduling.training_is_active: true
scheduling.detection_is_active: true
scheduling.training_window: 3600
scheduling.detection_window: 3600
scheduling.detection_query: SELECT DATE_TRUNC('HOUR', "@timestamp") AS es_timestamp, SUM(CASE WHEN response = '200' THEN 1 ELSE 0 END) AS status_code_200_counter, SUM(CASE WHEN CAST(response AS INTEGER) >= 500 AND CAST(response AS INTEGER) < 600 THEN 1 ELSE 0 END) AS status_code_5xx_counter FROM ".ds-kibana_sample_data_logs-*" WHERE "@timestamp" >= '$from' AND "@timestamp" < '$to' GROUP BY es_timestamp ORDER BY es_timestamp
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
