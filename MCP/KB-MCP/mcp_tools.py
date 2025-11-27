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
import uuid
import time
import json

from models import AlgorithmConfig, QueryMode
from utils import log_message as _utils_log_message, stderr_print
from instrumentation import timed
from description_utils import ALGORITHM_CONFIG_DESCRIPTION, AVAILABLE_ALGORITHMS_DESCRIPTION, SUPPORTED_ALGORITHMS, SUPPORTED_ALGORITHMS_INLINE, SUPPORTED_ALGORITHMS_QUOTED, generate_tool_list_for_describe_mcp, get_tool_count, generate_kb_config_template_description, generate_kb_config_fields_description, generate_kb_config_description, generate_kb_config_example, generate_kb_config_description, generate_kb_config_example, generate_algorithm_config_example


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


def ping_elasticsearch_debug():
    """Fallback ping helper that prefers package implementation or returns False."""
    pkg = _lazy_import_pkg()
    if pkg and hasattr(pkg, "ping_elasticsearch_debug"):
        try:
            return pkg.ping_elasticsearch_debug()
        except Exception:
            return False
    log_message("ping_elasticsearch_debug not implemented in migration package", "warning", "ping_elasticsearch_debug", "fallback")
    return False

def etl_docstring():
    return"""
    This configuration will be consumed by an ETL process that runs the training configuration to build training series data, and then applies the detection configuration on new incoming data to identify anomalies based on the trained models.

    CRITICAL: ETL will run on every modification of this configuration, so anytime you change this configuration, the ETL process will be triggered. (e.g., if you change the detection query, the ETL will reprocess data using the new query).
    If you need to make changes without triggering ETL, just set the training_is_active and detection_is_active flags to False.
    If you need to run ETL without changing the configuration, you use the `change_flag` to make a lightweight update.
    """

def _create_da_config_docstring():
    template_description = generate_kb_config_description()
    fields_description = generate_kb_config_fields_description()

    return f"""
    Create a new anomaly-detection configuration for monitoring data streams.

        This tool stores a complete anomaly detection configuration in MongoDB, including a unified `elasticsearch_sql_query`, query mode metadata, scheduling parameters, optional bucket profile linkage, and algorithm specifications. Dispatcher and extractor services will use the saved configuration to train models and perform detections in real time.

    {etl_docstring()}

    **Configuration Structure Overview** (automatically generated from KBConfig Pydantic model):
    {template_description}

    BEFORE USING THIS TOOL:
        **Validate your unified elasticsearch_sql_query with the `elasticsearch_sql` tool before calling this function. Ensure the query returns the timestamp field declared in `query_mode.timestamp_field`.**
        **Ensure the indices referenced in your query exist and are accessible in the Elasticsearch cluster.**
        **Confirm the algorithm dimensions map to actual column names returned by the unified query. Use `list_available_algorithms` plus `elasticsearch_sql` previews for verification.**
        **If you plan to link a bucket profile, create it first so you can reference the correct `bucket_profile_id`.**
    For more info, use the `describe_mcp_server` tool.

    {fields_description}

    **Algorithm Configuration Structure**:
    {ALGORITHM_CONFIG_DESCRIPTION}

        **Example AlgorithmConfig Structure** (dynamically generated from actual class):
        ```json
        {generate_algorithm_config_example()}
        ```

        Pass the algorithm object exactly as it should be stored (single algorithm entry with metadata and optional `is_active` flags). No legacy arrays are required—KBConfig stores a single `algorithm` object.

    Returns:
    - Success: "SUCCESS: Configuration saved to MongoDB! Document ID: <id> Configuration saved successfully."
    - Error: Validation error message describing what failed

    Common Validation Errors:
    - Invalid CRON expression in detection_frequency
    - SQL query syntax errors or non-existent indices
    - Dimension names not found in query output columns
    - Missing required fields

    **Complete Configuration Example** (dynamically generated from KBConfig model):
    ```json
    {generate_kb_config_example()}
    ```

    Tips:
    - Use elasticsearch_sql tool first to validate your queries and see available columns
    - Ensure dimension names exactly match column names from your query output
    - Training data should be historical data for model training
    - Detection query should be for real-time or recent data
    - The configuration structure automatically reflects any changes made to the KBConfig Pydantic model
    """


