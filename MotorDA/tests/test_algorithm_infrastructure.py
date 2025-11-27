"""Point-to-Point Test for Algorithm Infrastructure.

This test verifies the complete flow:
1. BaseAlgorithm abstract class
2. ZScoreAlgorithm implementation
3. Algorithm registry lookup
4. TrainingOrchestrator with registry
5. DetectionOrchestrator with registry

Run with:
    cd MotorDA
    python -m pytest tests/test_algorithm_infrastructure.py -v
    
Or directly:
    python tests/test_algorithm_infrastructure.py
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime, timezone
from typing import Dict, Any, List

import pandas as pd
import numpy as np


class TestBaseAlgorithm:
    """Test the base algorithm abstract class."""
    
    def test_detection_mode_enum(self):
        """Verify DetectionMode enum has required values."""
        from base_algorithm import DetectionMode
        
        assert DetectionMode.POINT.value == "point"
        assert DetectionMode.SERIES.value == "series"
        assert DetectionMode.BATCH.value == "batch"
    
    def test_bucket_mode_enum(self):
        """Verify BucketMode enum has required values."""
        from base_algorithm import BucketMode
        
        assert BucketMode.SEGMENT.value == "segment"
        assert BucketMode.FEATURE.value == "feature"
        assert BucketMode.METADATA_ONLY.value == "metadata_only"
    
    def test_training_result_to_dict(self):
        """Verify TrainingResult serializes correctly."""
        from base_algorithm import TrainingResult
        
        result = TrainingResult(
            baseline={"mean": 100.0, "std": 10.0, "threshold": 3.0},
            data_points=50,
            sufficient_data=True,
            metadata={"bucket_key": "workday_09"}
        )
        
        d = result.to_dict()
        
        assert d["mean"] == 100.0
        assert d["std"] == 10.0
        assert d["threshold"] == 3.0
        assert d["data_points"] == 50
        assert d["sufficient_data"] == True
        assert d["_metadata"]["bucket_key"] == "workday_09"
    
    def test_detection_result_to_dict(self):
        """Verify DetectionResult serializes correctly."""
        from base_algorithm import DetectionResult
        
        result = DetectionResult(
            is_anomaly=True,
            algorithm_details={"z_score": 4.5, "threshold": 3.0},
            confidence=0.95
        )
        
        d = result.to_dict()
        
        assert d["is_anomaly"] == True
        assert d["z_score"] == 4.5
        assert d["threshold"] == 3.0
        assert d["confidence"] == 0.95


class TestZScoreAlgorithm:
    """Test the ZScoreAlgorithm implementation."""
    
    def test_class_attributes(self):
        """Verify ZScoreAlgorithm has correct class attributes."""
        from ZScore.algorithm import ZScoreAlgorithm
        from base_algorithm import DetectionMode, BucketMode
        
        algo = ZScoreAlgorithm()
        
        assert algo.name == "zscore"
        assert algo.display_name == "Z-Score"
        assert algo.detection_mode.value == DetectionMode.POINT.value
        assert algo.bucket_mode.value == BucketMode.SEGMENT.value
        assert algo.minimum_training_points == 3
    
    def test_train_with_normal_data(self):
        """Verify training produces correct baseline."""
        from ZScore.algorithm import ZScoreAlgorithm
        
        algo = ZScoreAlgorithm()
        
        # Create training data with known distribution
        data = [
            {"timestamp": f"2025-01-01T{i:02d}:00:00Z", "value": 100 + i}
            for i in range(20)
        ]
        
        result = algo.train(data, bucket_key="test_bucket")
        
        assert result.sufficient_data == True
        assert result.data_points == 20
        assert "mean" in result.baseline
        assert "std" in result.baseline
        assert "threshold" in result.baseline
        assert result.baseline["mean"] == pytest.approx(109.5, rel=0.01)  # (100+119)/2
    
    def test_train_with_insufficient_data(self):
        """Verify training handles insufficient data."""
        from ZScore.algorithm import ZScoreAlgorithm
        
        algo = ZScoreAlgorithm()
        
        # Only 2 data points (less than minimum_training_points=3)
        data = [
            {"timestamp": "2025-01-01T00:00:00Z", "value": 100},
            {"timestamp": "2025-01-01T01:00:00Z", "value": 110},
        ]
        
        result = algo.train(data)
        
        assert result.sufficient_data == False
        assert result.data_points == 2
    
    def test_train_with_empty_data(self):
        """Verify training handles empty data."""
        from ZScore.algorithm import ZScoreAlgorithm
        
        algo = ZScoreAlgorithm()
        result = algo.train([])
        
        assert result.sufficient_data == False
        assert result.data_points == 0
    
    def test_detect_normal_value(self):
        """Verify detection of normal values."""
        from ZScore.algorithm import ZScoreAlgorithm
        
        algo = ZScoreAlgorithm()
        
        baseline = {
            "mean": 100.0,
            "std": 10.0,
            "threshold": 3.0,
            "data_points": 100,
            "percentile": 99.5
        }
        
        # Value within 1 std - should NOT be anomaly
        result = algo.detect(value=105.0, baseline=baseline)
        
        assert result.is_anomaly == False
        assert "z_score" in result.algorithm_details
        assert result.algorithm_details["z_score"] == pytest.approx(0.5, rel=0.01)
    
    def test_detect_anomalous_value(self):
        """Verify detection of anomalous values."""
        from ZScore.algorithm import ZScoreAlgorithm
        
        algo = ZScoreAlgorithm()
        
        baseline = {
            "mean": 100.0,
            "std": 10.0,
            "threshold": 3.0,
            "data_points": 100,
            "percentile": 99.5
        }
        
        # Value 5 std away - should BE anomaly (z_score=5 > threshold=3)
        result = algo.detect(value=150.0, baseline=baseline)
        
        assert result.is_anomaly == True
        assert result.algorithm_details["z_score"] == pytest.approx(5.0, rel=0.01)
    
    def test_format_anomaly_text(self):
        """Verify anomaly text formatting."""
        from ZScore.algorithm import ZScoreAlgorithm
        
        algo = ZScoreAlgorithm()
        
        details = {"z_score": 4.5, "threshold": 3.0}
        
        text = algo.format_anomaly_text(value=150.0, details=details, bucket_key="workday_09")
        
        assert "4.50" in text
        assert "3.00" in text
        assert "workday" in text.lower() or "hour 09" in text
    
    def test_validate_config_valid(self):
        """Verify config validation with valid params."""
        from ZScore.algorithm import ZScoreAlgorithm
        
        algo = ZScoreAlgorithm()
        
        errors = algo.validate_config({"percentile": 99.5, "min_points": 5})
        
        assert errors == []
    
    def test_validate_config_invalid_percentile(self):
        """Verify config validation catches invalid percentile."""
        from ZScore.algorithm import ZScoreAlgorithm
        
        algo = ZScoreAlgorithm()
        
        errors = algo.validate_config({"percentile": 150})
        
        assert len(errors) > 0
        assert any("percentile" in e for e in errors)


class TestAlgorithmRegistry:
    """Test the algorithm registry."""
    
    def test_zscore_is_registered(self):
        """Verify ZScore is in the registry."""
        from algorithm_registry import is_algorithm_supported, get_algorithm
        
        assert is_algorithm_supported("zscore") == True
        assert is_algorithm_supported("ZSCORE") == True  # Case insensitive
        
        algo = get_algorithm("zscore")
        assert algo is not None
        assert algo.name == "zscore"
    
    def test_unknown_algorithm(self):
        """Verify unknown algorithms return None."""
        from algorithm_registry import is_algorithm_supported, get_algorithm
        
        assert is_algorithm_supported("unknown_algo") == False
        assert get_algorithm("unknown_algo") is None
    
    def test_list_algorithms(self):
        """Verify list_algorithms returns registered algorithms."""
        from algorithm_registry import list_algorithms, list_algorithm_names
        
        algos = list_algorithms()
        names = list_algorithm_names()
        
        assert len(algos) > 0
        assert "zscore" in names
    
    def test_get_algorithms_by_mode(self):
        """Verify filtering by detection mode."""
        from algorithm_registry import get_algorithms_by_mode
        from base_algorithm import DetectionMode
        
        point_algos = get_algorithms_by_mode(DetectionMode.POINT)
        
        assert len(point_algos) > 0
        assert any(name == "zscore" for name, _ in point_algos)
    
    def test_get_algorithm_info(self):
        """Verify algorithm info retrieval."""
        from algorithm_registry import get_algorithm_info
        
        info = get_algorithm_info("zscore")
        
        assert info is not None
        assert info["name"] == "zscore"
        assert info["display_name"] == "Z-Score"
        assert info["detection_mode"] == "point"
        assert info["bucket_mode"] == "segment"


class TestEndToEndTraining:
    """Test complete training flow."""
    
    def test_train_via_algorithm_interface(self):
        """Verify training via BaseAlgorithm interface works."""
        from ZScore.algorithm import ZScoreAlgorithm
        
        algo = ZScoreAlgorithm()
        
        # Generate realistic training data
        np.random.seed(42)
        values = np.random.normal(loc=100, scale=15, size=100)
        
        data = [
            {"timestamp": f"2025-01-01T{i % 24:02d}:00:00Z", "value": float(v)}
            for i, v in enumerate(values)
        ]
        
        # Train
        train_result = algo.train(data, metadata={"percentile": 99.5})
        
        assert train_result.sufficient_data == True
        assert train_result.data_points == 100
        assert train_result.baseline["mean"] == pytest.approx(100, rel=0.2)
        assert train_result.baseline["std"] == pytest.approx(15, rel=0.3)
        
        # Detect normal value
        normal_result = algo.detect(value=100.0, baseline=train_result.baseline)
        assert normal_result.is_anomaly == False
        
        # Detect anomaly (5+ std away)
        anomaly_result = algo.detect(value=200.0, baseline=train_result.baseline)
        assert anomaly_result.is_anomaly == True
    
    def test_registry_to_training_flow(self):
        """Verify flow from registry lookup to training."""
        from algorithm_registry import get_algorithm
        
        # Get algorithm from registry
        algo = get_algorithm("zscore")
        assert algo is not None
        
        # Create training data
        data = [{"timestamp": f"2025-01-{i+1:02d}T12:00:00Z", "value": 50.0 + i * 2} 
                for i in range(30)]
        
        # Train using registry-obtained algorithm
        result = algo.train(data)
        
        assert result.sufficient_data == True
        assert result.data_points == 30
        
        # Detect using the trained baseline
        detection = algo.detect(value=1000.0, baseline=result.baseline)
        assert detection.is_anomaly == True


class TestPureZScoreFunctions:
    """Test the pure zscore_algorithm module still works."""
    
    def test_pure_train(self):
        """Verify pure train function."""
        from ZScore import zscore_algorithm as zscore
        
        values = [100, 105, 95, 102, 98, 103, 97, 101, 99, 104]
        baseline = zscore.train(values, percentile=99.5)
        
        assert baseline.mean == pytest.approx(100.4, rel=0.01)
        assert baseline.std > 0
        assert baseline.threshold > 0
        assert baseline.data_points == 10
    
    def test_pure_detect(self):
        """Verify pure detect function."""
        from ZScore import zscore_algorithm as zscore
        
        baseline = zscore.ZScoreBaseline(
            mean=100.0,
            std=10.0,
            threshold=3.0,
            data_points=100,
            percentile=99.5
        )
        
        result = zscore.detect(value=105.0, baseline=baseline)
        
        assert result.is_anomaly == False
        assert result.z_score == pytest.approx(0.5, rel=0.01)


def run_all_tests():
    """Run all tests and print results."""
    print("=" * 70)
    print("ALGORITHM INFRASTRUCTURE POINT-TO-POINT TEST")
    print("=" * 70)
    
    test_classes = [
        TestBaseAlgorithm,
        TestZScoreAlgorithm,
        TestAlgorithmRegistry,
        TestEndToEndTraining,
        TestPureZScoreFunctions,
    ]
    
    total_passed = 0
    total_failed = 0
    failures = []
    
    for test_class in test_classes:
        print(f"\n{test_class.__name__}")
        print("-" * 50)
        
        instance = test_class()
        methods = [m for m in dir(instance) if m.startswith("test_")]
        
        for method_name in methods:
            method = getattr(instance, method_name)
            try:
                method()
                print(f"  ✅ {method_name}")
                total_passed += 1
            except Exception as e:
                print(f"  ❌ {method_name}: {e}")
                total_failed += 1
                failures.append((test_class.__name__, method_name, str(e)))
    
    print("\n" + "=" * 70)
    print(f"RESULTS: {total_passed} passed, {total_failed} failed")
    print("=" * 70)
    
    if failures:
        print("\nFAILURES:")
        for cls, method, error in failures:
            print(f"  - {cls}.{method}: {error}")
        return 1
    else:
        print("\n✅ All tests passed! Algorithm infrastructure is working correctly.")
        return 0


if __name__ == "__main__":
    # Install pytest.approx for standalone run
    class ApproxMatcher:
        def __init__(self, expected, rel=0.01):
            self.expected = expected
            self.rel = rel
        
        def __eq__(self, other):
            if self.expected == 0:
                return abs(other) < self.rel
            return abs(other - self.expected) / abs(self.expected) <= self.rel
    
    # Monkey-patch if pytest not available
    try:
        import pytest
    except ImportError:
        class pytest:
            @staticmethod
            def approx(expected, rel=0.01):
                return ApproxMatcher(expected, rel)
    
    sys.exit(run_all_tests())
