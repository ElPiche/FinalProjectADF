#!/usr/bin/env python3
"""
Basic unit tests for KB-MCP models.
Run with: python -m tests.test_models (from MCP/KB-MCP directory) or `python tests/test_models.py`
"""

import sys
import os
# Ensure package root (KB-MCP) is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime
from models import KBConfig, ZScoreConfig, AlgorithmConfig, CRON
from utils import stderr_print


def test_valid_kb_config():
    """Test creating a valid KBConfig."""
    config_data = {
        "name": "Test Configuration",
        "description": "Test description",
        "change_flag": 0,
        "elasticsearch_sql_query": "SELECT @timestamp, field1 FROM test WHERE @timestamp >= '$from' AND @timestamp < '$to'",
        "query_mode": {"type": "raw", "timestamp_field": "@timestamp"},
        "scheduling": {
            "training_config": {
                "from": "2025-01-01T00:00:00Z",
                "to": "2025-01-02T00:00:00Z",
                "is_active": True
            },
            "detection_config": {
                "from": "2025-01-02T00:00:00Z",
                "frequency": "*/15 * * * *",
                "detection_window": 3600,
                "is_active": False
            }
        },
        "algorithm": {
            "name": "zscore",
            "parameters": [
                {"dimension": "field1"}
            ]
        }
    }

    config = KBConfig(**config_data)
    assert config.name == "Test Configuration"
    assert config.description == "Test description"
    assert config.change_flag == 0
    assert config.algorithm.name == "zscore"
    stderr_print("PASS: test_valid_kb_config")


def test_invalid_kb_config_empty_name():
    """Test KBConfig rejects empty name."""
    try:
        KBConfig(
            name="",
            description="Test",
            change_flag=0,
            elasticsearch_sql_query="SELECT @timestamp FROM test WHERE @timestamp >= '$from' AND @timestamp < '$to'",
            query_mode={"type": "raw", "timestamp_field": "@timestamp"},
            algorithm={"name": "zscore", "parameters": [{"dimension": "field1"}]},
            scheduling={
                "training_config": {
                    "from": "2025-01-01T00:00:00Z",
                    "to": "2025-01-02T00:00:00Z",
                    "is_active": True,
                },
                "detection_config": {
                    "from": "2025-01-02T00:00:00Z",
                    "frequency": "*/10 * * * *",
                    "detection_window": 3600,
                    "is_active": True,
                },
            },
        )
        assert False, "Should have raised ValueError"
    except ValueError:
        stderr_print("PASS: test_invalid_kb_config_empty_name")


def test_invalid_kb_config_empty_description():
    """Test KBConfig rejects empty description."""
    try:
        KBConfig(
            name="Test",
            description="",
            change_flag=0,
            elasticsearch_sql_query="SELECT @timestamp FROM test WHERE @timestamp >= '$from' AND @timestamp < '$to'",
            query_mode={"type": "raw", "timestamp_field": "@timestamp"},
            algorithm={"name": "zscore", "parameters": [{"dimension": "field1"}]},
            scheduling={
                "training_config": {
                    "from": "2025-01-01T00:00:00Z",
                    "to": "2025-01-02T00:00:00Z",
                    "is_active": True,
                },
                "detection_config": {
                    "from": "2025-01-02T00:00:00Z",
                    "frequency": "*/10 * * * *",
                    "detection_window": 3600,
                    "is_active": True,
                },
            },
        )
        assert False, "Should have raised ValueError"
    except ValueError:
        stderr_print("PASS: test_invalid_kb_config_empty_description")


def test_valid_zscore_config():
    """Test creating a valid ZScoreConfig."""
    config = ZScoreConfig(
        parameters=[{"dimension": "field1"}, {"dimension": "field2"}]
    )
    assert config.name == "zscore"
    assert [param.dimension for param in config.parameters] == ["field1", "field2"]
    stderr_print("PASS: test_valid_zscore_config")


def test_zscore_config_single_dimension():
    """Test ZScoreConfig with single dimension."""
    config = ZScoreConfig(parameters=[{"dimension": "field1"}])
    assert [param.dimension for param in config.parameters] == ["field1"]
    stderr_print("PASS: test_zscore_config_single_dimension")


def test_valid_cron():
    """Test valid CRON expressions."""
    valid_crons = [
        "*/15 * * * *",
        "0 * * * *",
        "0 0 * * *",
        "0 0 1 * *"
    ]

    for cron_expr in valid_crons:
        cron = CRON(cron_expr)
        assert str(cron) == cron_expr
    stderr_print("PASS: test_valid_cron")


def test_invalid_cron():
    """Test invalid CRON expressions."""
    invalid_crons = [
        "invalid",
        "*/15 * * *",
        "60 * * * *",
        "not a cron expression"
    ]

    for cron_expr in invalid_crons:
        try:
            CRON(cron_expr)
            assert False, f"Should have raised ValueError for {cron_expr}"
        except ValueError:
            pass
    stderr_print("PASS: test_invalid_cron")


if __name__ == "__main__":
    # Run basic tests if executed directly
    stderr_print("Running basic model tests...")

    test_valid_kb_config()
    test_invalid_kb_config_empty_name()
    test_invalid_kb_config_empty_description()
    test_valid_zscore_config()
    test_zscore_config_single_dimension()
    test_valid_cron()
    test_invalid_cron()

    stderr_print("All basic tests completed successfully!")