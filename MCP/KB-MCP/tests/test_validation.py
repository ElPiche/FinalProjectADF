# test_validation.py - Unit tests for validation functions

import sys
import os
import pytest

# Ensure package root (KB-MCP) is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from validation import (
    extract_sql_output_fields,
    extract_sql_select_fields,
    validate_algorithms,
    validate_window_size,
)
from utils import stderr_print

def test_extract_sql_output_fields():
    """Test extraction of output fields from SQL queries."""
    # Simple SELECT
    query1 = "SELECT field1, field2 FROM table WHERE condition"
    result1 = extract_sql_output_fields(query1)
    assert result1 == ['field1', 'field2'], f"Expected ['field1', 'field2'], got {result1}"

    # SELECT with aliases
    query2 = "SELECT COUNT(*) as count, AVG(field) as avg_val FROM table"
    result2 = extract_sql_output_fields(query2)
    assert result2 == ['avg_val', 'count'], f"Expected ['avg_val', 'count'], got {result2}"

    # SELECT with functions
    query3 = "SELECT MAX(price) as max_price, MIN(price) as min_price FROM products"
    result3 = extract_sql_output_fields(query3)
    assert result3 == ['max_price', 'min_price'], f"Expected ['max_price', 'min_price'], got {result3}"

    # No SELECT clause
    query4 = "FROM table WHERE condition"
    result4 = extract_sql_output_fields(query4)
    assert result4 == [], f"Expected [], got {result4}"

    stderr_print("PASS: test_extract_sql_output_fields")

def test_extract_sql_select_fields():
    """Test extraction of select fields from SQL queries."""
    # Simple SELECT
    query1 = "SELECT field1, field2 FROM table WHERE condition"
    result1 = extract_sql_select_fields(query1)
    assert result1 == ['field1', 'field2'], f"Expected ['field1', 'field2'], got {result1}"

    # SELECT with aliases
    query2 = "SELECT COUNT(*) as count, AVG(field) as avg_val FROM table"
    result2 = extract_sql_select_fields(query2)
    assert result2 == ['avg_val', 'count'], f"Expected ['avg_val', 'count'], got {result2}"

    # SELECT with functions
    query3 = "SELECT MAX(price) as max_price, MIN(price) as min_price FROM products"
    result3 = extract_sql_select_fields(query3)
    assert result3 == ['max_price', 'min_price'], f"Expected ['max_price', 'min_price'], got {result3}"

    # No SELECT clause
    query4 = "FROM table WHERE condition"
    result4 = extract_sql_select_fields(query4)
    assert result4 == [], f"Expected [], got {result4}"

    stderr_print("PASS: test_extract_sql_select_fields")

def test_validate_algorithms():
    """Test validation for both singular and legacy algorithm payloads."""

    # Valid singular algorithm dict
    valid_algorithm = {
        "name": "zscore",
        "parameters": [
            {"dimension": "field1"},
            {"dimension": "field2"},
        ],
    }
    assert validate_algorithms(valid_algorithm) == []

    # Legacy list format still supported
    legacy_algorithms = [
        {
            "alg_name": "zscore",
            "alg_parameters": [{"dimension": "field1"}],
        }
    ]
    assert validate_algorithms(legacy_algorithms) == []

    # Missing algorithm payload entirely
    payload_none = validate_algorithms(None)
    assert payload_none and "cannot be empty" in payload_none[0]

    # Empty list
    payload_empty = validate_algorithms([])
    assert payload_empty and "list cannot be empty" in payload_empty[0]

    # Unsupported algorithm name
    invalid_type = [{"name": "invalid", "parameters": [{"dimension": "field1"}]}]
    errors_invalid = validate_algorithms(invalid_type)
    assert errors_invalid and "not supported" in errors_invalid[0]

    # Missing name
    missing_name = [{"parameters": [{"dimension": "field1"}]}]
    errors_missing = validate_algorithms(missing_name)
    assert errors_missing and "missing algorithm name" in errors_missing[0]

    # Missing parameters
    missing_params = [{"name": "zscore"}]
    errors_missing_params = validate_algorithms(missing_params)
    assert errors_missing_params and "parameters must be a list" in errors_missing_params[0]

    # Invalid parameter type
    invalid_params_type = [{"name": "zscore", "parameters": "not_a_list"}]
    errors_invalid_params = validate_algorithms(invalid_params_type)
    assert errors_invalid_params and "parameters must be a list" in errors_invalid_params[0]

    # Missing dimension entry
    missing_dimension = [{"name": "zscore", "parameters": [{}]}]
    errors_missing_dim = validate_algorithms(missing_dimension)
    assert errors_missing_dim and "missing dimension" in errors_missing_dim[0]

    stderr_print("PASS: test_validate_algorithms")


def test_validate_window_size_valid_no_warning():
    result = validate_window_size(3600, "training")
    assert result["valid"] is True
    assert result["warning"] is None


def test_validate_window_size_too_small():
    with pytest.raises(ValueError):
        validate_window_size(0, "training")


def test_validate_window_size_non_integer():
    with pytest.raises(ValueError):
        validate_window_size(3.5, "detection")


def test_validate_window_size_large_warning(monkeypatch):
    import validation as validation_module

    monkeypatch.setitem(validation_module.VALIDATION_CONSTANTS, "LARGE_WINDOW_THRESHOLD_DAYS", 1)
    result = validation_module.validate_window_size(200000, "training")
    assert result["warning"] is not None


if __name__ == "__main__":
    test_extract_sql_output_fields()
    test_extract_sql_select_fields()
    test_validate_algorithms()
    stderr_print("All validation tests passed!")