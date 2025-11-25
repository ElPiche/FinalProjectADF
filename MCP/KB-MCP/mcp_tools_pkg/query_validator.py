"""Query validation helper that proxies validations to the extractor service."""

import logging
import os
import re
import time
from typing import Any, Dict, Optional

import requests
from requests.exceptions import ConnectionError, RequestException, Timeout
from mcp.server.fastmcp.exceptions import ToolError

from utils import log_message as _utils_log_message
from .config import (
    ELASTICSEARCH_QUERY_TIMEOUT,
    ELASTICSEARCH_SQL_PREVIEW_TIMEOUT,
    EXTRACTOR_VALIDATION_TIMEOUT,
)


logger = logging.getLogger(__name__)


VALIDATION_TIMEOUTS = {
    "EXTRACTOR_VALIDATION_TIMEOUT": EXTRACTOR_VALIDATION_TIMEOUT,
    "ELASTICSEARCH_SQL_PREVIEW_TIMEOUT": ELASTICSEARCH_SQL_PREVIEW_TIMEOUT,
    "ELASTICSEARCH_SQL_QUERY_TIMEOUT": ELASTICSEARCH_QUERY_TIMEOUT,
}

logger.info(
    "Timeout configuration loaded: extractor=%ss, es_preview=%ss, es_query=%ss",
    VALIDATION_TIMEOUTS["EXTRACTOR_VALIDATION_TIMEOUT"],
    VALIDATION_TIMEOUTS["ELASTICSEARCH_SQL_PREVIEW_TIMEOUT"],
    VALIDATION_TIMEOUTS["ELASTICSEARCH_SQL_QUERY_TIMEOUT"],
)


def log_message(
    message: str,
    level: str = "info",
    component: str = "query_validator",
    method: str = "entry",
    extra_data: Optional[Dict[str, Any]] = None,
):
    return _utils_log_message(message, level, component, method, extra_data=extra_data)


