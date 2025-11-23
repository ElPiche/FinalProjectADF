"""Split mcp tools package with lazy attribute loading.

All tool implementations moved here from the monolithic mcp_tools.py.
Modules avoid import-time network calls; perform I/O in function bodies only.
"""

import importlib

__all__ = [
    "create_da_config",
    "modify_kb_config",
    "list_kb_configurations",
    "describe_mcp_server",
    "list_available_algorithms",
    "elasticsearch_sql",
    "ping_elasticsearch",
]

_MODULE_MAP = {
    "create_da_config": "create_da_config",
    "modify_kb_config": "modify_kb_config",
    "list_kb_configurations": "list_kb_configurations",
    "describe_mcp_server": "describe_mcp_server",
    "list_available_algorithms": "list_available_algorithms",
    "elasticsearch_sql": "elasticsearch_sql",
    "ping_elasticsearch": "ping_elasticsearch",
}


def __getattr__(name: str):
    if name not in _MODULE_MAP:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(f"{__name__}.{_MODULE_MAP[name]}")
    value = getattr(module, name)
    globals()[name] = value
    return value
