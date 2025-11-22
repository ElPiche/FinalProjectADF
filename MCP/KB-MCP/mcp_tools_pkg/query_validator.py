"""Query validation helper that proxies validations to the extractor service."""

import os
from typing import Any, Dict, Optional

import requests
from mcp.server.fastmcp.exceptions import ToolError

from utils import log_message as _utils_log_message


def log_message(
    message: str,
    level: str = "info",
    component: str = "query_validator",
    method: str = "entry",
    extra_data: Optional[Dict[str, Any]] = None,
):
    return _utils_log_message(message, level, component, method, extra_data=extra_data)


class QueryValidator:
    """Validate SQL queries through the extractor's validation endpoint.

    The extractor service enforces query compatibility with downstream ETL components.
    If the extractor is unavailable and fallback is enabled, the validator reports the
    failure but allows callers to continue with legacy validation logic.
    """

    DEFAULT_TIMEOUT_SECONDS = 3

    @classmethod
    def validate(
        cls,
        query: str,
        query_label: str = "query",
        timeout: Optional[int] = None,
        allow_fallback: Optional[bool] = None,
    ) -> bool:
        """Validate the provided query via the extractor.

        Args:
            query: SQL/ES|QL string to validate.
            query_label: Name used for logging/error context (e.g., "training").
            timeout: Optional timeout override for the HTTP request.
            allow_fallback: Optional override for fallback behavior. If None, the
                value is sourced from the EXTRACTOR_VALIDATION_FALLBACK env var.

        Returns:
            bool: True if extractor validation succeeded, False if a fallback was
            triggered. Raises ToolError when validation fails and fallback is not
            allowed.
        """

        endpoint = cls._build_endpoint()
        timeout_seconds = timeout or cls.DEFAULT_TIMEOUT_SECONDS
        fallback_enabled = cls._is_fallback_allowed(allow_fallback)

        log_message(
            f"Validating {query_label} query via extractor",
            "info",
            "query_validator",
            "request",
            extra_data={"extractor_endpoint": endpoint},
        )

        try:
            response = requests.post(endpoint, json={"query": query}, timeout=timeout_seconds)
        except requests.RequestException as exc:  # pragma: no cover - exercised via tests
            if fallback_enabled:
                log_message(
                    f"Extractor validation unreachable for {query_label} query; falling back",
                    "warning",
                    "query_validator",
                    "fallback",
                    extra_data={"error": str(exc)},
                )
                return False
            raise ToolError(f"Extractor validation failed for {query_label} query: {exc}") from exc

        payload = cls._safe_json(response)

        if response.status_code == 200:
            errors = payload.get("errors") if isinstance(payload, dict) else None
            if errors:
                message = payload.get("message", "Extractor reported validation errors")
                raise ToolError(f"Extractor validation failed for {query_label} query: {message} - {errors}")
            log_message(
                f"Extractor validation succeeded for {query_label} query",
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
                extra_data={"error": error_detail},
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
