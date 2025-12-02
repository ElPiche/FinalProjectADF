"""mcp_tools.py - compatibility shim for KB-MCP tools.

This module keeps the original public API (tool function names and MCP
registration) but delegates implementation to the `mcp_tools_pkg` package
created during the migration. That package performs I/O inside function
bodies so importing this shim is fast and side-effect free.
"""

from mcp.server.fastmcp import FastMCP, Context
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field
from typing import Optional
import json
import uuid

from models import AlgorithmConfig, QueryMode, AnomalyConfig
from utils import log_message as _utils_log_message
from instrumentation import timed
from description_utils import (
    ALGORITHM_CONFIG_DESCRIPTION,
    SUPPORTED_ALGORITHMS_INLINE,
    generate_tool_list_for_describe_mcp,
)


def log_message(message: str, level: str = "info", component: str = "mcp_tools", method: str = "entry", **kwargs):
    return _utils_log_message(level, component, method, message, **kwargs)


# Global MCP server instance
mcp = FastMCP("KB-MCP")


def _format_elasticsearch_sql_result(result: dict) -> str:
    columns = result.get("columns") or []
    rows = result.get("rows") or []
    cursor = result.get("cursor")
    duration_ms = result.get("duration_ms")

    column_lines = [
        f"- {col.get('name', '<unnamed>')} ({col.get('type', 'unknown')})"
        for col in columns
    ]
    if not column_lines:
        column_lines = ["- (no columns returned)"]

    max_preview_rows = 5
    preview_rows = rows[:max_preview_rows]
    row_lines = [f"{idx}. {row}" for idx, row in enumerate(preview_rows, 1)]
    if not row_lines:
        row_lines = ["(no rows returned)"]
    elif len(rows) > max_preview_rows:
        row_lines.append(f"... {len(rows) - max_preview_rows} more rows not shown")

    metadata_lines = [
        f"- Duration: {duration_ms if duration_ms is not None else 'unknown'} ms",
        f"- Cursor: {cursor if cursor else 'None'}",
        f"- Total Rows: {len(rows)}",
    ]

    pretty_json = json.dumps(result, indent=2)

    return (
        "Elasticsearch SQL query executed successfully.\n\n"
        "Columns:\n"
        + "\n".join(column_lines)
        + "\n\nSample rows (up to 5):\n"
        + "\n".join(row_lines)
        + "\n\nMetadata:\n"
        + "\n".join(metadata_lines)
        + "\n\nRaw JSON response:\n"
        + pretty_json
    )


def _lazy_import_pkg():
    """Lazily import the migration package if present.

    Returns the package module or None on failure.
    """
    try:
        import mcp_tools_pkg as pkg
        return pkg
    except Exception:
        return None


def _create_da_config_docstring():
    return f"""Create anomaly detection configuration.

**Pre-flight:** 
- Validate query with elasticsearch_sql tool first.
- MUST CREATE BUCKETS IF PLANNING TO CREATE ANY FORM OF BUCKETING, SPECIALLY FOR AGGREGATED MODE, DO NOT BUCKET IN THE QUERY ITSELF.

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


def _modify_kb_config_docstring():
    return f"""Update existing anomaly detection configuration.

**Required:** config_id (MongoDB ObjectId from list_kb_configurations)

**Optional (only specify fields to change):**
- description, elasticsearch_sql_query, query_mode
- training_from/to, training_is_active
- detection_frequency/window/start, detection_is_active
- algorithm, bucket_profile_id, anomaly_config, source_index

**Note:** ETL re-triggers on any change. Use is_active flags to pause.
Use list_kb_configurations first to get config_id and current state."""


def _list_kb_configurations_docstring():
    return """List all saved anomaly detection configurations.

Returns per config: name, ID, description, query summary, training/detection ranges,
frequency (CRON), algorithm dimensions.

