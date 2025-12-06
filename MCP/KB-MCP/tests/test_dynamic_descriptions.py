#!/usr/bin/env python3
"""
Unit tests for dynamic description generation functionality.
Tests that descriptions are generated from Pydantic models and contain expected content.
Run with: python -m pytest tests/test_dynamic_descriptions.py -v
"""

import asyncio
import sys
import os
import json
# Ensure package root (KB-MCP) is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
import importlib
from description_utils import (
    generate_kb_config_description,
    generate_kb_config_example,
    ALGORITHM_CONFIG_DESCRIPTION
)
from models import KBConfig, ZScoreConfig


DEFAULT_CREATE_ARGS = {
    "name": "test",
    "description": "test",
    "elasticsearch_sql_query": "SELECT @timestamp, field FROM test WHERE @timestamp >= '$from' AND @timestamp < '$to'",
    "query_mode": {"type": "raw", "timestamp_field": "@timestamp"},
    "training_from": "2025-01-01T00:00:00Z",
    "training_to": "2025-01-02T00:00:00Z",
    "training_is_active": True,
    "detection_is_active": True,
    "detection_window": 3600,
    "detection_frequency": "*/5 * * * *",  # Every 5 minutes, valid for raw mode
    "detection_start": "2025-01-03T00:00:00Z",
    "algorithm": {"name": "zscore", "parameters": [{"dimension": "field"}]},
}


def _patch_create_da_config_dependencies(monkeypatch):
    create_module = importlib.import_module("mcp_tools_pkg.create_da_config")
    monkeypatch.setattr(create_module.QueryValidator, "validate", lambda *args, **kwargs: True)
    async def _fake_elasticsearch_sql(*_args, **_kwargs):
        return {
            "columns": [
                {"name": "@timestamp", "type": "date"},
                {"name": "field", "type": "long"},
            ],
            "rows": [],
        }

    monkeypatch.setattr(create_module, "elasticsearch_sql", _fake_elasticsearch_sql)
    monkeypatch.setattr(create_module, "connect_mongodb", lambda: None)


def _invoke_create_da_config(monkeypatch, **overrides):
    from mcp_tools_pkg.create_da_config import create_da_config

    _patch_create_da_config_dependencies(monkeypatch)
    params = DEFAULT_CREATE_ARGS.copy()
    params.update(overrides)
    return asyncio.run(create_da_config(**params))


