# test_validation.py - Unit tests for validation functions

import sys
import os

# Ensure package root (KB-MCP) is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from validation import extract_sql_output_fields, extract_sql_select_fields, validate_algorithms

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

    print("PASS: test_extract_sql_output_fields")

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

    print("PASS: test_extract_sql_select_fields")

def test_validate_algorithms():
    """Test validation of algorithms array."""
    # Valid algorithms
    valid_algorithms = [
        {
            "alg_name": "zscore",
            "alg_parameters": [
                {"dimension": "field1"},
                {"dimension": "field2"}
            ]
        }
    ]
    errors = validate_algorithms(valid_algorithms)
    assert errors == [], f"Expected no errors, got {errors}"

    # Empty algorithms
    errors_empty = validate_algorithms([])
    assert len(errors_empty) == 1 and "cannot be empty" in errors_empty[0], f"Expected empty error, got {errors_empty}"

    # Invalid algorithm type
    invalid_type = [{"alg_name": "invalid", "alg_parameters": [{"dimension": "field1"}]}]
    errors_invalid = validate_algorithms(invalid_type)
    assert len(errors_invalid) == 1 and "not supported" in errors_invalid[0], f"Expected unsupported error, got {errors_invalid}"

    # Missing alg_name
    missing_name = [{"alg_parameters": [{"dimension": "field1"}]}]
    errors_missing = validate_algorithms(missing_name)
    assert len(errors_missing) == 1 and "missing alg_name" in errors_missing[0], f"Expected missing name error, got {errors_missing}"

    # Missing alg_parameters
    missing_params = [{"alg_name": "zscore"}]
    errors_missing_params = validate_algorithms(missing_params)
    assert len(errors_missing_params) == 1 and "missing alg_parameters" in errors_missing_params[0], f"Expected missing params error, got {errors_missing_params}"

    # Invalid alg_parameters type
    invalid_params_type = [{"alg_name": "zscore", "alg_parameters": "not_a_list"}]
    errors_invalid_params = validate_algorithms(invalid_params_type)
    assert len(errors_invalid_params) == 1 and "must be a list" in errors_invalid_params[0], f"Expected list error, got {errors_invalid_params}"

    # Missing dimension in parameter
    missing_dimension = [{"alg_name": "zscore", "alg_parameters": [{}]}]
    errors_missing_dim = validate_algorithms(missing_dimension)
    assert len(errors_missing_dim) == 1 and "missing dimension" in errors_missing_dim[0], f"Expected missing dimension error, got {errors_missing_dim}"

    print("PASS: test_validate_algorithms")

if __name__ == "__main__":
    test_extract_sql_output_fields()
    test_extract_sql_select_fields()
    test_validate_algorithms()
    print("All validation tests passed!")
