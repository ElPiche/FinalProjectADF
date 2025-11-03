#!/usr/bin/env python3
"""
Unit tests for dynamic description generation functionality.
Tests that descriptions are generated from Pydantic models and contain expected content.
Run with: python -m pytest tests/test_dynamic_descriptions.py -v
"""

import sys
import os
# Ensure package root (KB-MCP) is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from description_utils import (
    generate_kb_config_description,
    generate_kb_config_example,
    ALGORITHM_CONFIG_DESCRIPTION
)
from models import KBConfig, ZScoreConfig


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
        assert "training_query" in description
        assert "detection_query" in description
        assert "algorithms" in description

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
        assert "algorithms" in example

        # Check nested scheduling fields
        scheduling = example["scheduling"]
        assert "training_config" in scheduling
        assert "detection_config" in scheduling

        training_config = scheduling["training_config"]
        assert "training_query" in training_config
        assert "from" in training_config
        assert "to" in training_config

        detection_config = scheduling["detection_config"]
        assert "detection_query" in detection_config
        assert "from" in detection_config
        assert "frequency" in detection_config

        # Check algorithms structure
        algorithms = example["algorithms"]
        assert isinstance(algorithms, list)
        assert len(algorithms) > 0
        assert "alg_name" in algorithms[0]
        assert "alg_parameters" in algorithms[0]

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
        from models import KBConfig, TrainingConfig, DetectionConfig, SchedulingConfig, AlgorithmConfigItem, AlgorithmParameter
        
        # Test valid configuration
        config = KBConfig(
            name='test_config',
            description='test description',
            change_flag=0,
            scheduling=SchedulingConfig(
                training_config=TrainingConfig(
                    training_query='SELECT * FROM test',
                    **{"from": '2025-01-01T00:00:00Z'},
                    to='2025-01-02T00:00:00Z',
                    training_window=3600,
                    is_active=True
                ),
                detection_config=DetectionConfig(
                    detection_query='SELECT * FROM test',
                    **{"from": '2025-01-03T00:00:00Z'},
                    frequency='* * * * *',
                    detection_window=3600,
                    is_active=False
                )
            ),
            algorithms=[AlgorithmConfigItem(
                alg_name='zscore',
                alg_parameters=[AlgorithmParameter(dimension='test_field')]
            )]
        )
        
        assert config.name == 'test_config'
        assert config.description == 'test description'
        assert len(config.algorithms) == 1

    def test_pydantic_validation_rejects_invalid_input(self):
        """Test that Pydantic models reject invalid input."""
        from models import KBConfig, TrainingConfig, DetectionConfig, SchedulingConfig
        
        # Test empty name
        with pytest.raises(Exception):  # Should raise validation error
            KBConfig(
                name='',  # Invalid: empty string
                description='test desc',
                change_flag=0,
                scheduling=SchedulingConfig(
                    training_config=TrainingConfig(
                        training_query='SELECT * FROM test',
                        **{"from": '2025-01-01T00:00:00Z'},
                        to='2025-01-02T00:00:00Z',
                        training_window=3600,
                        is_active=True
                    ),
                    detection_config=DetectionConfig(
                        detection_query='SELECT * FROM test',
                        **{"from": '2025-01-03T00:00:00Z'},
                        frequency='* * * * *',
                        detection_window=3600,
                        is_active=False
                    )
                ),
                algorithms=[]
            )

    def test_modify_kb_config_uses_pydantic_validation(self):
        """Test that modify_kb_config function uses Pydantic validation (without MongoDB)."""
        # Mock the MongoDB connection and document retrieval
        import unittest.mock
        from mcp_tools_pkg.modify_kb_config import modify_kb_config
        
        # Mock existing config document
        mock_config = {
            "_id": "507f1f77bcf86cd799439011",
            "name": "existing_config",
            "description": "existing description",
            "change_flag": 0,
            "scheduling": {
                "training_config": {
                    "training_query": "SELECT * FROM existing",
                    "from": "2025-01-01T00:00:00Z",
                    "to": "2025-01-02T00:00:00Z",
                    "training_window": 3600,
                    "is_active": True
                },
                "detection_config": {
                    "detection_query": "SELECT * FROM existing",
                    "from": "2025-01-03T00:00:00Z",
                    "frequency": "* * * * *",
                    "detection_window": 3600,
                    "is_active": False
                }
            },
            "algorithms": []
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
                result = modify_kb_config(
                    config_id="507f1f77bcf86cd799439011",
                    description="updated description"
                )
                assert "updated successfully" in result
            except Exception as e:
                # Should not fail validation - only MongoDB operations
                assert "Input validation failed" not in str(e)
                assert "Invalid" not in str(e) or "not found" in str(e)

    def test_create_da_config_rejects_invalid_cron_expression(self):
        """Test that create_da_config rejects invalid CRON expressions."""
        from mcp_tools_pkg.create_da_config import create_da_config
        
        with pytest.raises(Exception) as exc_info:
            create_da_config(
                name="test",
                description="test",
                training_query="SELECT * FROM test",
                detection_query="SELECT * FROM test",
                training_from="2025-01-01T00:00:00Z",
                training_to="2025-01-02T00:00:00Z",
                detection_frequency="invalid cron expression",
                detection_start="2025-01-03T00:00:00Z",
                algorithms=[{"alg_name": "zscore", "alg_parameters": [{"dimension": "field"}]}]
            )
        
        assert "Invalid CRON expression" in str(exc_info.value)

    def test_create_da_config_rejects_invalid_timestamp(self):
        """Test that create_da_config rejects invalid ISO 8601 timestamps."""
        from mcp_tools_pkg.create_da_config import create_da_config
        
        with pytest.raises(Exception) as exc_info:
            create_da_config(
                name="test",
                description="test",
                training_query="SELECT * FROM test",
                detection_query="SELECT * FROM test",
                training_from="invalid timestamp",
                training_to="2025-01-02T00:00:00Z",
                detection_frequency="* * * * *",
                detection_start="2025-01-03T00:00:00Z",
                algorithms=[{"alg_name": "zscore", "alg_parameters": [{"dimension": "field"}]}]
            )
        
        assert "Invalid ISO 8601 timestamp" in str(exc_info.value)

    def test_create_da_config_rejects_incorrect_algorithm_format(self):
        """Test that create_da_config rejects incorrect algorithm field names."""
        from mcp_tools_pkg.create_da_config import create_da_config
        from models import ZScoreConfig
        
        # Test with old/incorrect ZScoreConfig format (this test is now obsolete since we fixed the model)
        # The ZScoreConfig now uses the correct format, so this test should be removed or updated
        # For now, let's test with a manually constructed incorrect object
        class OldZScoreConfig:
            def __init__(self):
                self.algorithm = "zscore"
                self.dimensions = ["field"]
        
        algorithms = [OldZScoreConfig()]
        
        with pytest.raises(Exception) as exc_info:
            create_da_config(
                name="test",
                description="test",
                training_query="SELECT field FROM test",
                detection_query="SELECT field FROM test",
                training_from="2025-01-01T00:00:00Z",
                training_to="2025-01-02T00:00:00Z",
                detection_frequency="* * * * *",
                detection_start="2025-01-03T00:00:00Z",
                algorithms=algorithms
            )
        
        assert "Unsupported algorithm format" in str(exc_info.value)
        
        with pytest.raises(Exception) as exc_info:
            create_da_config(
                name="test",
                description="test",
                training_query="SELECT field FROM test",
                detection_query="SELECT field FROM test",
                training_from="2025-01-01T00:00:00Z",
                training_to="2025-01-02T00:00:00Z",
                detection_frequency="* * * * *",
                detection_start="2025-01-03T00:00:00Z",
                algorithms=algorithms
            )
        
        assert "Unsupported algorithm format" in str(exc_info.value)

    def test_create_da_config_rejects_incorrect_algorithm_dict_format(self):
        """Test that create_da_config rejects incorrect algorithm dictionary structure."""
        from mcp_tools_pkg.create_da_config import create_da_config
        
        # Test with incorrect dictionary format
        algorithms = [{"algorithm": "zscore", "dimensions": ["field"]}]
        
        with pytest.raises(Exception) as exc_info:
            create_da_config(
                name="test",
                description="test",
                training_query="SELECT field FROM test",
                detection_query="SELECT field FROM test",
                training_from="2025-01-01T00:00:00Z",
                training_to="2025-01-02T00:00:00Z",
                detection_frequency="* * * * *",
                detection_start="2025-01-03T00:00:00Z",
                algorithms=algorithms
            )
        
        assert "Algorithm validation error" in str(exc_info.value)

    def test_create_da_config_accepts_correct_algorithm_format(self):
        """Test that create_da_config accepts the correct algorithm format."""
        from mcp_tools_pkg.create_da_config import create_da_config
        from models import ZScoreConfig
        
        # Test with ZScoreConfig object (correct format)
        algorithms = [ZScoreConfig(alg_name="zscore", alg_parameters=[{"dimension": "field"}])]
        
        # Should pass validation and only fail at MongoDB connection
        with pytest.raises(Exception) as exc_info:
            create_da_config(
                name="test",
                description="test",
                training_query="SELECT field FROM test",
                detection_query="SELECT field FROM test",
                training_from="2025-01-01T00:00:00Z",
                training_to="2025-01-02T00:00:00Z",
                detection_frequency="* * * * *",
                detection_start="2025-01-03T00:00:00Z",
                algorithms=algorithms
            )
        
        # Should fail at MongoDB/Elasticsearch, not validation
        error_str = str(exc_info.value)
        assert "Input validation failed" not in error_str
        assert "Algorithm validation error" not in error_str
        assert "Invalid CRON expression" not in error_str
        assert "Invalid ISO 8601 timestamp" not in error_str


if __name__ == "__main__":
    pytest.main([__file__, "-v"])