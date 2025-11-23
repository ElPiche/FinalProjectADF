import asyncio
import os
import sys
from types import SimpleNamespace
import importlib

import pytest
from bson import ObjectId
from mcp.server.fastmcp.exceptions import ToolError

# Ensure package root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from mcp_tools_pkg.create_da_config import create_da_config  # noqa: E402  pylint: disable=wrong-import-position
from mcp_tools_pkg.modify_kb_config import modify_kb_config  # noqa: E402  pylint: disable=wrong-import-position

create_module = importlib.import_module("mcp_tools_pkg.create_da_config")
modify_module = importlib.import_module("mcp_tools_pkg.modify_kb_config")


VALID_ALGORITHMS = [
    {
        "alg_name": "zscore",
        "alg_parameters": [
            {"dimension": "response_time"},
        ],
    }
]


class FakeCollection:
    def __init__(self, document=None):
        self.document = document
        self.inserted = None
        self.updated_payload = None

    def insert_one(self, payload):
        self.inserted = payload
        return SimpleNamespace(inserted_id=ObjectId())

    def find_one(self, query):
        if not self.document:
            return None
        if query.get("_id") == self.document.get("_id"):
            return dict(self.document)
        if query.get("name") == self.document.get("name"):
            return dict(self.document)
        return None

    def update_one(self, _filter, update):
        self.updated_payload = update
        return SimpleNamespace(modified_count=1)


class FakeDatabase:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, name):
        return self.collection


class FakeClient:
    def __init__(self, collection):
        self.database = FakeDatabase(collection)
        self.closed = False

    def __getitem__(self, name):
        return self.database

    def close(self):
        self.closed = True


async def fake_elasticsearch_success(*_args, **_kwargs):
    return {"columns": [{"name": "response_time", "type": "long"}], "rows": []}


def build_existing_document(object_id):
    return {
        "_id": object_id,
        "name": "Existing config",
        "description": "Monitor latency",
        "change_flag": 0,
        "scheduling": {
            "training_config": {
                "training_query": "SELECT response_time FROM metrics",
                "from": "2025-01-01T00:00:00Z",
                "to": "2025-01-02T00:00:00Z",
                "training_window": 3600,
                "is_active": True,
            },
            "detection_config": {
                "detection_query": "SELECT response_time FROM metrics",
                "from": "2025-01-02T00:00:00Z",
                "frequency": "*/15 * * * *",
                "detection_window": 900,
                "is_active": True,
            },
        },
        "algorithms": VALID_ALGORITHMS,
    }


def test_create_da_config_stops_when_extractor_rejects(monkeypatch):
    def fake_validate(query, label):
        raise ToolError("invalid query")

    monkeypatch.setattr(create_module.QueryValidator, "validate", fake_validate)

    with pytest.raises(ToolError):
        asyncio.run(
            create_da_config(
                name="Config",
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
                algorithms=VALID_ALGORITHMS,
            )
        )


def test_create_da_config_succeeds_after_extractor_validation(monkeypatch):
    fake_collection = FakeCollection()

    monkeypatch.setattr(
        create_module.QueryValidator,
        "validate",
        lambda query, label: True,
    )
    monkeypatch.setattr(create_module, "elasticsearch_sql", fake_elasticsearch_success)
    monkeypatch.setattr(create_module, "connect_mongodb", lambda: FakeClient(fake_collection))

    result = asyncio.run(
        create_da_config(
            name="Config",
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
            algorithms=VALID_ALGORITHMS,
        )
    )

    assert "SUCCESS" in result
    assert fake_collection.inserted is not None


def test_create_da_config_replaces_placeholders_before_validation(monkeypatch):
    fake_collection = FakeCollection()
    captured_queries = []
    preview_queries = []

    def fake_validate(query, label):
        captured_queries.append((label, query))
        return True

    async def fake_elastic(query, ctx=None):  # noqa: D401 - simple stub
        preview_queries.append(query)
        return {"columns": [{"name": "response_time", "type": "long"}], "rows": []}

    monkeypatch.setattr(create_module.QueryValidator, "validate", fake_validate)
    monkeypatch.setattr(create_module, "elasticsearch_sql", fake_elastic)
    monkeypatch.setattr(create_module, "connect_mongodb", lambda: FakeClient(fake_collection))

    training_query = "SELECT DATE_TRUNC('HOUR', '@timestamp') AS es_timestamp FROM logs WHERE '@timestamp' >= '$from' AND '@timestamp' < '$to'"
    detection_query = "SELECT COUNT(*) AS total FROM logs WHERE '@timestamp' >= '$from' AND '@timestamp' < '$to'"

    result = asyncio.run(
        create_da_config(
            name="placeholder-config",
            description="Desc",
            training_query=training_query,
            detection_query=detection_query,
            training_from="2025-01-01T00:00:00Z",
            training_to="2025-01-02T00:00:00Z",
            training_is_active=True,
            detection_is_active=True,
            training_window=3600,
            detection_window=900,
            detection_frequency="*/15 * * * *",
            detection_start="2025-01-02T00:00:00Z",
            algorithms=VALID_ALGORITHMS,
        )
    )

    assert "SUCCESS" in result
    assert captured_queries
    assert preview_queries
    for label, query in captured_queries:
        assert "$from" not in query
        assert "$to" not in query
        assert "2025-01-01T00:00:00Z" in query
        assert "2025-01-02T00:00:00Z" in query
    for query in preview_queries:
        assert "$from" not in query
        assert "$to" not in query