def _modify_kb_config_docstring():
    template_description = generate_kb_config_description()
    fields_description = generate_kb_config_fields_description()

    return f"""
    Update an existing anomaly-detection configuration.

    Provide the `config_id` plus whichever fields you want to update. KB-MCP persists the changes atomically, leaving unspecified fields untouched. The tool now works with the unified query schema (single `elasticsearch_sql_query`, `query_mode`, singular `algorithm`, optional `bucket_profile_id`).

    {etl_docstring()}
    
    **Configuration Structure Overview** (automatically generated from KBConfigTemplate.json):
    {template_description}

    Required Input:
    - config_id (string): MongoDB ID of the configuration to update (e.g., "507f1f77bcf86cd799439011").

    Optional Inputs (all map directly to KBConfig fields):
    - description, elasticsearch_sql_query, query_mode
    - training_from, training_to, training_is_active
    - detection_start, detection_frequency, detection_window, detection_is_active
    - algorithm (singular AlgorithmConfig)
    - bucket_profile_id

    {fields_description}

    **Algorithm Configuration Structure**:
    {ALGORITHM_CONFIG_DESCRIPTION}

    Returns:
    - Success: Confirmation message indicating the update succeeded.
    - Error: Validation message describing what failed (missing config, invalid CRON, SQL validation failure, etc.).

    Common Validation Errors:
    - config_id not found in database
    - Invalid CRON expression if detection_frequency is updated
    - SQL query validation failures if queries are updated
    - Dimension names not matching query output if algorithms are updated

    Example Usage:
    Update description and detection frequency:
    {{
      "config_id": "507f1f77bcf86cd799439011",
      "description": "Updated monitoring for web traffic anomalies",
      "detection_frequency": "*/30 * * * *"
    }}

    Update algorithm dimensions and query metadata:
    {{
      "config_id": "507f1f77bcf86cd799439011",
      "algorithm": {generate_algorithm_config_example()},
      "query_mode": {{"type": "aggregated", "timestamp_field": "event_time"}}
    }}

    Tips:
    - Use list_kb_configurations first to inspect the current state.
    - Only specify fields you intend to change.
    - Changing `query_mode` re-validates the stored CRON for compliance with per-mode minimums.
    - Ensure any referenced bucket_profile_id exists before updating.
    """


def _list_kb_configurations_docstring():
    return f"""
    List all saved anomaly-detection configurations.

    This tool retrieves and displays all stored configurations from the knowledge base in a human-readable format. Each configuration shows its name, unique ID, scheduling information, and configured algorithms.

    Inputs: None

    Returns:
    A formatted list showing:
    - Configuration name and ID
    - Description
    - Training query summary
    - Detection query summary
    - Time ranges (training_from/to, detection_start)
    - Detection frequency (CRON expression)
    - Algorithm details (name and monitored dimensions)

    Example Output:
    ## Configuration: Web Traffic Monitor
    ID: 507f1f77bcf86cd799439011
    Description: Monitor HTTP response codes
    Training: SELECT ... FROM logs WHERE @timestamp >= $from AND @timestamp < $to
    Detection: FROM logs | STATS ... BY @timestamp
    Training Range: 2025-10-01T00:00:00Z to 2025-10-09T23:59:59Z
    Detection Start: 2025-10-10T00:00:00Z
    Frequency: */15 * * * *
    Algorithms:
      - zscore: status_code_200_counter, status_code_5xx_counter

    Tips:
    - Use this tool to find configuration IDs for modify_kb_config
    - Review algorithm dimensions to ensure they match your data
    - Check scheduling to understand when detections run
    """


def _describe_mcp_server_docstring():
    tool_count = get_tool_count()
    tool_list = generate_tool_list_for_describe_mcp()

    return f"""
    Get comprehensive usage guide and examples for all KB-MCP tools.

    This tool provides detailed documentation for using the KB-MCP (Knowledge Base - Model Context Protocol) server. It includes descriptions of all {tool_count} available tools, their inputs, outputs, common usage patterns, and copy-pasteable examples.

    Inputs: None

    Returns:
    A comprehensive guide containing:
    - Purpose and overview of KB-MCP
    - Detailed description of each tool with:
      - Required and optional inputs
      - Return value formats
      - Common validation errors
      - Example usage with real data
    - Best practices and tips
    - JSON examples for complex inputs

    Example Output Structure:
    KB-MCP: How to use the tools

    Purpose
    [Overview text]

    Tools
    {tool_list}
    [Each tool with detailed description, inputs, outputs, and examples]

    Common notes for callers
    [General tips and best practices]

    Plain labelled example
    [Copy-pasteable example]

    JSON example
    [JSON format example]

    Tips:
    - Read this first when starting to use KB-MCP tools
    - Use the examples as templates for your own configurations
    - Refer back to this guide when encountering validation errors
    """


