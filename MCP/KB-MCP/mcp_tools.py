"""mcp_tools.py - compatibility shim for KB-MCP tools.

This module keeps the original public API (tool function names and MCP
registration) but delegates implementation to the `mcp_tools_pkg` package
created during the migration. That package performs I/O inside function
bodies so importing this shim is fast and side-effect free.
"""

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field
from typing import List
import uuid
import time
import json

from models import AlgorithmConfig
from utils import log_message as _utils_log_message
from instrumentation import timed


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


@mcp.tool()
def create_da_config(
    name: str = Field(description="Configuration name"),
    description: str = Field(description="Human-readable description"),
    training_query: str = Field(description="SQL query for training data"),
    detection_query: str = Field(description="SQL query for detection"),
    training_from: str = Field(description="Training start timestamp (ISO format)"),
    training_to: str = Field(description="Training end timestamp (ISO format)"),
    detection_frequency: str = Field(description="Detection frequency (CRON format)"),
    detection_start: str = Field(description="Detection start timestamp (ISO format)"),
    algorithms: List[AlgorithmConfig] = Field(description="List of algorithm configurations")
) -> str:
    """
    Create a new anomaly-detection configuration for monitoring data streams.

    This tool creates and stores a complete anomaly detection configuration in MongoDB, including training and detection queries, scheduling parameters, and algorithm specifications. The configuration will be used by the anomaly detection engine to train models and detect anomalies in real-time.

    BEFORE USING THIS TOOL:
    **It is Required to first validate your training_query and detection_query using the `elasticsearch_sql` tool. This ensures that your queries are syntactically correct and return the expected columns, which is crucial for the algorithms to function properly.**
    **also ensure the indices referenced in your queries exist and are accessible in the elasticsearch cluster.**
    **and lastly ensure that the algorithms you plan to use are compatible with the output columns of your queries by using the `list_available_algorithms` tool**
    **and ensure that the dimension names specified in the algorithm configurations exactly match the column names returned by your queries.**
    For more info, use the `describe_mcp_server` tool.

    Required Inputs:
    - name (string): A unique, descriptive name for the configuration (e.g., "Web Traffic Anomaly Detection")
    - description (string): Human-readable description of what this configuration monitors (e.g., "Monitor HTTP response codes and detect unusual patterns")
    - training_query (string): Elasticsearch SQL query for training data. Must return the columns you want to monitor. Use placeholders like $from and $to for time ranges.
    - detection_query (string): Elasticsearch SQL query for detection runs. Should match the structure of training_query but for real-time data.
    - training_from (string): ISO 8601 timestamp for training data start (e.g., "2025-10-01T00:00:00Z")
    - training_to (string): ISO 8601 timestamp for training data end (e.g., "2025-10-09T23:59:59Z")
    - detection_frequency (string): CRON expression for how often to run detection (e.g., "*/15 * * * *" for every 15 minutes)
    - detection_start (string): ISO 8601 timestamp when detection should begin (e.g., "2025-10-10T00:00:00Z")
    - algorithms (array): List of algorithm configurations. Currently supports 'zscore' algorithm.

    Algorithm Format:
    Each algorithm object must have:
    - alg_name: "zscore" (currently the only supported algorithm)
    - alg_parameters: Array of objects with 'dimension' field naming columns from your query output

    The algorithms parameter accepts a list of algorithm configuration objects in the exact format that will be stored in the database, following the KBConfigTemplate.json specification. No complex parsing or legacy format conversion is performed.

    Returns:
    - Success: "SUCCESS: Configuration saved to MongoDB! Document ID: <id> Configuration saved successfully."
    - Error: Validation error message describing what failed

    Common Validation Errors:
    - Invalid CRON expression in detection_frequency
    - SQL query syntax errors or non-existent indices
    - Dimension names not found in query output columns
    - Missing required fields

    Example Usage:
    {
      "name": "Geographic Traffic Pattern Analysis",
      "description": "Monitor hourly status code counts and detect spikes in 5xx errors",
      "training_query": "SELECT DATE_TRUNC('HOUR', \"@timestamp\") AS es_timestamp, SUM(CASE WHEN response = '200' THEN 1 ELSE 0 END) AS status_code_200_counter, SUM(CASE WHEN CAST(response AS INTEGER) >= 500 AND CAST(response AS INTEGER) < 600 THEN 1 ELSE 0 END) AS status_code_5xx_counter FROM \".ds-kibana_sample_data_logs-*\" WHERE \"@timestamp\" >= '$from' AND \"@timestamp\" < '$to' GROUP BY es_timestamp ORDER BY es_timestamp",
      "detection_query": "SELECT DATE_TRUNC('HOUR', \"@timestamp\") AS es_timestamp, SUM(CASE WHEN response = '200' THEN 1 ELSE 0 END) AS status_code_200_counter, SUM(CASE WHEN CAST(response AS INTEGER) >= 500 AND CAST(response AS INTEGER) < 600 THEN 1 ELSE 0 END) AS status_code_5xx_counter FROM \".ds-kibana_sample_data_logs-*\" WHERE \"@timestamp\" >= '$from' AND \"@timestamp\" < '$to' GROUP BY es_timestamp ORDER BY es_timestamp",
      "training_from": "2025-10-01T00:00:00Z",
      "training_to": "2025-10-09T23:59:59Z",
      "detection_frequency": "*/15 * * * *",
      "detection_start": "2025-10-10T00:00:00Z",
      "algorithms": [
        {
          "alg_name": "zscore",
          "alg_parameters": [
            {"dimension": "status_code_200_counter"},
            {"dimension": "status_code_5xx_counter"}
          ]
        }
      ]
    }

    Tips:
    - Use elasticsearch_sql tool first to validate your queries and see available columns
    - Ensure dimension names exactly match column names from your query output
    - Training data should be historical data for model training
    - Detection query should be for real-time or recent data
    """
    pkg = _lazy_import_pkg()
    if pkg and hasattr(pkg, "create_da_config"):
        return pkg.create_da_config(name, description, training_query, detection_query,
                                     training_from, training_to, detection_frequency,
                                     detection_start, algorithms)
    raise ToolError("create_da_config is not implemented in the migration package yet")


