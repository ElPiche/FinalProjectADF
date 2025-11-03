import time
import uuid
import json
from mcp.server.fastmcp.exceptions import ToolError
from utils import log_message as _utils_log_message


def log_message(message: str, level: str = "info", component: str = "mcp_tools", method: str = "entry", **kwargs):
    return _utils_log_message(message, level, component, method, **kwargs)


__tool_description__ = "Run an Elasticsearch SQL/ES-SQL query and return 'columns' and 'rows' in JSON. Use this to verify which columns your query produces."


def elasticsearch_sql(query: str) -> str:
    request_id = str(uuid.uuid4())[:8]

    log_message("Tool execution started", "info", "elasticsearch_sql", "entry",
                request_id=request_id, extra_data={"query_length": len(query)})

    import db
    es_host = db.es_host

    try:
        log_message("info", "elasticsearch_sql", "attempt",
                    f"Attempting SQL query execution with Elasticsearch at {es_host}",
                    request_id=request_id)
        from elasticsearch import Elasticsearch
        es = Elasticsearch(es_host, timeout=2)

        response = es.sql.query(query=query)

        results = {
            "columns": response.get("columns", []),
            "rows": response.get("rows", []),
            "cursor": response.get("cursor"),
            "total_rows": len(response.get("rows", []))
        }

        log_message(f"SQL query executed successfully with {es_host}, returned {results['total_rows']} rows", "info",
                    "elasticsearch_sql", "execution", request_id=request_id,
                    extra_data={"host": es_host, "row_count": results['total_rows']})
        return json.dumps(results, indent=2)

    except Exception as e:
        log_message(f"SQL query failed with {es_host}: {str(e)}", "warning",
                    "elasticsearch_sql", "retry", request_id=request_id,
                    extra_data={"host": es_host, "error_type": type(e).__name__})
        last_error = e

    error_msg = f"ERROR: Failed to execute SQL query on all Elasticsearch hosts - {str(last_error) if 'last_error' in locals() else 'No hosts available'}"
    log_message(error_msg, "error", "elasticsearch_sql", "failure", request_id=request_id,
                extra_data={"hosts_tried": 1})
    raise ToolError(error_msg)

