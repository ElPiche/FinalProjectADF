# smoke_test.py - Basic smoke tests for KB-MCP modular refactor

import sys
import os
import subprocess
import time

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

def test_imports():
    """Test that all modules can be imported successfully."""
    try:
        import models
        import validation
        import db
        import mcp_tools
        import utils
        import instrumentation
        print("PASS: All modules imported successfully")
        return True
    except ImportError as e:
        print(f"FAIL: Import error - {e}")
        return False

def test_models():
    """Test basic model functionality."""
    try:
        from models import KBConfig, ZScoreConfig, CRON
        from validation import validate_algorithms

        # Test valid config
        config = KBConfig(
            name="Test Config",
            description="Test description",
            change_flag=0,
            scheduling={
                "training_config": {
                    "training_query": "SELECT * FROM test",
                    "from": "2025-01-01T00:00:00Z",
                    "to": "2025-01-02T00:00:00Z",
                    "training_window": 3600,
                    "is_active": True
                },
                "detection_config": {
                    "detection_query": "SELECT * FROM test",
                    "from": "2025-01-02T00:00:00Z",
                    "frequency": "*/15 * * * *",
                    "detection_window": 3600,
                    "is_active": False
                }
            },
            algorithms=[{
                "alg_name": "zscore",
                "alg_parameters": [{"dimension": "test_field"}]
            }]
        )

        # Test CRON validation
        cron = CRON("*/15 * * * *")

        # Test algorithm validation
        errors = validate_algorithms([{
            "alg_name": "zscore",
            "alg_parameters": [{"dimension": "test_field"}]
        }])

        if errors:
            print(f"FAIL: Algorithm validation failed - {errors}")
            return False

        print("PASS: Models and validation work correctly")
        return True
    except Exception as e:
        print(f"FAIL: Model test error - {e}")
        return False

def test_validation_functions():
    """Test validation functions."""
    try:
        from validation import extract_sql_output_fields, validate_algorithms

        # Test SQL field extraction
        fields = extract_sql_output_fields("SELECT field1, field2 FROM table")
        if fields != ['field1', 'field2']:
            print(f"FAIL: SQL field extraction failed - got {fields}")
            return False

        # Test algorithm validation
        errors = validate_algorithms([])
        if not errors or "cannot be empty" not in errors[0]:
            print(f"FAIL: Algorithm validation failed - got {errors}")
            return False

        print("PASS: Validation functions work correctly")
        return True
    except Exception as e:
        print(f"FAIL: Validation test error - {e}")
        return False

def test_db_connections():
    """Test database connection functions (without actual connections)."""
    try:
        from db import connect_mongodb, connect_elasticsearch, safe_close_client

        # Test that functions exist and can be called (they will fail due to no actual DBs)
        # We just want to ensure no import errors
        print("PASS: Database connection functions available")
        return True
    except Exception as e:
        print(f"FAIL: Database connection test error - {e}")
        return False

def test_instrumentation():
    """Test instrumentation decorators."""
    try:
        from instrumentation import timed, watch_threshold

        @timed
        def test_function():
            return "test"

        result = test_function()
        if result != "test":
            print(f"FAIL: Timed decorator failed - got {result}")
            return False

        print("PASS: Instrumentation decorators work correctly")
        return True
    except Exception as e:
        print(f"FAIL: Instrumentation test error - {e}")
        return False

def test_mcp_tools():
    """Test MCP tool imports and basic structure."""
    try:
        import mcp_tools
        # Check that mcp server instance exists
        if not hasattr(mcp_tools, 'mcp'):
            print("FAIL: MCP server instance not found")
            return False

        print("PASS: MCP tools module loaded correctly")
        return True
    except Exception as e:
        print(f"FAIL: MCP tools test error - {e}")
        return False

def run_smoke_tests():
    """Run all smoke tests."""
    print("Running KB-MCP smoke tests...")
    print("=" * 50)

    tests = [
        test_imports,
        test_models,
        test_validation_functions,
        test_db_connections,
        test_instrumentation,
        test_mcp_tools
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"FAIL: {test.__name__} crashed - {e}")

    print("=" * 50)
    print(f"Smoke tests completed: {passed}/{total} passed")

    if passed == total:
        print("SUCCESS: All smoke tests passed!")
        return True
    else:
        print("FAILURE: Some smoke tests failed!")
        return False

if __name__ == "__main__":
    success = run_smoke_tests()
    sys.exit(0 if success else 1)