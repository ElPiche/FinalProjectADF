"""Shared configuration helpers for MCP tools."""
from __future__ import annotations

import os
from typing import Iterable


def _env_int(name: str, default: int, legacy_names: Iterable[str] | None = None) -> int:
    """Return an integer environment variable with optional legacy fallbacks."""
    names = [name]
    if legacy_names:
        names.extend(legacy_names)
    for env_name in names:
        raw_value = os.getenv(env_name)
        if raw_value is None:
            continue
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            # Invalid override; ignore and continue to next candidate
            continue
    return default


MAX_TOOL_EXECUTION_TIME = _env_int("MAX_TOOL_EXECUTION_TIME", 60)
MONGODB_OPERATION_TIMEOUT = _env_int("MONGODB_OPERATION_TIMEOUT", 10)
ELASTICSEARCH_QUERY_TIMEOUT = _env_int(
    "ELASTICSEARCH_QUERY_TIMEOUT",
    15,
    legacy_names=("ELASTICSEARCH_SQL_QUERY_TIMEOUT_SECONDS",),
)
ELASTICSEARCH_SQL_PREVIEW_TIMEOUT = _env_int(
    "ELASTICSEARCH_SQL_PREVIEW_TIMEOUT",
    5,
    legacy_names=("ELASTICSEARCH_SQL_PREVIEW_TIMEOUT_SECONDS",),
)
EXTRACTOR_VALIDATION_TIMEOUT = _env_int(
    "EXTRACTOR_VALIDATION_TIMEOUT",
    20,
    legacy_names=("EXTRACTOR_VALIDATION_TIMEOUT_SECONDS",),
)

ENABLE_PROGRESS_REPORTING = os.getenv("ENABLE_PROGRESS_REPORTING", "true").lower() not in {"false", "0", "no"}