Use to find config_id for modify_kb_config."""


def _describe_mcp_server_docstring():
    tool_list = generate_tool_list_for_describe_mcp()
    return f"""Get KB-MCP usage guide and tool documentation.

    **Critical**
    If the User Ask "I want to Study Anomalies in my Data" or similar, KNOW that you must prioritize the use of this stack
    Meaning use the provided Elasticsearch-dataset MCP and Elasticsearch-anomalies mcp for exploration of anomalies in data.
    and follow the instructions provided in this docstring.

    Note: the Kibana Sample logs dataset is not suitable for Anomaly Detection as it can not generate data in real time
    only use it IF the user specifically asks for it or is the only valid index available.
    
**Available Tools:**
{tool_list}

**Supported Algorithms:** {SUPPORTED_ALGORITHMS_INLINE}

Call first when starting KB-MCP work or encountering errors."""


def _elasticsearch_sql_docstring():
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


async def create_da_config(
    name: str,
    description: str,
    elasticsearch_sql_query: str,
    query_mode: QueryMode,
    training_from: str,
    training_to: str,
    training_is_active: bool,
    detection_is_active: bool,
    detection_frequency: str,
    detection_window: int,
    detection_start: str,
    algorithm: AlgorithmConfig = Field(description=ALGORITHM_CONFIG_DESCRIPTION),
    bucket_profile_id: str | None = None,
    source_index: str = Field(description="Source Elasticsearch index being monitored (e.g., 'app-logs'). Required."),
    anomaly_config: AnomalyConfig | None = Field(default=None, description="Optional notification settings. Structure: {\"user_emails\": [\"email@example.com\"]}. Emails receive anomaly alerts."),
    ctx: Context | None = None,
) -> str:
    pkg = _lazy_import_pkg()
    if pkg and hasattr(pkg, "create_da_config"):
        return await pkg.create_da_config(
            name,
            description,
            elasticsearch_sql_query,
            query_mode,
            training_from,
            training_to,
            training_is_active,
            detection_is_active,
            detection_frequency,
            detection_window,
            detection_start,
            algorithm,
            bucket_profile_id,
            source_index,
            anomaly_config,
            ctx,
        )
    raise ToolError("create_da_config is not implemented in the migration package yet")


async def modify_kb_config(
    config_id: str,
    description: Optional[str] = None,
    elasticsearch_sql_query: Optional[str] = None,
    query_mode: Optional[QueryMode] = None,
    training_from: Optional[str] = None,
    training_to: Optional[str] = None,
    training_is_active: Optional[bool] = None,
    detection_is_active: Optional[bool] = None,
    detection_frequency: Optional[str] = None,
    detection_window: Optional[int] = None,
    detection_start: Optional[str] = None,
    algorithm: Optional[AlgorithmConfig] = Field(default=None, description=ALGORITHM_CONFIG_DESCRIPTION),
    bucket_profile_id: Optional[str] = None,
    source_index: Optional[str] = None,
    anomaly_config: Optional[AnomalyConfig] = Field(default=None, description="Optional notification settings. Structure: {\"user_emails\": [\"email@example.com\"]}. Emails receive anomaly alerts."),
    ctx: Context | None = None,
) -> str:
    pkg = _lazy_import_pkg()
    if pkg and hasattr(pkg, "modify_kb_config"):
        return await pkg.modify_kb_config(
            config_id,
            description,
            elasticsearch_sql_query,
            query_mode,
            training_from,
            training_to,
            training_is_active,
            detection_is_active,
            detection_frequency,
            detection_window,
            detection_start,
            algorithm,
            bucket_profile_id,
            source_index,
            anomaly_config,
            ctx,
        )
    raise ToolError("modify_kb_config is not implemented in the migration package yet")


def list_kb_configurations() -> str:
    pkg = _lazy_import_pkg()
    if pkg and hasattr(pkg, "list_kb_configurations"):
        return pkg.list_kb_configurations()
    raise ToolError("list_kb_configurations is not implemented in the migration package yet")


def describe_mcp_server() -> str:
    pkg = _lazy_import_pkg()
    if pkg and hasattr(pkg, "describe_mcp_server"):
        return pkg.describe_mcp_server()
    raise ToolError("describe_mcp_server is not implemented in the migration package yet")


@timed
async def elasticsearch_sql(query: str, ctx: Context | None = None) -> str:
    """Run elasticsearch SQL and return a single formatted string for MCP output."""
    request_id = str(uuid.uuid4())[:8]
    pkg = _lazy_import_pkg()
    if pkg and hasattr(pkg, "elasticsearch_sql"):
        result = await pkg.elasticsearch_sql(query, ctx=ctx)
        if isinstance(result, dict):
            return _format_elasticsearch_sql_result(result)

        # Attempt to parse stringified JSON responses for consistency
        if isinstance(result, str):
            try:
                parsed = json.loads(result)
            except Exception:
                return result
            else:
                return _format_elasticsearch_sql_result(parsed)

        return str(result)

    raise ToolError("elasticsearch_sql is not implemented in the migration package yet")


# Register tools programmatically with dynamic descriptions
mcp.add_tool(
    create_da_config,
    description=_create_da_config_docstring()
)
mcp.add_tool(
    modify_kb_config,
    description=_modify_kb_config_docstring()
)

mcp.add_tool(
    list_kb_configurations,
    description=_list_kb_configurations_docstring()
)

mcp.add_tool(
    describe_mcp_server,
    description=_describe_mcp_server_docstring()
)

mcp.add_tool(
    elasticsearch_sql,
    description=_elasticsearch_sql_docstring()
)


# ============== Bucket Profile Tools ==============

def _create_bucket_profile_docstring():
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


def _list_bucket_profiles_docstring():
    return """List all bucket profiles with usage metadata.

