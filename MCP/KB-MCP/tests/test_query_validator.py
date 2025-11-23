import os
import sys

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from requests import RequestException

# Ensure package root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from mcp_tools_pkg.query_validator import QueryValidator  # noqa: E402  pylint: disable=wrong-import-position


class DummyResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("No JSON")
        return self._payload


def test_query_validator_success(monkeypatch):
    calls = {}

    def fake_post(url, json, timeout):
        calls["url"] = url
        return DummyResponse(200, {"message": "Query is valid", "errors": []})

    monkeypatch.setattr("mcp_tools_pkg.query_validator.requests.post", fake_post)

    assert QueryValidator.validate("SELECT 1 FROM test", "training") is True
    assert calls["url"].endswith("/api/validate/query")


def test_query_validator_rejects_errors(monkeypatch):
    def fake_post(url, json, timeout):
        return DummyResponse(400, {"message": "bad query", "errors": ["missing timestamp"]})

    monkeypatch.setattr("mcp_tools_pkg.query_validator.requests.post", fake_post)

    with pytest.raises(ToolError) as exc:
        QueryValidator.validate("SELECT 1 FROM test", "training")

    assert "Extractor validation rejected" in str(exc.value)


def test_query_validator_fallback_on_connection_error(monkeypatch):
    monkeypatch.setenv("EXTRACTOR_VALIDATION_FALLBACK", "true")

    def fake_post(url, json, timeout):
        raise RequestException("boom")

    monkeypatch.setattr("mcp_tools_pkg.query_validator.requests.post", fake_post)

    assert QueryValidator.validate("SELECT 1", "training") is False


def test_query_validator_no_fallback(monkeypatch):
    monkeypatch.setenv("EXTRACTOR_VALIDATION_FALLBACK", "false")

    def fake_post(url, json, timeout):
        raise RequestException("boom")

    monkeypatch.setattr("mcp_tools_pkg.query_validator.requests.post", fake_post)

    with pytest.raises(ToolError):
        QueryValidator.validate("SELECT 1", "training")


def test_query_validator_blocks_esql_pipeline(monkeypatch):
    def fail_post(*_args, **_kwargs):  # pragma: no cover - should never run
        raise AssertionError("Extractor should not be called for ES|QL queries")

    monkeypatch.setattr("mcp_tools_pkg.query_validator.requests.post", fail_post)

    with pytest.raises(ToolError) as exc:
        QueryValidator.validate("from logs | stats count()", "detection")

    assert "ES|QL" in str(exc.value)


def test_query_validator_requires_sql_entrypoint(monkeypatch):
    def fail_post(*_args, **_kwargs):  # pragma: no cover - should never run
        raise AssertionError("Extractor should not be called for invalid entrypoints")

    monkeypatch.setattr("mcp_tools_pkg.query_validator.requests.post", fail_post)

    with pytest.raises(ToolError) as exc:
        QueryValidator.validate("FROM metrics", "training")

    assert "Elasticsearch SQL keyword" in str(exc.value)
