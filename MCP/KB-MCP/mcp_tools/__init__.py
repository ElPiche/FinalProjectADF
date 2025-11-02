"""mcp_tools package - split out tools from the monolithic mcp_tools.py.

This package provides individual modules for each MCP tool. The old
`mcp_tools.py` file will act as a compatibility shim that imports and
re-exports the same symbols. Modules here should avoid heavy import-time
work (no network calls) — prefer lazy operations inside functions.
"""
from typing import TYPE_CHECKING

# Expose a lightweight public surface. Actual tool implementations are
# imported lazily in the compatibility shim to keep startup fast.
__all__ = [
    "create_da_config",
    "modify_kb_config",
    "list_kb_configurations",
    "describe_mcp_server",
    "list_available_algorithms",
    "elasticsearch_sql",
    "ping_elasticsearch",
    "mcp",
]

# Placeholder for FastMCP instance; real instance will be created in shim.
mcp = None
