import asyncio
import logging
import time
import uuid
from typing import TYPE_CHECKING

import requests
from requests.exceptions import ConnectionError, RequestException, Timeout
from mcp.server.fastmcp.exceptions import ToolError

import db
from utils import log_message as _utils_log_message
from .query_validator import VALIDATION_TIMEOUTS


if TYPE_CHECKING:
    from mcp.server.fastmcp import Context


logger = logging.getLogger(__name__)


def log_message(message: str, level: str = "info", component: str = "mcp_tools", method: str = "entry", **kwargs):
    return _utils_log_message(message, level, component, method, **kwargs)


def _run_query(query: str) -> dict:
    request_id = str(uuid.uuid4())[:8]
    timeout = VALIDATION_TIMEOUTS["ELASTICSEARCH_SQL_QUERY_TIMEOUT"]
    endpoint = f"{db.es_host.rstrip('/')}/_sql"
    start_time = time.time()

    log_message(
        "Tool execution started",
        "info",
        "elasticsearch_sql",
        "entry",
        request_id=request_id,
        extra_data={"query_length": len(query), "timeout_seconds": timeout},
    )

    headers = {"Content-Type": "application/json"}
    payload = {"query": query}

    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
    except Timeout as exc:
        elapsed = time.time() - start_time
        message = (
            f"Elasticsearch SQL query timed out after {timeout} seconds. "
            "Try simplifying the query, reducing the requested window, or increase "
            "ELASTICSEARCH_SQL_QUERY_TIMEOUT_SECONDS if the workload is expected to be slow."
        )
        log_message(
            message,
            "error",
            "elasticsearch_sql",
            "timeout",
            request_id=request_id,
            extra_data={"elapsed_seconds": round(elapsed, 2)},
        )
        raise ToolError(message) from exc
    except (ConnectionError, RequestException) as exc:
        elapsed = time.time() - start_time
        message = f"Elasticsearch SQL connection failed: {exc}"
        log_message(
            message,
            "error",
            "elasticsearch_sql",
            "connection",
            request_id=request_id,
            extra_data={"elapsed_seconds": round(elapsed, 2)},
        )
        raise ToolError(message) from exc

    elapsed = time.time() - start_time
    if response.status_code != 200:
        log_message(
            f"SQL query failed after {elapsed:.2f}s: {response.text}",
            "error",
            "elasticsearch_sql",
            "failure",
            request_id=request_id,
            extra_data={"status_code": response.status_code},
        )
        raise ToolError(f"Elasticsearch SQL query failed (HTTP {response.status_code}): {response.text}")

    try:
        result = response.json()
    except ValueError as exc:
        log_message(
            "SQL query returned non-JSON payload",
            "error",
            "elasticsearch_sql",
            "parse_error",
            request_id=request_id,
            extra_data={"status_code": response.status_code},
        )
        raise ToolError("Elasticsearch SQL query returned invalid JSON") from exc

    total_rows = len(result.get("rows", []))
    duration_ms = int(elapsed * 1000)
    log_message(
        f"SQL query executed successfully in {elapsed:.2f}s",
        "info",
        "elasticsearch_sql",
        "execution",
        request_id=request_id,
        extra_data={"row_count": total_rows, "endpoint": endpoint},
    )

    return {
        "columns": result.get("columns", []),
        "rows": result.get("rows", []),
        "cursor": result.get("cursor"),
        "duration_ms": duration_ms,
    }


async def elasticsearch_sql(query: str, ctx: "Context | None" = None) -> dict:
    """Async wrapper that executes the Elasticsearch SQL query on a worker thread."""
    # ctx reserved for future progress reporting integration. It is unused when None.
    return await asyncio.to_thread(_run_query, query)