def _list_available_algorithms_docstring():
    return f"""
    List all available anomaly detection algorithms with configuration details.

    This tool provides information about all implemented algorithms that can be used in anomaly detection configurations. It shows algorithm names, descriptions, required parameters, and example configurations.

    Inputs: None

    Returns:
    A formatted list containing:
    - Algorithm name and description
    - Required parameter names and types
    - Example configuration objects
    - Current implementation status

    {AVAILABLE_ALGORITHMS_DESCRIPTION}
    """


def _ping_elasticsearch_docstring():
    return f"""
    Test connectivity to the Elasticsearch cluster.

    This tool checks if the KB-MCP server can successfully connect to the configured Elasticsearch hosts. It's useful for diagnosing connectivity issues before running queries or creating configurations.

    Inputs: None

    Returns:
    A JSON object with:
    - ping_success (boolean): true if connection successful, false otherwise
    - duration_ms (float): Time taken for the ping in milliseconds
    - error (string, optional): Error message if ping failed

    Example Success Response:
    {{"ping_success": true, "duration_ms": 45.2}}

    Example Failure Response:
    {{"ping_success": false, "error": "Connection timeout", "duration_ms": 30000.0}}

    Common Issues:
    - Network connectivity problems
    - Elasticsearch cluster down
    - Authentication failures
    - Incorrect host configuration

    Tips:
    - Run this tool first if you're having issues with SQL queries
    - Use the duration_ms to monitor Elasticsearch response times
    - Check error messages for specific connectivity problems
    """


def _elasticsearch_sql_docstring():
    return f"""
    Execute an Elasticsearch SQL query and return results.

    This tool runs SQL queries against Elasticsearch data and returns the column structure and sample rows. It's essential for validating queries before using them in anomaly detection configurations.

    Important: always query the available indices BEFORE attempting a query, this will increase your chances of success.
    YOU WILL NOT ASSUME AN INDEX EXISTS
for more info, use the `describe_mcp_server` tool.

    Required Input:
    - query (string): The Elasticsearch SQL query to execute

    Returns:
    A JSON object with:
    - columns: Array of column objects with 'name' and 'type' fields
    - rows: Array of data rows (limited to prevent large responses)

    Example Query (SQL):
    "SELECT @timestamp, response, COUNT(*) as request_count FROM \".ds-kibana_sample_data_logs-*\" WHERE @timestamp >= '2025-10-01T00:00:00Z' GROUP BY @timestamp, response LIMIT 10"

    Example Response:
    {{
      "columns": [
        {{"name": "@timestamp", "type": "datetime"}},
        {{"name": "response", "type": "keyword"}},
        {{"name": "request_count", "type": "long"}}
      ],
      "rows": [
        ["2025-10-01T00:00:00Z", "200", 150],
        ["2025-10-01T00:01:00Z", "404", 5]
      ]
    }}

    Common Query Patterns:
    - SELECT ... FROM index WHERE conditions GROUP BY columns
    - Use LIMIT to prevent large result sets
    - Use $from and $to placeholders for time ranges in configurations

    Validation Tips:
    - Check column names match what you'll use in algorithms
    - Ensure numeric columns for zscore algorithm dimensions
    - Test with LIMIT 0 first to validate syntax without data
    - Use this tool before create_da_config to verify your queries work

    Error Handling:
    - Syntax errors return descriptive error messages
    - Index not found errors specify which index failed
    - Permission errors indicate authentication issues
    """


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
    source_index: str | None = None,
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


def list_available_algorithms() -> str:
    pkg = _lazy_import_pkg()
    if pkg and hasattr(pkg, "list_available_algorithms"):
        return pkg.list_available_algorithms()
    raise ToolError("list_available_algorithms is not implemented in the migration package yet")