@mcp.tool()
def modify_kb_config(
    config_id: str,
    description: str = Field(description="Human-readable description", default=None),
    training_query: str = Field(description="SQL query for training data", default=None),
    detection_query: str = Field(description="SQL query for detection", default=None),
    training_from: str = Field(description="Training start timestamp (ISO format)", default=None),
    training_to: str = Field(description="Training end timestamp (ISO format)", default=None),
    detection_frequency: str = Field(description="Detection frequency (CRON format)", default=None),
    detection_start: str = Field(description="Detection start timestamp (ISO format)", default=None),
    algorithms: List[AlgorithmConfig] = Field(description="List of algorithm configurations", default=None)
) -> str:
    """
    Update an existing anomaly-detection configuration.

    This tool allows you to modify any aspect of an existing configuration by providing its config_id and the fields you want to update. Only the specified fields will be changed; others remain unchanged.

    Required Input:
    - config_id (string): The unique identifier of the configuration to update (e.g., "507f1f77bcf86cd799439011")

    Optional Inputs (provide only what you want to change):
    - description (string): Update the human-readable description
    - training_query (string): Update the Elasticsearch SQL query for training data
    - detection_query (string): Update the Elasticsearch SQL query for detection runs
    - training_from (string): Update the training start timestamp (ISO 8601 format)
    - training_to (string): Update the training end timestamp (ISO 8601 format)
    - detection_frequency (string): Update the CRON expression for detection frequency
    - detection_start (string): Update the detection start timestamp (ISO 8601 format)
    - algorithms (dict): Update the algorithm configurations

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
    {
      "config_id": "507f1f77bcf86cd799439011",
      "description": "Updated monitoring for web traffic anomalies",
      "detection_frequency": "*/30 * * * *"
    }

    To change the algorithms:
    {
      "config_id": "507f1f77bcf86cd799439011",
      "algorithms": [
        {
          "alg_name": "zscore",
          "alg_parameters": [
            {"dimension": "new_metric_column"}
          ]
        }
      ]
    }

    Tips:
    - Use list_kb_configurations first to see current configuration details
    - Only include fields you want to change
    - Changes take effect immediately for future detection runs
    """
    pkg = _lazy_import_pkg()
    if pkg and hasattr(pkg, "modify_kb_config"):
        return pkg.modify_kb_config(config_id, description, training_query, detection_query,
                                     training_from, training_to, detection_frequency,
                                     detection_start, algorithms)
    raise ToolError("modify_kb_config is not implemented in the migration package yet")