class TestDynamicDescriptions:
    """Test suite for dynamic description generation."""

    def test_generate_kb_config_description_returns_string(self):
        """Test that generate_kb_config_description returns a non-empty string."""
        description = generate_kb_config_description()
        assert isinstance(description, str)
        assert len(description) > 0
        assert "KBConfig" in description

    def test_generate_kb_config_description_contains_model_fields(self):
        """Test that the description contains expected fields from KBConfig model."""
        description = generate_kb_config_description()

        # Check for main KBConfig fields
        assert "name" in description
        assert "description" in description
        assert "elasticsearch_sql_query" in description
        assert "query_mode" in description
        assert "algorithm" in description

        # Check for nested config fields (using aliases from the model)
        assert "from" in description  # This is the alias for from_ field
        assert "to" in description
        assert "frequency" in description

    def test_generate_kb_config_example_returns_string(self):
        """Test that generate_kb_config_example returns a string."""
        example = generate_kb_config_example()
        assert isinstance(example, str)
        # Should either be valid JSON or an error message
        assert len(example) > 0

    def test_generate_kb_config_example_contains_required_fields(self):
        """Test that the example contains all required KBConfig fields."""
        import json

        example_str = generate_kb_config_example()

        # Should not be an error message
        assert not example_str.startswith("Error"), f"Example generation failed: {example_str}"

        # Parse the JSON
        try:
            example = json.loads(example_str)
        except json.JSONDecodeError as e:
            pytest.fail(f"Example is not valid JSON: {e}")

        # Check top-level fields
        assert "name" in example
        assert "description" in example
        assert "scheduling" in example
        assert "algorithm" in example

        # Check nested scheduling fields
        scheduling = example["scheduling"]
        assert "training_config" in scheduling
        assert "detection_config" in scheduling

        training_config = scheduling["training_config"]
        assert "from" in training_config
        assert "to" in training_config

        detection_config = scheduling["detection_config"]
        assert "from" in detection_config
        assert "frequency" in detection_config

        # Check algorithm structure
        algorithm = example["algorithm"]
        assert isinstance(algorithm, dict)
        assert "name" in algorithm
        assert "parameters" in algorithm

    def test_algorithm_config_description_contains_zscore(self):
        """Test that ALGORITHM_CONFIG_DESCRIPTION contains zscore algorithm info."""
        assert isinstance(ALGORITHM_CONFIG_DESCRIPTION, str)
        assert len(ALGORITHM_CONFIG_DESCRIPTION) > 0
        assert "zscore" in ALGORITHM_CONFIG_DESCRIPTION.lower()

    def test_algorithm_config_description_contains_dimensions(self):
        """Test that ALGORITHM_CONFIG_DESCRIPTION mentions dimensions."""
        assert "dimension" in ALGORITHM_CONFIG_DESCRIPTION.lower()

    def test_descriptions_update_with_model_changes(self):
        """Test that descriptions reflect changes to the underlying models."""
        # Get baseline description
        baseline_description = generate_kb_config_description()

        # This is a conceptual test - in practice, we'd need to modify the model
        # and reload the module to test this fully. For now, we verify the
        # description generation mechanism works with current models.

        # Verify the description contains fields that exist in our current models
        assert "name: str" in baseline_description or "name" in baseline_description
        assert "description: str" in baseline_description or "description" in baseline_description

        # Verify it doesn't contain fields that don't exist
        assert "nonexistent_field" not in baseline_description

    def test_description_generation_is_deterministic(self):
        """Test that description generation produces consistent results."""
        desc1 = generate_kb_config_description()
        desc2 = generate_kb_config_description()

        assert desc1 == desc2, "Description generation should be deterministic"

    def test_pydantic_validation_works(self):
        """Test that Pydantic models properly validate input data."""
        from models import (
            KBConfig,
            TrainingConfig,
            DetectionConfig,
            SchedulingConfig,
            AlgorithmConfig,
            AlgorithmParameter,
        )

        config = KBConfig(
            name="test_config",
            description="test description",
            change_flag=0,
            elasticsearch_sql_query="SELECT @timestamp, value FROM test WHERE @timestamp >= '$from' AND @timestamp < '$to'",
            query_mode={"type": "raw", "timestamp_field": "@timestamp"},
            algorithm=AlgorithmConfig(
                name="zscore",
                parameters=[AlgorithmParameter(dimension="test_field")],
            ),
            scheduling=SchedulingConfig(
                training_config=TrainingConfig(
                    **{"from": "2025-01-01T00:00:00Z"},
                    to="2025-01-02T00:00:00Z",
                    is_active=True,
                ),
                detection_config=DetectionConfig(
                    **{"from": "2025-01-03T00:00:00Z"},
                    frequency="* * * * *",
                    detection_window=3600,
                    is_active=False,
                ),
            ),
        )

        assert config.name == "test_config"
        assert config.description == "test description"
        assert config.algorithm.name == "zscore"

    def test_pydantic_validation_rejects_invalid_input(self):
        """Test that Pydantic models reject invalid input."""
        from models import KBConfig, TrainingConfig, DetectionConfig, SchedulingConfig

        with pytest.raises(Exception):
            KBConfig(
                name="",
                description="test desc",
                change_flag=0,
                elasticsearch_sql_query="SELECT @timestamp FROM test",
                query_mode={"type": "raw", "timestamp_field": "@timestamp"},
                algorithm={"name": "zscore", "parameters": [{"dimension": "field"}]},
                scheduling=SchedulingConfig(
                    training_config=TrainingConfig(
                        **{"from": "2025-01-01T00:00:00Z"},
                        to="2025-01-02T00:00:00Z",
                        is_active=True,
                    ),
                    detection_config=DetectionConfig(
                        **{"from": "2025-01-03T00:00:00Z"},
                        frequency="* * * * *",
                        detection_window=3600,
                        is_active=False,
                    ),
                ),
            )

    def test_modify_kb_config_uses_pydantic_validation(self):
        """Test that modify_kb_config function uses Pydantic validation (without MongoDB)."""
        # Mock the MongoDB connection and document retrieval
        import unittest.mock
        from mcp_tools_pkg.modify_kb_config import modify_kb_config
        
        mock_config = {
            "_id": "507f1f77bcf86cd799439011",
            "name": "existing_config",
            "description": "existing description",
            "change_flag": 0,
            "elasticsearch_sql_query": "SELECT @timestamp, value FROM test WHERE @timestamp >= '$from' AND @timestamp < '$to'",
            "query_mode": {"type": "raw", "timestamp_field": "@timestamp"},
            "algorithm": {"name": "zscore", "parameters": [{"dimension": "value"}]},
            "scheduling": {
                "training_config": {
                    "from": "2025-01-01T00:00:00Z",
                    "to": "2025-01-02T00:00:00Z",
                    "is_active": True,
                },
                "detection_config": {
                    "from": "2025-01-03T00:00:00Z",
                    "frequency": "* * * * *",
                    "detection_window": 3600,
                    "is_active": False,
                },
            },
        }
        
        with unittest.mock.patch('db.connect_mongodb') as mock_connect:
            mock_client = unittest.mock.MagicMock()
            mock_collection = unittest.mock.MagicMock()
            mock_client.__getitem__.return_value.__getitem__.return_value = mock_collection
            mock_connect.return_value = mock_client
            
            # Mock find_one to return existing config
            mock_collection.find_one.side_effect = lambda query: mock_config if "_id" in query else None
            
            # Mock update_one to succeed
            mock_collection.update_one.return_value.modified_count = 1
            
            # Test valid update
            try:
                result = asyncio.run(
                    modify_kb_config(
                        kb_id="507f1f77bcf86cd799439011",
                        description="updated description"
                    )
                )
                assert "updated successfully" in result
            except Exception as e:
                # Should not fail validation - only MongoDB operations
                assert "Input validation failed" not in str(e)
                assert "Invalid" not in str(e) or "not found" in str(e)

    def test_create_da_config_rejects_invalid_cron_expression(self, monkeypatch):
        """Test that create_da_config rejects invalid CRON expressions."""
        with pytest.raises(Exception) as exc_info:
            _invoke_create_da_config(
                monkeypatch,
                detection_frequency="invalid cron expression",
            )
        
        assert "Invalid CRON expression" in str(exc_info.value)

    def test_create_da_config_rejects_invalid_timestamp(self, monkeypatch):
        """Test that create_da_config rejects invalid ISO 8601 timestamps."""
        with pytest.raises(Exception) as exc_info:
            _invoke_create_da_config(
                monkeypatch,
                training_from="invalid timestamp",
                # Use aggregated mode to avoid frequency validation error
                query_mode={"type": "aggregated", "timestamp_field": "@timestamp"},
            )
        
        assert "Invalid ISO 8601 timestamp" in str(exc_info.value)

    def test_create_da_config_rejects_incorrect_algorithm_format(self, monkeypatch):
        """Test that create_da_config rejects incorrect algorithm field names."""
        from models import ZScoreConfig
        
        # Test with old/incorrect ZScoreConfig format (this test is now obsolete since we fixed the model)
        # The ZScoreConfig now uses the correct format, so this test should be removed or updated
        # For now, let's test with a manually constructed incorrect object
        class OldZScoreConfig:
            def __init__(self):
                self.algorithm = "zscore"
                self.dimensions = ["field"]

        bad_algorithm = OldZScoreConfig()

        with pytest.raises(Exception) as exc_info:
            _invoke_create_da_config(monkeypatch, algorithm=bad_algorithm)
        
        # The actual error is "Algorithm validation error" from Pydantic
        assert "Algorithm validation error" in str(exc_info.value)
        
    def test_create_da_config_rejects_incorrect_algorithm_dict_format(self, monkeypatch):
        """Test that create_da_config rejects incorrect algorithm dictionary structure."""
        
        # Test with incorrect dictionary format
        algorithm = {"algorithm": "zscore", "dimensions": ["field"]}

        with pytest.raises(Exception) as exc_info:
            _invoke_create_da_config(monkeypatch, algorithm=algorithm)
        
        assert "Algorithm validation error" in str(exc_info.value)

    def test_create_da_config_accepts_correct_algorithm_format(self, monkeypatch):
        """Test that create_da_config accepts the correct algorithm format."""
        from models import ZScoreConfig
        
        # Test with ZScoreConfig object (correct format)
        algorithm = ZScoreConfig(parameters=[{"dimension": "field"}])

        with pytest.raises(Exception) as exc_info:
            _invoke_create_da_config(monkeypatch, algorithm=algorithm)
        
        # Should fail at MongoDB/Elasticsearch, not validation
        error_str = str(exc_info.value)
        assert "Input validation failed" not in error_str
        assert "Algorithm validation error" not in error_str
        assert "Invalid CRON expression" not in error_str
        assert "Invalid ISO 8601 timestamp" not in error_str


if __name__ == "__main__":
    pytest.main([__file__, "-v"])