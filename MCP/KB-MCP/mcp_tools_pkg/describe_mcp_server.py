"""Provide a human-readable description for MCP callers describing available tools and how to use them.

This module returns plain instructions and copy/pasteable examples the AI caller can use
to call the MCP tools. It intentionally avoids internal-only language and focuses on the
exact inputs each tool needs.
"""

import time
import uuid
from utils import log_message as _utils_log_message
from models import get_supported_algorithms


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

    # Get dynamically supported algorithms
    algorithms = get_supported_algorithms()
    supported_algorithms = ", ".join(sorted(algorithms.keys()))
    
    # Use first available algorithm for example (default to 'zscore' if none available)
    example_algorithm = sorted(algorithms.keys())[0] if algorithms else "zscore"
    
    # Build algorithm details section
    algorithm_details = []
    for name in sorted(algorithms.keys()):
        info = algorithms[name]
        details = f"- **{name}**: {info.get('description', 'No description available')}"
        if info.get('best_for'):
            details += f" (Best for: {info['best_for']})"
        algorithm_details.append(details)
    algorithm_details_text = "\n".join(algorithm_details) if algorithm_details else "- No algorithms available"

    text = f"""
KB-MCP: Usage Guide

**8 Available Tools:**
1) create_da_config - Create anomaly detection configuration
2) modify_kb_config - Update existing configuration  
3) list_kb_configurations - List all saved configurations
4) describe_mcp_server - This guide
5) elasticsearch_sql - Run ES SQL query to validate queries
6) create_bucket_profile - Create time-context bucket profile
7) list_bucket_profiles - List bucket profiles
8) delete_bucket_profile - Delete bucket profile

**Supported Algorithms:** {supported_algorithms}

{algorithm_details_text}

---

**1) create_da_config**
Create anomaly detection configuration.

Required:
- name: Unique config identifier
- description: What this monitors
- source_index: ES index being monitored (e.g., 'app-logs')
- elasticsearch_sql_query: SQL with $from/$to placeholders
- query_mode: {{"type": "raw"|"aggregated", "timestamp_field": "<column>"}}
- training_from/to: ISO 8601 timestamps for training period
- detection_frequency: CRON (5-field or 6-field with seconds)
- detection_window: Seconds per detection cycle
- detection_start: When detection begins (ISO 8601)
- algorithm: {{"name": "{example_algorithm}", "parameters": [{{"dimension": "<column>", "is_active": true}}]}}

Optional:
- bucket_profile_id: Link to time-context profile
- anomaly_config: {{"user_emails": ["email@example.com"]}}

---

**2) modify_kb_config**
Update existing configuration.

Required: kb_id (MongoDB ObjectId from list_kb_configurations)
Optional: Any field from create_da_config

---

**3) list_kb_configurations**
Returns: name, ID, description, query, training/detection ranges, CRON, algorithm dimensions

---

**5) elasticsearch_sql**
Execute ES SQL query. CRITICAL: List indices first. Never assume index exists.

ES SQL Syntax (differs from standard SQL):
- Identifiers: Double quotes → "field-name", "@timestamp"
- Strings: Single quotes → 'value'
- FROM: Double-quoted index → FROM "my-index-*"
- GROUP BY: Use aliases or positional (1, 2) or repeat expression
- Date truncation: DATE_TRUNC('hour', "@timestamp") AS bucket
- Conditionals: CASE WHEN condition THEN x ELSE y END

---

**6-8) Bucket Profile Tools**
create_bucket_profile: Create time-context profile for context-aware detection
list_bucket_profiles: List all profiles with usage metadata
delete_bucket_profile: Delete profile (cannot delete if referenced by KBs)

---

**Example Configuration:**
```json
{{
  "name": "Web Traffic Monitor",
  "description": "Monitor HTTP status codes",
  "source_index": "kibana_sample_data_logs",
  "elasticsearch_sql_query": "SELECT DATE_TRUNC('hour', \\"@timestamp\\") AS bucket, COUNT(*) AS requests FROM \\".ds-kibana_sample_data_logs-*\\" WHERE \\"@timestamp\\" >= '$from' AND \\"@timestamp\\" < '$to' GROUP BY bucket ORDER BY bucket",
  "query_mode": {{"type": "aggregated", "timestamp_field": "bucket"}},
  "training_from": "2025-10-01T00:00:00Z",
  "training_to": "2025-10-14T23:59:59Z",
  "training_is_active": true,
  "detection_is_active": true,
  "detection_frequency": "*/15 * * * *",
  "detection_window": 3600,
  "detection_start": "2025-10-15T00:00:00Z",
  "algorithm": {{
    "name": "{example_algorithm}",
    "parameters": [{{"dimension": "requests", "is_active": true}}]
  }}
}}
```

"""

    duration_ms = (time.time() - start_time) * 1000
    log_message("Server description generated successfully", "info",
                "describe_mcp_server", "completion", request_id=request_id,
                duration_ms=duration_ms)
    return text