@mcp.tool()
def list_kb_configurations() -> str:
    """
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
    pkg = _lazy_import_pkg()
    if pkg and hasattr(pkg, "list_kb_configurations"):
        return pkg.list_kb_configurations()
    raise ToolError("list_kb_configurations is not implemented in the migration package yet")


@mcp.tool()
def describe_mcp_server() -> str:
    """
    Get comprehensive usage guide and examples for all KB-MCP tools.

    This tool provides detailed documentation for using the KB-MCP (Knowledge Base - Model Context Protocol) server. It includes descriptions of all available tools, their inputs, outputs, common usage patterns, and copy-pasteable examples.

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
    1) create_da_config
    - Inputs: [detailed list]
    - Return: [description]
    [Examples and tips]

    2) modify_kb_config
    [Similar detailed format]

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
    pkg = _lazy_import_pkg()
    if pkg and hasattr(pkg, "describe_mcp_server"):
        return pkg.describe_mcp_server()
    raise ToolError("describe_mcp_server is not implemented in the migration package yet")


@mcp.tool()
def list_available_algorithms() -> str:
    """
    List all available anomaly detection algorithms with configuration details.

    This tool provides information about all implemented algorithms that can be used in anomaly detection configurations. It shows algorithm names, descriptions, required parameters, and example configurations.

    Inputs: None

    Returns:
    A formatted list containing:
    - Algorithm name and description
    - Required parameter names and types
    - Example configuration objects
    - Current implementation status

    Currently Available Algorithms:

    1) zscore
    - Description: Z-score based anomaly detection using standard deviation thresholds
    - Parameters:
      - dimensions: Array of column names from your query output to monitor
    - Example:
      {
        "alg_name": "zscore",
        "alg_parameters": [
          {"dimension": "response_time"},
          {"dimension": "error_count"}
        ]
      }

    Future Algorithms (planned):
    - kmeans: Clustering-based anomaly detection

    Example Output:
    # Available Anomaly Detection Algorithms

    ## zscore
    **Description:** Detects anomalies based on standard deviation from the mean. Values that fall outside a threshold (typically 3 standard deviations) are flagged as anomalies.

    **Parameters:**
    - `dimensions`: List of numeric columns to monitor for anomalies

    **Example Configuration:**
    ```json
    {
      "alg_name": "zscore",
      "alg_parameters": [
        {"dimension": "cpu_usage"},
        {"dimension": "memory_usage"}
      ]
    }
    ```

    Tips:
    - Use this tool before creating configurations to understand available algorithms
    - Ensure your query outputs numeric columns for the specified dimensions
    - Start with zscore for most use cases as it's the most mature implementation
    """
    pkg = _lazy_import_pkg()
    if pkg and hasattr(pkg, "list_available_algorithms"):
        return pkg.list_available_algorithms()
    raise ToolError("list_available_algorithms is not implemented in the migration package yet")


@mcp.tool()
def ping_elasticsearch() -> str:
    """
    Test connectivity to the Elasticsearch cluster.

    This tool checks if the KB-MCP server can successfully connect to the configured Elasticsearch hosts. It's useful for diagnosing connectivity issues before running queries or creating configurations.

    Inputs: None

    Returns:
    A JSON object with:
    - ping_success (boolean): true if connection successful, false otherwise
    - duration_ms (float): Time taken for the ping in milliseconds
    - error (string, optional): Error message if ping failed

    Example Success Response:
    {"ping_success": true, "duration_ms": 45.2}

    Example Failure Response:
    {"ping_success": false, "error": "Connection timeout", "duration_ms": 30000.0}

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


@mcp.tool()
@timed
def elasticsearch_sql(query: str) -> str:
    """
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
    {
      "columns": [
        {"name": "@timestamp", "type": "datetime"},
        {"name": "response", "type": "keyword"},
        {"name": "request_count", "type": "long"}
      ],
      "rows": [
        ["2025-10-01T00:00:00Z", "200", 150],
        ["2025-10-01T00:01:00Z", "404", 5]
      ]
    }

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
    request_id = str(uuid.uuid4())[:8]
    pkg = _lazy_import_pkg()
    if pkg and hasattr(pkg, "elasticsearch_sql"):
        return pkg.elasticsearch_sql(query)
    raise ToolError("elasticsearch_sql is not implemented in the migration package yet")

