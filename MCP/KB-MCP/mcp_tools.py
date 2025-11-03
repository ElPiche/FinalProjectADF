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
    algorithms: List[dict] = Field(description="List of algorithm configurations")
) -> str:
    """Create a new anomaly-detection configuration.

    Provide name, optional description, scheduling (training_query/detection_query and timestamps),
    and an 'algorithms' array. Returns the saved configuration ID or validation errors.
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
    description: str = None,
    training_query: str = None,
    detection_query: str = None,
    training_from: str = None,
    training_to: str = None,
    detection_frequency: str = None,
    detection_start: str = None,
    algorithms: dict = None
) -> str:
    """Update an existing configuration by config_id.

    Supply any fields from creation to update them (description, queries, scheduling, algorithms).
    Returns confirmation or validation errors.
    """
    pkg = _lazy_import_pkg()
    if pkg and hasattr(pkg, "modify_kb_config"):
        return pkg.modify_kb_config(config_id, description, training_query, detection_query,
                                     training_from, training_to, detection_frequency,
                                     detection_start, algorithms)
    raise ToolError("modify_kb_config is not implemented in the migration package yet")


@mcp.tool()
def list_kb_configurations() -> str:
    """Return a human-readable listing of saved KB configurations (name, id, scheduling summary, algorithms)."""
    pkg = _lazy_import_pkg()
    if pkg and hasattr(pkg, "list_kb_configurations"):
        return pkg.list_kb_configurations()
    raise ToolError("list_kb_configurations is not implemented in the migration package yet")


@mcp.tool()
def describe_mcp_server() -> str:
    """Return human-readable instructions for using KB-MCP tools, including required inputs and examples."""
    pkg = _lazy_import_pkg()
    if pkg and hasattr(pkg, "describe_mcp_server"):
        return pkg.describe_mcp_server()
    raise ToolError("describe_mcp_server is not implemented in the migration package yet")


@mcp.tool()
def list_available_algorithms() -> str:
    """Return a Markdown listing of implemented algorithms and a JSON example showing how to populate the 'algorithms' field."""
    pkg = _lazy_import_pkg()
    if pkg and hasattr(pkg, "list_available_algorithms"):
        return pkg.list_available_algorithms()
    raise ToolError("list_available_algorithms is not implemented in the migration package yet")


@mcp.tool()
def ping_elasticsearch() -> str:
    """Check connectivity to Elasticsearch hosts. Returns ping_success (boolean) and duration_ms (float)."""
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
    """Run an Elasticsearch SQL/ES-SQL query and return 'columns' and 'rows' in JSON to verify query output columns."""
    request_id = str(uuid.uuid4())[:8]
    pkg = _lazy_import_pkg()
    if pkg and hasattr(pkg, "elasticsearch_sql"):
        return pkg.elasticsearch_sql(query)
    raise ToolError("elasticsearch_sql is not implemented in the migration package yet")

