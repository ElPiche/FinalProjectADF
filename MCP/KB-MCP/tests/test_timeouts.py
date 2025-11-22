import asyncio
import importlib
import os
import sys
from types import SimpleNamespace

import pytest
from requests.exceptions import Timeout
from mcp.server.fastmcp.exceptions import ToolError

# Ensure package root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from mcp_tools_pkg.query_validator import QueryValidator  # noqa: E402  pylint: disable=wrong-import-position
from mcp_tools_pkg.elasticsearch_sql import elasticsearch_sql  # noqa: E402  pylint: disable=wrong-import-position
from mcp_tools_pkg.create_da_config import create_da_config  # noqa: E402  pylint: disable=wrong-import-position

DEFAULT_ALGORITHMS = [
    {
        "alg_name": "zscore",
        "alg_parameters": [
            {"dimension": "response_time"},
        ],
    }
]


def test_query_validator_timeout(monkeypatch):
    monkeypatch.setenv("EXTRACTOR_VALIDATION_FALLBACK", "false")

    def raise_timeout(*_args, **_kwargs):
        raise Timeout("connection timeout")

    monkeypatch.setattr("mcp_tools_pkg.query_validator.requests.post", raise_timeout)

    with pytest.raises(ToolError) as exc:
        QueryValidator.validate("SELECT 1 FROM logs", "training")

    assert "timed out" in str(exc.value)


def test_elasticsearch_sql_timeout(monkeypatch):
    def raise_timeout(*_args, **_kwargs):
        raise Timeout("query timeout")

    es_module = importlib.import_module("mcp_tools_pkg.elasticsearch_sql")
    monkeypatch.setattr(es_module.requests, "post", raise_timeout)

    with pytest.raises(ToolError) as exc:
        elasticsearch_sql("SELECT * FROM logs LIMIT 1")

    assert "timed out" in str(exc.value)


def test_create_da_config_logs_steps(monkeypatch, caplog):
    caplog.set_level("INFO", logger="KB-MCP")

    class StubCollection:
        def __init__(self):
            self.inserted = None

        def insert_one(self, payload):
            self.inserted = payload
            return SimpleNamespace(inserted_id="507f1f77bcf86cd799439011")

        def find_one(self, query):
            return None

    class StubDatabase:
        def __init__(self, collection):
            self.collection = collection

        def __getitem__(self, _name):
            return self.collection

    class StubClient:
        def __init__(self, collection):
            self.database = StubDatabase(collection)

        def __getitem__(self, _name):
            return self.database

        def close(self):
            pass

    collection = StubCollection()

    create_module = importlib.import_module("mcp_tools_pkg.create_da_config")

    monkeypatch.setattr(create_module.QueryValidator, "validate", lambda *_args, **_kwargs: True)

    async def _fake_elasticsearch_sql(*_args, **_kwargs):
        return {"columns": [{"name": "response_time"}], "rows": []}

    monkeypatch.setattr(create_module, "elasticsearch_sql", _fake_elasticsearch_sql)
    monkeypatch.setattr(create_module, "connect_mongodb", lambda: StubClient(collection))

    result = asyncio.run(
        create_da_config(
            name="log-test",
            description="Desc",
            training_query="SELECT response_time FROM metrics",
            detection_query="SELECT response_time FROM metrics",
            training_from="2025-01-01T00:00:00Z",
            training_to="2025-01-02T00:00:00Z",
            training_is_active=True,
            detection_is_active=True,
            training_window=3600,
            detection_window=900,
            detection_frequency="*/15 * * * *",
            detection_start="2025-01-02T00:00:00Z",
            algorithms=DEFAULT_ALGORITHMS,
        )
    )

    assert "SUCCESS" in result
    assert "Step 1/5" in caplog.text
    assert "Step 5/5" in caplog.text
