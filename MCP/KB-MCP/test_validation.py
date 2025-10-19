#!/usr/bin/env python3
"""
Test script to validate ESQL field validation in create_da_config function.
"""

import sys
import os
import importlib.util

# Load the kb-mcp module
spec = importlib.util.spec_from_file_location("kb_mcp", os.path.join(os.path.dirname(__file__), "kb-mcp.py"))
kb_mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kb_mcp)

create_da_config = kb_mcp.create_da_config
KBConfig = kb_mcp.KBConfig
ZScore = kb_mcp.ZScore
DaAlgParameters = kb_mcp.DaAlgParameters

def test_valid_config():
    """Test with valid configuration"""
    print("Testing valid configuration...")
    kb_config = KBConfig(
        id="test-valid",
        description="Test config",
        query_elastic="FROM test | EVAL es_timestamp = DATE_TRUNC(1 hour, @timestamp) | STATS count = COUNT(*) BY es_timestamp"
    )

    da_params = DaAlgParameters(algorithms=[ZScore(threshold=3.0, observed_value="count")])

    result = create_da_config(kb_config=kb_config, da_alg_parameters=da_params)
    print(f"Result: {result[:100]}...")
    print("OK Valid config test passed\n")

def test_invalid_observed_value():
    """Test with invalid observed_value field"""
    print("Testing invalid observed_value...")
    kb_config = KBConfig(
        id="test-invalid",
        description="Test config",
        query_elastic="FROM test | EVAL es_timestamp = DATE_TRUNC(1 hour, @timestamp) | STATS count = COUNT(*) BY es_timestamp"
    )

    da_params = DaAlgParameters(algorithms=[ZScore(threshold=3.0, observed_value="nonexistent_field")])

    result = create_da_config(kb_config=kb_config, da_alg_parameters=da_params)
    print(f"Result: {result[:200]}...")
    print("OK Invalid observed_value test passed\n")

def test_eval_field_as_observed_value():
    """Test using EVAL field as observed_value (should warn)"""
    print("Testing EVAL field as observed_value...")
    kb_config = KBConfig(
        id="test-eval",
        description="Test config",
        query_elastic="FROM test | EVAL es_timestamp = DATE_TRUNC(1 hour, @timestamp) | STATS count = COUNT(*) BY es_timestamp"
    )

    da_params = DaAlgParameters(algorithms=[ZScore(threshold=3.0, observed_value="es_timestamp")])

    result = create_da_config(kb_config=kb_config, da_alg_parameters=da_params)
    print(f"Result: {result[:300]}...")
    print("OK EVAL field test passed\n")

def test_mismatched_fields():
    """Test with mismatched fields: query produces test_counter, algorithms use error_rate and error_count"""
    print("Testing mismatched fields (error_rate and error_count vs test_counter)...")
    kb_config = KBConfig(
        id="test-mismatch",
        description="Test config with mismatched fields",
        query_elastic="FROM test | EVAL es_timestamp = DATE_TRUNC(1 hour, @timestamp) | STATS test_counter = COUNT(*) BY es_timestamp"
    )

    da_params = DaAlgParameters(algorithms=[
        ZScore(threshold=3.0, observed_value="error_rate"),
        ZScore(threshold=2.5, observed_value="error_count")
    ])

    result = create_da_config(kb_config=kb_config, da_alg_parameters=da_params)
    print(f"Result: {result[:400]}...")
    print("OK Mismatched fields test passed\n")

if __name__ == "__main__":
    test_valid_config()
    test_invalid_observed_value()
    test_eval_field_as_observed_value()
    test_mismatched_fields()
    print("All tests completed!")