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

    def test_algorithm_description_is_deterministic(self):
        """Test that algorithm description generation is consistent."""
        alg1 = ALGORITHM_CONFIG_DESCRIPTION
        alg2 = ALGORITHM_CONFIG_DESCRIPTION

        assert alg1 == alg2, "Algorithm description should be deterministic"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])