def test_create_config_duplicate_name_warns(monkeypatch):
    existing = {"_id": ObjectId(), "name": "duplicate-config"}
    fake_collection = FakeCollection(document=existing)

    monkeypatch.setattr(create_module.QueryValidator, "validate", lambda *_: True)
    monkeypatch.setattr(create_module, "elasticsearch_sql", fake_elasticsearch_success)
    monkeypatch.setattr(create_module, "connect_mongodb", lambda: FakeClient(fake_collection))

    result = asyncio.run(
        create_da_config(
            name="duplicate-config",
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
            algorithms=VALID_ALGORITHMS,
        )
    )

    assert "Warning" in result
    assert "duplicate-config" in result


def test_create_config_unique_name_has_no_warning(monkeypatch):
    fake_collection = FakeCollection()

    monkeypatch.setattr(create_module.QueryValidator, "validate", lambda *_: True)
    monkeypatch.setattr(create_module, "elasticsearch_sql", fake_elasticsearch_success)
    monkeypatch.setattr(create_module, "connect_mongodb", lambda: FakeClient(fake_collection))

    result = asyncio.run(
        create_da_config(
            name="unique-config",
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
            algorithms=VALID_ALGORITHMS,
        )
    )

    assert "Warning" not in result
    assert "SUCCESS" in result


def test_modify_config_replaces_placeholders_before_validation(monkeypatch):
    object_id = ObjectId()
    existing_document = build_existing_document(object_id)
    existing_document["_id"] = object_id
    existing_document["scheduling"]["training_config"]["training_query"] = (
        "SELECT count(*) FROM logs WHERE '@timestamp' >= '$from' AND '@timestamp' < '$to'"
    )
    fake_collection = FakeCollection(document=existing_document)

    captured_queries = []
    preview_queries = []

    def fake_validate(query, label):
        captured_queries.append((label, query))
        return True

    async def fake_elastic(query, ctx=None):
        preview_queries.append(query)
        return {"columns": [{"name": "response_time", "type": "long"}], "rows": []}

    monkeypatch.setattr(modify_module.QueryValidator, "validate", fake_validate)
    monkeypatch.setattr(modify_module, "elasticsearch_sql", fake_elastic)
    monkeypatch.setattr(modify_module, "connect_mongodb", lambda: FakeClient(fake_collection))

    result = asyncio.run(
        modify_kb_config(
            config_id=str(object_id),
            detection_query="SELECT max(response_time) FROM logs WHERE '@timestamp' >= '$from' AND '@timestamp' < '$to'",
        )
    )

    assert "SUCCESS" in result
    assert captured_queries
    label, detection_query = captured_queries[0]
    assert label == "detection"
    assert "$from" not in detection_query
    assert "$to" not in detection_query
    assert "2025-01-01T00:00:00Z" in detection_query
    assert "2025-01-02T00:00:00Z" in detection_query
    for query in preview_queries:
        assert "$from" not in query
        assert "$to" not in query


def test_modify_kb_config_stops_when_extractor_rejects(monkeypatch):
    config_id = str(ObjectId())
    document = build_existing_document(ObjectId(config_id))
    fake_collection = FakeCollection(document)

    monkeypatch.setattr(modify_module, "connect_mongodb", lambda: FakeClient(fake_collection))

    def raise_validation_error(*args, **kwargs):
        raise ToolError("invalid")

    monkeypatch.setattr(modify_module.QueryValidator, "validate", raise_validation_error)

    with pytest.raises(ToolError):
        asyncio.run(
            modify_kb_config(
                config_id=config_id,
                detection_query="SELECT response_time FROM metrics WHERE foo=1",
            )
        )


def test_modify_kb_config_runs_when_extractor_passes(monkeypatch):
    config_id = str(ObjectId())
    document = build_existing_document(ObjectId(config_id))
    fake_collection = FakeCollection(document)

    monkeypatch.setattr(modify_module, "connect_mongodb", lambda: FakeClient(fake_collection))

    validations = []

    def record_validate(query, label):
        validations.append((query, label))
        return True

    monkeypatch.setattr(modify_module.QueryValidator, "validate", record_validate)
    monkeypatch.setattr(modify_module, "elasticsearch_sql", fake_elasticsearch_success)

    result = asyncio.run(
        modify_kb_config(
            config_id=config_id,
            detection_query="SELECT response_time FROM metrics WHERE foo=1",
        )
    )

    assert "SUCCESS" in result
    assert any(label == "detection" for _, label in validations)
