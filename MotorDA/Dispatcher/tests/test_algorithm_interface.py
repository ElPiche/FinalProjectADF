"""Tests for Algorithm Interface - Protocol + Registry.

Tests the AnomalyAlgorithm protocol and algorithm registry.
"""

import pytest
from typing import Dict, Any, List
from MotorDA.Dispatcher.algorithm_interface import (
    AnomalyAlgorithm,
    ZScoreAlgorithm,
    ALGORITHM_REGISTRY,
    get_algorithm,
    is_algorithm_registered,
    list_algorithms,
    register_algorithm,
)


class TestZScoreAlgorithm:
    """Tests for ZScoreAlgorithm implementation."""
    
    def test_name_property(self):
        algo = ZScoreAlgorithm()
        assert algo.name == "zscore"
    
    def test_train_basic(self):
        algo = ZScoreAlgorithm()
        values = [10, 20, 30, 40, 50]
        result = algo.train(values)
        
        assert "mean" in result
        assert "std" in result
        assert "threshold" in result
        assert result["mean"] == 30.0
    
    def test_train_custom_percentile(self):
        algo = ZScoreAlgorithm()
        values = [10, 20, 30, 40, 50]
        result = algo.train(values, percentile=95.0)
        
        assert result["percentile"] == 95.0
    
    def test_detect_normal_value(self):
        algo = ZScoreAlgorithm()
        model = algo.train([10, 20, 30, 40, 50])
        result = algo.detect(30.0, model)
        
        assert result["is_anomaly"] is False
        assert "z_score" in result
    
    def test_detect_anomaly(self):
        algo = ZScoreAlgorithm()
        model = algo.train([10, 20, 30, 40, 50])
        result = algo.detect(1000.0, model)
        
        assert result["is_anomaly"] is True
    
    def test_detect_batch(self):
        algo = ZScoreAlgorithm()
        model = algo.train([10, 20, 30, 40, 50])
        results = algo.detect_batch([30.0, 1000.0, 25.0], model)
        
        assert len(results) == 3
        assert results[0]["is_anomaly"] is False
        assert results[1]["is_anomaly"] is True
        assert results[2]["is_anomaly"] is False
    
    def test_implements_protocol(self):
        algo = ZScoreAlgorithm()
        assert isinstance(algo, AnomalyAlgorithm)


class TestAlgorithmRegistry:
    """Tests for algorithm registry functions."""
    
    def test_zscore_in_registry(self):
        assert "zscore" in ALGORITHM_REGISTRY
    
    def test_get_algorithm_zscore(self):
        algo = get_algorithm("zscore")
        assert algo.name == "zscore"
    
    def test_get_algorithm_case_insensitive(self):
        algo_lower = get_algorithm("zscore")
        algo_upper = get_algorithm("ZSCORE")
        algo_mixed = get_algorithm("ZScore")
        
        assert algo_lower.name == algo_upper.name == algo_mixed.name
    
    def test_get_algorithm_unknown_raises(self):
        with pytest.raises(ValueError) as exc_info:
            get_algorithm("unknown_algo")
        assert "Unknown algorithm" in str(exc_info.value)
    
    def test_is_algorithm_registered_true(self):
        assert is_algorithm_registered("zscore") is True
        assert is_algorithm_registered("ZSCORE") is True
    
    def test_is_algorithm_registered_false(self):
        assert is_algorithm_registered("unknown") is False
    
    def test_list_algorithms(self):
        algos = list_algorithms()
        assert "zscore" in algos
        assert isinstance(algos, list)


class TestRegisterAlgorithm:
    """Tests for registering custom algorithms."""
    
    def test_register_new_algorithm(self):
        from dataclasses import dataclass
        
        @dataclass
        class MockAlgorithm:
            @property
            def name(self) -> str:
                return "mock_algo"
            
            def train(self, values: List[float], percentile: float = 99.5, **kwargs) -> Dict[str, Any]:
                return {"mean": sum(values) / len(values)}
            
            def detect(self, value: float, model: Dict[str, Any]) -> Dict[str, Any]:
                return {"is_anomaly": value > model["mean"] * 2}
            
            def detect_batch(self, values: List[float], model: Dict[str, Any]) -> List[Dict[str, Any]]:
                return [self.detect(v, model) for v in values]
        
        # Register mock algorithm
        mock = MockAlgorithm()
        register_algorithm(mock)
        
        # Verify it's registered
        assert is_algorithm_registered("mock_algo")
        
        # Verify we can get it
        retrieved = get_algorithm("mock_algo")
        assert retrieved.name == "mock_algo"
        
        # Clean up
        del ALGORITHM_REGISTRY["mock_algo"]


class TestProtocolCompliance:
    """Tests to verify ZScoreAlgorithm complies with AnomalyAlgorithm protocol."""
    
    def test_has_name_property(self):
        algo = ZScoreAlgorithm()
        assert hasattr(algo, "name")
        assert isinstance(algo.name, str)
    
    def test_has_train_method(self):
        algo = ZScoreAlgorithm()
        assert hasattr(algo, "train")
        assert callable(algo.train)
    
    def test_has_detect_method(self):
        algo = ZScoreAlgorithm()
        assert hasattr(algo, "detect")
        assert callable(algo.detect)
    
    def test_has_detect_batch_method(self):
        algo = ZScoreAlgorithm()
        assert hasattr(algo, "detect_batch")
        assert callable(algo.detect_batch)
    
    def test_train_returns_serializable_dict(self):
        algo = ZScoreAlgorithm()
        result = algo.train([1, 2, 3, 4, 5])
        
        # Should be JSON serializable
        import json
        json.dumps(result)  # Should not raise
    
    def test_detect_returns_dict_with_is_anomaly(self):
        algo = ZScoreAlgorithm()
        model = algo.train([1, 2, 3, 4, 5])
        result = algo.detect(3.0, model)
        
        assert "is_anomaly" in result
        assert isinstance(result["is_anomaly"], bool)


class TestEndToEnd:
    """End-to-end tests for algorithm interface usage."""
    
    def test_full_workflow(self):
        # Get algorithm from registry
        algo = get_algorithm("zscore")
        
        # Train
        training_data = [100, 105, 98, 102, 101, 99, 103, 97, 104, 100]
        model = algo.train(training_data, percentile=99.5)
        
        # Detect normal value
        normal_result = algo.detect(101.0, model)
        assert normal_result["is_anomaly"] is False
        
        # Detect anomaly
        anomaly_result = algo.detect(500.0, model)
        assert anomaly_result["is_anomaly"] is True
    
    def test_realistic_traffic_pattern(self):
        """Test with realistic traffic data."""
        import random
        random.seed(42)
        
        algo = get_algorithm("zscore")
        
        # Normal traffic pattern (mean ~1000, std ~50)
        normal_traffic = [1000 + random.gauss(0, 50) for _ in range(100)]
        model = algo.train(normal_traffic)
        
        # Normal value should not be anomaly
        normal_result = algo.detect(1025.0, model)
        assert normal_result["is_anomaly"] is False
        
        # Spike should be anomaly
        spike_result = algo.detect(2000.0, model)
        assert spike_result["is_anomaly"] is True
        
        # Crash should be anomaly
        crash_result = algo.detect(100.0, model)
        assert crash_result["is_anomaly"] is True
