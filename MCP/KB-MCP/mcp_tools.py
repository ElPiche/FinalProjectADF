"""mcp_tools.py - compatibility shim for KB-MCP tools.

This module keeps the original public API (tool function names and MCP
registration) but delegates implementation to the `mcp_tools_pkg` package
created during the migration. That package performs I/O inside function
bodies so importing this shim is fast and side-effect free.
"""

from mcp.server.fastmcp import FastMCP, Context
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field
from typing import List
import uuid
import time
import json

from models import AlgorithmConfig
from utils import log_message as _utils_log_message
from instrumentation import timed
from description_utils import ALGORITHM_CONFIG_DESCRIPTION, AVAILABLE_ALGORITHMS_DESCRIPTION, SUPPORTED_ALGORITHMS, SUPPORTED_ALGORITHMS_INLINE, SUPPORTED_ALGORITHMS_QUOTED, generate_tool_list_for_describe_mcp, get_tool_count, generate_kb_config_template_description, generate_kb_config_fields_description, generate_kb_config_description, generate_kb_config_example, generate_kb_config_description, generate_kb_config_example, generate_algorithm_config_example


def log_message(message: str, level: str = "info", component: str = "mcp_tools", method: str = "entry", **kwargs):
    return _utils_log_message(level, component, method, message, **kwargs)


# Global MCP server instance
mcp = FastMCP("KB-MCP")


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

    This tool creates and stores a complete anomaly detection configuration in MongoDB, including training and detection queries, scheduling parameters, and algorithm specifications. The configuration will be used by the anomaly detection engine to train models and detect anomalies in real-time.

    {etl_docstring()}

    **Configuration Structure Overview** (automatically generated from KBConfig Pydantic model):
    {template_description}

    BEFORE USING THIS TOOL:
    **It is Required to first validate your training_query and detection_query using the `elasticsearch_sql` tool. This ensures that your queries are syntactically correct and return the expected columns, which is crucial for the algorithms to function properly.**
    **also ensure the indices referenced in your queries exist and are accessible in the elasticsearch cluster.**
    **and lastly ensure that the algorithms you plan to use are compatible with the output columns of your queries by using the `list_available_algorithms` tool**
    **and ensure that the dimension names specified in the algorithm configurations exactly match the column names returned by your queries.**
    For more info, use the `describe_mcp_server` tool.

    {fields_description}

    **Algorithm Configuration Structure**:
    {ALGORITHM_CONFIG_DESCRIPTION}

    **Example AlgorithmConfig Structure** (dynamically generated from actual class):
    ```json
    {{
      "alg_name": "zscore",
      "alg_parameters": [
        {{
          "dimension": "response_time"
        }},
        {{
          "dimension": "error_count"
        }}
      ]
    }}
    ```

    **Complete algorithms Array Example**:
    ```json
    [
      {{
        "alg_name": "zscore",
        "alg_parameters": [
          {{
            "dimension": "response_time"
          }},
          {{
            "dimension": "error_count"
          }}
        ]
      }}
    ]
    ```

    The algorithms parameter accepts a list of algorithm configuration objects in the exact format that will be stored in the database, following the KBConfigTemplate.json specification. No complex parsing or legacy format conversion is performed.

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

    This tool allows you to modify any aspect of an existing configuration by providing its config_id and the fields you want to update. Only the specified fields will be changed; others remain unchanged.

    {etl_docstring()}
    
    **Configuration Structure Overview** (automatically generated from KBConfigTemplate.json):
    {template_description}

    Required Input:
    - config_id (string): The unique identifier of the configuration to update (e.g., "507f1f77bcf86cd799439011")

    {fields_description}

    **Algorithm Configuration Structure**:
    {ALGORITHM_CONFIG_DESCRIPTION}

    Returns:
    - Success: Confirmation message indicating what was updated
    - Error: Validation error message if the update failed

    Common Validation Errors:
    - config_id not found in database
    - Invalid CRON expression if detection_frequency is updated
    - SQL query validation failures if queries are updated
    - Dimension names not matching query output if algorithms are updated

    Example Usage:
    To update just the description and detection frequency:
    {{
      "config_id": "507f1f77bcf86cd799439011",
      "description": "Updated monitoring for web traffic anomalies",
      "detection_frequency": "*/30 * * * *"
    }}

        To change the algorithms:
        {{
            "config_id": "507f1f77bcf86cd799439011",
            "algorithms": [
                {{
                    "alg_name": "zscore",
                    "alg_parameters": [
                        {{
                            "dimension": "new_metric_column"
                        }}
                    ]
                }}
            ]
        }}

    Tips:
    - Use list_kb_configurations first to see current configuration details
    - Only include fields you want to change
    - Changes take effect immediately for future detection runs
    - The configuration structure automatically reflects any changes made to KBConfigTemplate.json
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
    training_query: str,
    detection_query: str,
    training_from: str,
    training_to: str,
    training_is_active: bool,
    detection_is_active: bool,
    training_window: int,
    detection_window: int,
    detection_frequency: str,
    detection_start: str,
    algorithms: List[AlgorithmConfig] = Field(description=ALGORITHM_CONFIG_DESCRIPTION),
    ctx: Context | None = None
) -> str:
    pkg = _lazy_import_pkg()
    if pkg and hasattr(pkg, "create_da_config"):
        return await pkg.create_da_config(name, 
                                          description, 
                                          training_query, 
                                          detection_query,
                                          training_from, 
                                          training_to, 
                                          training_is_active, 
                                          detection_is_active,
                                          training_window, 
                                          detection_window, 
                                          detection_frequency,
                                          detection_start, 
                                          algorithms,
                                          ctx)
    raise ToolError("create_da_config is not implemented in the migration package yet")


async def modify_kb_config(
    config_id: str,
    description: str,
    training_query: str,
    detection_query: str,
    training_from: str,
    training_to: str,
    training_is_active: bool,
    detection_is_active: bool,
    training_window: int,
    detection_window: int,
    detection_frequency: str,
    detection_start: str,
    algorithms: List[AlgorithmConfig] = Field(description=ALGORITHM_CONFIG_DESCRIPTION),
    ctx: Context | None = None
) -> str:
    pkg = _lazy_import_pkg()
    if pkg and hasattr(pkg, "modify_kb_config"):
        return await pkg.modify_kb_config(config_id, 
                                          description, 
                                          training_query, 
                                          detection_query,
                                          training_from, 
                                          training_to, 
                                          training_is_active,
                                          detection_is_active, 
                                          training_window, 
                                          detection_window,
                                          detection_frequency, 
                                          detection_start, 
                                          algorithms,
                                          ctx)
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
        print(f"[KB-MCP] ping_elasticsearch result: {success}")
        return json.dumps({"ping_success": success, "duration_ms": duration_ms})
    except Exception as e:
        duration_ms = (time.time() - start) * 1000
        log_message(f"ping_elasticsearch tool error: {str(e)}", "error",
                    "ping_elasticsearch", "error", request_id=request_id,
                    duration_ms=duration_ms, extra_data={"error_type": type(e).__name__})
        print(f"[KB-MCP] ping_elasticsearch error: {e}")
        return json.dumps({"ping_success": False, "error": str(e), "duration_ms": duration_ms})


@timed
def elasticsearch_sql(query: str) -> str:
    request_id = str(uuid.uuid4())[:8]
    pkg = _lazy_import_pkg()
    if pkg and hasattr(pkg, "elasticsearch_sql"):
        return pkg.elasticsearch_sql(query)
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