def ping_elasticsearch() -> str:
    request_id = str(uuid.uuid4())[:8]
    start = time.time()
    try:
        pkg = _lazy_import_pkg()
        if pkg and hasattr(pkg, "ping_elasticsearch"):
            success = pkg.ping_elasticsearch()
        else:
            success = ping_elasticsearch_debug()
        duration_ms = (time.time() - start) * 1000
        log_message(f"ping_elasticsearch tool completed: {success}", "info",
                    "ping_elasticsearch", "completion", request_id=request_id,
                    duration_ms=duration_ms, extra_data={"ping_success": success})
        stderr_print(f"[KB-MCP] ping_elasticsearch result: {success}")
        return json.dumps({"ping_success": success, "duration_ms": duration_ms})
    except Exception as e:
        duration_ms = (time.time() - start) * 1000
        log_message(f"ping_elasticsearch tool error: {str(e)}", "error",
                    "ping_elasticsearch", "error", request_id=request_id,
                    duration_ms=duration_ms, extra_data={"error_type": type(e).__name__})
        stderr_print(f"[KB-MCP] ping_elasticsearch error: {e}")
        return json.dumps({"ping_success": False, "error": str(e), "duration_ms": duration_ms})


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
    list_available_algorithms,
    description=_list_available_algorithms_docstring()
)

mcp.add_tool(
    ping_elasticsearch,
    description=_ping_elasticsearch_docstring()
)

mcp.add_tool(
    elasticsearch_sql,
    description=_elasticsearch_sql_docstring()
)


# ============== Bucket Profile Tools ==============

def _create_bucket_profile_docstring():
    return """
    Create a reusable bucket profile for time-context definitions.

    Bucket profiles define how timestamps are mapped to semantic bucket keys for
    context-aware anomaly detection. This enables different baselines for different
    time periods (e.g., business hours vs. weekends, holidays vs. normal days).

    Required Inputs:
    - profile_id (string): Unique identifier (e.g., "business_hours_v1")
    - timezone (string): IANA timezone (e.g., "America/New_York")

    Optional Inputs:
    - exceptions: List of exception rules for specific dates (holidays)
    - schedule: List of schedule rules for recurring patterns
    - fallback: Configuration for when no rule matches

    Exception Rule Structure:
    {
        "bucket_base_key": "holiday_xmas",
        "rule": {"month": 12, "day": 25, "year": null},
        "granularity": "block"  // "block" or "hourly"
    }

    Schedule Rule Structure:
    {
        "bucket_base_key": "workday",
        "days": [1,2,3,4,5],  // 1=Monday, 7=Sunday
        "time_range": {"start": "09:00", "end": "17:00"},
        "granularity": "hourly",
        "months": null  // optional: [1,2,12] for winter
    }

    Fallback Structure:
    {"bucket_base_key": "off_hours", "granularity": "hourly"}

    Priority Order:
    1. Exceptions (holidays) - checked first
    2. Schedule rules - in list order, first match wins
    3. Fallback - always matches

    Example:
    {
        "profile_id": "business_hours_v1",
        "timezone": "America/New_York",
        "exceptions": [
            {"bucket_base_key": "holiday_xmas", "rule": {"month": 12, "day": 25}, "granularity": "block"}
        ],
        "schedule": [
            {"bucket_base_key": "workday", "days": [1,2,3,4,5], "time_range": {"start": "09:00", "end": "17:00"}, "granularity": "hourly"}
        ],
        "fallback": {"bucket_base_key": "off_hours", "granularity": "hourly"}
    }

    Returns:
    Success message with profile ID.

    Common Errors:
    - Profile ID already exists
    - Invalid timezone
    - Invalid time format (must be HH:MM)
    - Invalid day values (must be 1-7)
    """


def _list_bucket_profiles_docstring():
    return """
    List all bucket profiles with usage metadata.

    Returns a formatted list of all saved bucket profiles, including:
    - Profile ID and timezone
    - Number of exception and schedule rules
    - Fallback configuration
    - Number of KB configurations using this profile

    Inputs: None

    Example Output:
    Bucket Profiles:
      - business_hours_v1 (TZ: America/New_York, exceptions: 2, schedules: 3, used by: 5 KB(s))
      - weekend_only (TZ: UTC, exceptions: 0, schedules: 2, used by: 1 KB(s))

    Tips:
    - Use this to find profile IDs for create_da_config or modify_kb_config
    - Check usage count before attempting to delete a profile
    """


def _delete_bucket_profile_docstring():
    return """
    Delete a bucket profile if not referenced by any KB.

    Required Input:
    - profile_id (string): The ID of the profile to delete

    Returns:
    Success message if deleted.

    Referential Integrity:
    Bucket profiles cannot be deleted if any KB configuration references them.
    You must first update those KBs to remove the bucket_profile_id reference.

    Common Errors:
    - Profile not found
    - Profile is referenced by KB configurations (list of KBs provided in error)
    """


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
