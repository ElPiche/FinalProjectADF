import json
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


def fake_elasticsearch_success(*_args, **_kwargs):
    return json.dumps({"columns": [{"name": "response_time", "type": "long"}], "rows": []})


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


def test_create_da_config_succeeds_after_extractor_validation(monkeypatch):
    fake_collection = FakeCollection()

    monkeypatch.setattr(
        create_module.QueryValidator,
        "validate",
        lambda query, label: True,
    )
    monkeypatch.setattr(create_module, "elasticsearch_sql", fake_elasticsearch_success)
    monkeypatch.setattr(create_module, "connect_mongodb", lambda: FakeClient(fake_collection))

    result = create_da_config(
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

    assert "SUCCESS" in result
    assert fake_collection.inserted is not None


def test_modify_kb_config_stops_when_extractor_rejects(monkeypatch):
    config_id = str(ObjectId())
    document = build_existing_document(ObjectId(config_id))
    fake_collection = FakeCollection(document)

    monkeypatch.setattr(modify_module, "connect_mongodb", lambda: FakeClient(fake_collection))

    def raise_validation_error(*args, **kwargs):
        raise ToolError("invalid")

    monkeypatch.setattr(modify_module.QueryValidator, "validate", raise_validation_error)

    with pytest.raises(ToolError):
        modify_kb_config(
            config_id=config_id,
            detection_query="SELECT response_time FROM metrics WHERE foo=1",
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

    result = modify_kb_config(
        config_id=config_id,
        detection_query="SELECT response_time FROM metrics WHERE foo=1",
    )

    assert "SUCCESS" in result
    assert any(label == "detection" for _, label in validations)