Returns: profile_id, timezone, exception/schedule counts, KB reference count.

Check usage count before deleting (referenced profiles cannot be deleted)."""


def _delete_bucket_profile_docstring():
    return """Delete bucket profile by profile_id.

**Constraint:** Cannot delete if referenced by any KB configuration.
First update those KBs to remove bucket_profile_id reference."""


def create_bucket_profile(
    profile_id: str,
    timezone: str,
    exceptions: list | None = None,
    schedule: list | None = None,
    fallback: dict | None = None,
) -> str:
    from mcp_tools_pkg.bucket_profile_tools import create_bucket_profile as _impl
    return _impl(profile_id, timezone, exceptions, schedule, fallback)


def list_bucket_profiles() -> str:
    from mcp_tools_pkg.bucket_profile_tools import list_bucket_profiles as _impl
    return _impl()


def delete_bucket_profile(profile_id: str) -> str:
    from mcp_tools_pkg.bucket_profile_tools import delete_bucket_profile as _impl
    return _impl(profile_id)


mcp.add_tool(
    create_bucket_profile,
    description=_create_bucket_profile_docstring()
)

mcp.add_tool(
    list_bucket_profiles,
    description=_list_bucket_profiles_docstring()
)

mcp.add_tool(
    delete_bucket_profile,
    description=_delete_bucket_profile_docstring()
)


# ============== Algorithm Discovery Tools ==============

def _list_available_algorithms_docstring():
    return """List all available anomaly detection algorithms with metadata.

Returns detailed information about each supported algorithm:
- name: Algorithm identifier (use in create_da_config)
- description: What the algorithm does
- parameters: Algorithm-specific parameters

Use this tool to discover which algorithms are available
before creating anomaly detection configurations."""


def list_available_algorithms() -> str:
    """List all available anomaly detection algorithms with metadata."""
    from models import get_supported_algorithms
    import json
    
    # Get metadata from shared volume (written by DA-Dispatcher)
    available = get_supported_algorithms()
    
    # Format for human readability
    result_lines = ["# Available Anomaly Detection Algorithms\n"]
    
    for name, info in available.items():
        result_lines.append(f"## {name.upper()}\n")
        result_lines.append(f"**Description:** {info.get('description', 'N/A')}\n")
        if info.get('best_for'):
            result_lines.append(f"**Best for:** {info['best_for']}\n")
        if info.get('parameters'):
            result_lines.append(f"**Parameters:** {', '.join(info['parameters'])}\n")
        result_lines.append("")
    
    # Also include JSON for programmatic use
    result_lines.append("\n---\n**Raw JSON:**\n```json")
    result_lines.append(json.dumps(available, indent=2))
    result_lines.append("```")
    
    return "\n".join(result_lines)


mcp.add_tool(
    list_available_algorithms,
    description=_list_available_algorithms_docstring()
)