class QueryValidator:
    """Validate Elasticsearch SQL queries through the extractor endpoint.

    The extractor service enforces query compatibility with downstream ETL components.
    If the extractor is unavailable and fallback is enabled, the validator reports the
    failure but allows callers to continue with legacy validation logic. Only the SQL
    dialect exposed by Elasticsearch's `_sql` endpoint is supported; ES|QL or other
    syntaxes must be rejected before reaching the extractor.
    """

    DEFAULT_TIMEOUT_SECONDS = VALIDATION_TIMEOUTS["EXTRACTOR_VALIDATION_TIMEOUT"]
    _SQL_ENTRYPOINTS = ("select", "show", "describe", "explain", "with")
    _PIPE_PATTERN = re.compile(r"\|\s*[A-Za-z]", re.MULTILINE)

    @classmethod
    def validate(
        cls,
        query: str,
        query_label: str = "query",
        timeout: Optional[int] = None,
        allow_fallback: Optional[bool] = None,
        query_mode: Optional[str] = None,
        timestamp_field: Optional[str] = None,
    ) -> bool:
        """Validate the provided query via the extractor.

        Args:
            query: Elasticsearch SQL string to validate.
            query_label: Name used for logging/error context (e.g., "training").
            timeout: Optional timeout override for the HTTP request.
            allow_fallback: Optional override for fallback behavior. If None, the
                value is sourced from the EXTRACTOR_VALIDATION_FALLBACK env var.

        Returns:
            bool: True if extractor validation succeeded, False if a fallback was
            triggered. Raises ToolError when validation fails and fallback is not
            allowed.
        """

        cls._assert_elasticsearch_sql(query, query_label)

        endpoint = cls._build_endpoint()
        timeout_seconds = timeout or VALIDATION_TIMEOUTS["EXTRACTOR_VALIDATION_TIMEOUT"]
        fallback_enabled = cls._is_fallback_allowed(allow_fallback)

        log_message(
            f"Validating {query_label} query via extractor (timeout={timeout_seconds}s)",
            "info",
            "query_validator",
            "request",
            extra_data={
                "extractor_endpoint": endpoint,
                "query_mode": query_mode,
                "timestamp_field": timestamp_field,
            },
        )

        start_time = time.time()

        payload = {"query": query}
        if query_mode:
            payload["query_mode"] = query_mode
        if timestamp_field:
            payload["timestamp_field"] = timestamp_field

        try:
            response = requests.post(endpoint, json=payload, timeout=timeout_seconds)
        except Timeout as exc:
            elapsed = time.time() - start_time
            message = (
                f"Extractor validation timed out after {timeout_seconds} seconds for {query_label} query. "
                "The query may be too complex or the extractor cluster may be slow. "
                "Try simplifying the query, narrowing the time range, or increasing EXTRACTOR_VALIDATION_TIMEOUT_SECONDS if appropriate."
            )
            log_message(
                message,
                "error",
                "query_validator",
                "timeout",
                extra_data={"elapsed_seconds": round(elapsed, 2)},
            )
            raise ToolError(message) from exc
        except (ConnectionError, RequestException) as exc:  # pragma: no cover - exercised via tests
            elapsed = time.time() - start_time
            if fallback_enabled:
                log_message(
                    f"Extractor validation unreachable for {query_label} query; falling back",
                    "warning",
                    "query_validator",
                    "fallback",
                    extra_data={"error": str(exc), "elapsed_seconds": round(elapsed, 2)},
                )
                return False
            raise ToolError(f"Extractor validation failed for {query_label} query: {exc}") from exc

        payload = cls._safe_json(response)
        elapsed = time.time() - start_time

        if response.status_code == 200:
            errors = payload.get("errors") if isinstance(payload, dict) else None
            if errors:
                message = payload.get("message", "Extractor reported validation errors")
                raise ToolError(f"Extractor validation failed for {query_label} query: {message} - {errors}")
            log_message(
                f"Extractor validation succeeded for {query_label} query in {elapsed:.2f}s",
                "info",
                "query_validator",
                "success",
            )
            return True

        if response.status_code == 400:
            error_detail = cls._format_error_detail(payload, response)
            raise ToolError(f"Extractor validation rejected {query_label} query: {error_detail}")

        error_detail = cls._format_error_detail(payload, response)
        if fallback_enabled:
            log_message(
                f"Extractor validation returned HTTP {response.status_code}; falling back",
                "warning",
                "query_validator",
                "fallback",
                extra_data={"error": error_detail, "elapsed_seconds": round(elapsed, 2)},
            )
            return False

        raise ToolError(
            f"Extractor validation failed for {query_label} query (HTTP {response.status_code}): {error_detail}"
        )

    @staticmethod
    def _safe_json(response) -> Dict[str, Any]:
        try:
            data = response.json()
            if isinstance(data, dict):
                return data
            return {"message": data}
        except ValueError:
            return {}

    @staticmethod
    def _format_error_detail(payload: Dict[str, Any], response) -> str:
        if not payload:
            return response.text or "No error details provided"
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            return ", ".join(str(err) for err in errors)
        if isinstance(errors, str):
            return errors
        message = payload.get("message")
        if message:
            return message
        return response.text or "No error details provided"

    @staticmethod
    def _get_env_value(name: str, default: str) -> str:
        value = os.getenv(name)
        return value.strip() if value and value.strip() else default

    @classmethod
    def _assert_elasticsearch_sql(cls, query: str, query_label: str) -> None:
        cleaned = cls._strip_leading_comments(query or "")
        if not cleaned:
            raise ToolError(f"{query_label.title()} query must be a non-empty Elasticsearch SQL statement")

        if cls._PIPE_PATTERN.search(cleaned):
            raise ToolError(
                f"{query_label.title()} query appears to use ES|QL style pipelines, which are not supported. "
                "Please provide an Elasticsearch SQL statement (SELECT/SHOW/DESCRIBE/EXPLAIN/WITH)."
            )

        token = cls._leading_token(cleaned)
        if token not in cls._SQL_ENTRYPOINTS:
            raise ToolError(
                f"{query_label.title()} query must start with an Elasticsearch SQL keyword "
                f"({', '.join(keyword.upper() for keyword in cls._SQL_ENTRYPOINTS)}); received '{token or 'unknown'}'."
            )

        if token in {"with", "explain"}:
            lowered = cleaned.lower()
            if "select" not in lowered:
                raise ToolError(f"{query_label.title()} query must include a SELECT statement when using {token.upper()}.")

    @staticmethod
    def _strip_leading_comments(query: str) -> str:
        text = query.lstrip()
        while True:
            if text.startswith("/*"):
                end = text.find("*/", 2)
                if end == -1:
                    return ""
                text = text[end + 2 :].lstrip()
                continue
            if text.startswith("--") or text.startswith("//"):
                newline = text.find("\n")
                if newline == -1:
                    return ""
                text = text[newline + 1 :].lstrip()
                continue
            if text.startswith("#"):
                newline = text.find("\n")
                if newline == -1:
                    return ""
                text = text[newline + 1 :].lstrip()
                continue
            break
        return text

    @staticmethod
    def _leading_token(query: str) -> Optional[str]:
        match = re.match(r"([A-Za-z]+)", query)
        return match.group(1).lower() if match else None

    @classmethod
    def _build_endpoint(cls) -> str:
        host = cls._get_env_value("EXTRACTOR_HOST", "http://extractor:8080")
        host = host.rstrip("/")
        return f"{host}/api/validate/query"

    @classmethod
    def _is_fallback_allowed(cls, override: Optional[bool]) -> bool:
        if override is not None:
            return override
        env_value = cls._get_env_value("EXTRACTOR_VALIDATION_FALLBACK", "true").lower()
        return env_value not in {"0", "false", "no"}


def materialize_query_time_range(
    query: str,
    from_timestamp: Optional[str],
    to_timestamp: Optional[str],
    query_label: str,
) -> str:
    """Replace $from/$to placeholders with real timestamps before validation.

    The extractor executes the provided SQL, so placeholder values must be
    resolved to concrete ISO timestamps to avoid syntax errors during query
    validation. This helper intentionally reuses the *training* window for both
    training and detection queries because the goal is only to exercise the
    statement structure, not the production detection schedule.
    """

    if not query:
        return query

    materialized = query

    if "$from" in materialized:
        if not from_timestamp:
            raise ToolError(
                f"Cannot validate {query_label} query because $from is present but training_from is missing."
            )
        materialized = materialized.replace("$from", from_timestamp)

    if "$to" in materialized:
        if not to_timestamp:
            raise ToolError(
                f"Cannot validate {query_label} query because $to is present but training_to is missing."
            )
        materialized = materialized.replace("$to", to_timestamp)

    unresolved = [placeholder for placeholder in ("$from", "$to") if placeholder in materialized]
    if unresolved:
        raise ToolError(
            f"Unable to resolve placeholder(s) {', '.join(unresolved)} in {query_label} query."
        )

    return materialized
