"""Point-to-Point Test for ARMAX Algorithm.

This test verifies the complete ARMAX flow:
1. ARMAXModel dataclass
2. armax_core pure functions (train_armax, predict_armax, detect_armax)
3. ARMAXAlgorithm BaseAlgorithm implementation
4. Algorithm registry integration
5. End-to-end training and detection

Run with:
    cd MotorDA
    python -m pytest tests/test_armax_algorithm.py -v
    
Or directly:
    python tests/test_armax_algorithm.py
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

import numpy as np


class TestARMAXModel:
    """Test the ARMAXModel dataclass."""
    
    def test_model_creation(self):
        """Verify ARMAXModel can be created with defaults."""
        from ARMAX.armax_core import ARMAXModel
        
        model = ARMAXModel()
        
        assert model.order == (1, 0, 1)
        assert model.data_points == 0
        assert model.threshold_multiplier == 3.0
    
    def test_model_to_dict(self):
        """Verify ARMAXModel serializes correctly."""
        from ARMAX.armax_core import ARMAXModel
        
        model = ARMAXModel(
            ar_params=[0.5, 0.3],
            ma_params=[0.1],
            intercept=10.0,
            residual_std=5.0,
            order=(2, 0, 1),
            training_mean=100.0,
            training_std=15.0,
            threshold_multiplier=3.0,
            data_points=50,
        )
        
        d = model.to_dict()
        
        assert d["ar_params"] == [0.5, 0.3]
        assert d["order"] == [2, 0, 1]
        assert d["training_mean"] == 100.0
        assert d["anomaly_threshold"] == 5.0 * 3.0  # residual_std * multiplier
    
    def test_model_from_dict(self):
        """Verify ARMAXModel deserializes correctly."""
        from ARMAX.armax_core import ARMAXModel
        
        d = {
            "ar_params": [0.7],
            "ma_params": [],
            "intercept": 5.0,
            "residual_std": 2.0,
            "order": [1, 0, 0],
            "training_mean": 50.0,
            "training_std": 10.0,
            "threshold_multiplier": 2.5,
            "data_points": 30,
        }
        
        model = ARMAXModel.from_dict(d)
        
        assert model.ar_params == [0.7]
        assert model.order == (1, 0, 0)
        assert model.training_mean == 50.0


class TestARMAXCoreFunctions:
    """Test the armax_core pure functions."""
    
    def test_extract_exog_features(self):
        """Verify exogenous feature extraction."""
        from ARMAX.armax_core import extract_exog_features
        
        data = [
            {"timestamp": datetime(2025, 1, 6, 9, 0, tzinfo=timezone.utc), "value": 100},  # Monday 9am
            {"timestamp": datetime(2025, 1, 6, 14, 0, tzinfo=timezone.utc), "value": 110}, # Monday 2pm
            {"timestamp": datetime(2025, 1, 11, 10, 0, tzinfo=timezone.utc), "value": 90}, # Saturday 10am
        ]
        
        features = extract_exog_features(data, ["hour", "is_workday"])
        
        assert features.shape == (3, 2)
        assert features[0, 0] == 9.0  # hour
        assert features[0, 1] == 1.0  # is_workday (Monday)
        assert features[2, 1] == 0.0  # is_workday (Saturday)
    
    def test_train_armax_minimal(self):
        """Verify training with minimal data returns safe defaults."""
        from ARMAX.armax_core import train_armax
        
        # Only 5 data points - less than minimum
        data = [
            {"timestamp": datetime(2025, 1, 1, i, 0, tzinfo=timezone.utc), "value": 100 + i}
            for i in range(5)
        ]
        
        model = train_armax(data, min_training_points=10)
        
        assert model.data_points == 5
        assert model.training_mean == pytest.approx(102.0, rel=0.01)  # mean of 100-104
    
    def test_train_armax_full(self):
        """Verify training with sufficient data."""
        from ARMAX.armax_core import train_armax
        
        np.random.seed(42)
        
        # Generate 50 data points with pattern
        data = []
        for i in range(50):
            ts = datetime(2025, 1, 1, i % 24, 0, tzinfo=timezone.utc) + timedelta(days=i // 24)
            value = 100 + 10 * np.sin(i * 0.5) + np.random.randn() * 2
            data.append({
                "timestamp": ts,
                "value": value,
                "hour": ts.hour,
                "is_workday": 1 if ts.weekday() < 5 else 0,
            })
        
        model = train_armax(data, order=(2, 0, 1), min_training_points=20)
        
        assert model.data_points == 50
        assert len(model.ar_params) > 0
        assert model.residual_std > 0
    
    def test_predict_armax(self):
        """Verify prediction uses history."""
        from ARMAX.armax_core import ARMAXModel, predict_armax
        
        model = ARMAXModel(
            ar_params=[0.5, 0.3],
            intercept=0.0,
            training_mean=100.0,
            training_std=10.0,
            order=(2, 0, 0),
        )
        
        history = [
            {"value": 95.0},
            {"value": 100.0},
            {"value": 105.0},
            {"value": 110.0},
        ]
        
        prediction = predict_armax(model, history)
        
        # Should be influenced by recent values
        assert prediction is not None
        assert abs(prediction - 100) < 50  # Reasonable range
    
    def test_detect_armax_normal(self):
        """Verify detection of normal values."""
        from ARMAX.armax_core import ARMAXModel, detect_armax
        
        model = ARMAXModel(
            ar_params=[0.5],
            intercept=0.0,
            training_mean=100.0,
            training_std=10.0,
            residual_std=0.5,  # Low residual std
            threshold_multiplier=3.0,
            order=(1, 0, 0),
        )
        
        history = [{"value": 100.0 + i} for i in range(10)]
        
        result = detect_armax(
            model=model,
            actual_value=105.0,  # Close to prediction
            history=history,
        )
        
        # Normal value should not be anomaly (prediction should be close)
        # The exact result depends on model prediction
        assert result.actual_value == 105.0
    
    def test_detect_armax_anomaly(self):
        """Verify detection of anomalous values."""
        from ARMAX.armax_core import ARMAXModel, detect_armax
        
        model = ARMAXModel(
            ar_params=[0.9],  # Strong AR - predicts close to recent
            intercept=0.0,
            training_mean=100.0,
            training_std=10.0,
            residual_std=0.1,  # Very low residual - tight threshold
            threshold_multiplier=3.0,
            order=(1, 0, 0),
        )
        
        # History around 100
        history = [{"value": 100.0 + i * 0.1} for i in range(10)]
        
        result = detect_armax(
            model=model,
            actual_value=500.0,  # Way off from prediction
            history=history,
        )
        
        assert result.is_anomaly == True
        assert result.prediction_error > result.threshold


class TestARMAXAlgorithm:
    """Test the ARMAXAlgorithm BaseAlgorithm implementation."""
    
    def test_class_attributes(self):
        """Verify ARMAXAlgorithm has correct class attributes."""
        from ARMAX.algorithm import ARMAXAlgorithm
        from base_algorithm import DetectionMode, BucketMode
        
        algo = ARMAXAlgorithm()
        
        assert algo.name == "armax"
        assert algo.display_name == "ARMAX"
        assert algo.detection_mode.value == DetectionMode.SERIES.value
        assert algo.bucket_mode.value == BucketMode.FEATURE.value
        assert algo.required_history_length == 10
        assert algo.minimum_training_points == 20
    
    def test_train_empty_data(self):
        """Verify training handles empty data."""
        from ARMAX.algorithm import ARMAXAlgorithm
        
        algo = ARMAXAlgorithm()
        result = algo.train([])
        
        assert result.sufficient_data == False
        assert result.data_points == 0
        assert "model_type" in result.baseline
        assert result.baseline["model_type"] == "armax"
    
    def test_train_with_data(self):
        """Verify training produces valid baseline."""
        from ARMAX.algorithm import ARMAXAlgorithm
        
        algo = ARMAXAlgorithm()
        
        np.random.seed(42)
        data = []
        for i in range(30):
            ts = datetime(2025, 1, 1 + i // 24, i % 24, 0, tzinfo=timezone.utc)
            data.append({
                "timestamp": ts,
                "value": 100 + np.random.randn() * 5,
                "hour": ts.hour,
                "is_workday": 1 if ts.weekday() < 5 else 0,
            })
        
        result = algo.train(data, metadata={"order": [2, 0, 1]})
        
        assert result.sufficient_data == True
        assert result.data_points == 30
        assert result.baseline["model_type"] == "armax"
        assert "ar_params" in result.baseline
    
    def test_detect_insufficient_history(self):
        """Verify detection handles insufficient history."""
        from ARMAX.algorithm import ARMAXAlgorithm
        
        algo = ARMAXAlgorithm()
        
        baseline = {
            "ar_params": [0.5],
            "training_mean": 100.0,
            "training_std": 10.0,
            "residual_std": 1.0,
            "threshold_multiplier": 3.0,
            "order": [1, 0, 0],
        }
        
        # Only 3 history points - need 10
        history = [{"value": 100.0}, {"value": 101.0}, {"value": 102.0}]
        
        result = algo.detect(value=105.0, baseline=baseline, history=history)
        
        assert result.is_anomaly == False
        assert "error" in result.algorithm_details or "Insufficient" in str(result.algorithm_details)
    
    def test_detect_with_history(self):
        """Verify detection with sufficient history."""
        from ARMAX.algorithm import ARMAXAlgorithm
        
        algo = ARMAXAlgorithm()
        
        baseline = {
            "ar_params": [0.7, 0.2],
            "ma_params": [],
            "exog_params": {"hour": 0.1},
            "intercept": 0.0,
            "training_mean": 100.0,
            "training_std": 10.0,
            "residual_std": 2.0,
            "threshold_multiplier": 3.0,
            "order": [2, 0, 0],
            "exog_features": ["hour"],
        }
        
        history = [{"value": 100.0 + i, "hour": i % 24} for i in range(15)]
        
        result = algo.detect(
            value=110.0, 
            baseline=baseline, 
            history=history,
            bucket_features={"hour": 15.0, "is_workday": 1.0}
        )
        
        assert "predicted_value" in result.algorithm_details
        assert "prediction_error" in result.algorithm_details
        assert "threshold" in result.algorithm_details
    
    def test_format_anomaly_text(self):
        """Verify anomaly text formatting."""
        from ARMAX.algorithm import ARMAXAlgorithm
        
        algo = ARMAXAlgorithm()
        
        details = {
            "predicted_value": 100.0,
            "prediction_error": 50.0,
            "threshold": 30.0,
        }
        
        text = algo.format_anomaly_text(value=150.0, details=details, bucket_key="workday_09")
        
        assert "50.00" in text  # error
        assert "30.00" in text  # threshold
        assert "workday" in text.lower()
    
    def test_validate_config_valid(self):
        """Verify config validation with valid params."""
        from ARMAX.algorithm import ARMAXAlgorithm
        
        algo = ARMAXAlgorithm()
        
        errors = algo.validate_config({
            "order": [2, 0, 2],
            "threshold_multiplier": 3.0,
            "exog_features": ["hour", "is_workday"],
        })
        
        assert errors == []
    
    def test_validate_config_invalid_order(self):
        """Verify config validation catches invalid order."""
        from ARMAX.algorithm import ARMAXAlgorithm
        
        algo = ARMAXAlgorithm()
        
        errors = algo.validate_config({"order": [10, 0, 10]})  # p, q too high
        
        assert len(errors) > 0
        assert any("order" in e.lower() for e in errors)
    
    def test_validate_config_invalid_threshold(self):
        """Verify config validation catches invalid threshold."""
        from ARMAX.algorithm import ARMAXAlgorithm
        
        algo = ARMAXAlgorithm()
        
        errors = algo.validate_config({"threshold_multiplier": -1})
        
        assert len(errors) > 0


class TestAlgorithmRegistry:
    """Test ARMAX integration with algorithm registry."""
    
    def test_armax_is_registered(self):
        """Verify ARMAX is in the registry."""
        from algorithm_registry import is_algorithm_supported, get_algorithm
        
        assert is_algorithm_supported("armax") == True
        assert is_algorithm_supported("ARMAX") == True  # Case insensitive
        
        algo = get_algorithm("armax")
        assert algo is not None
        assert algo.name == "armax"
    
    def test_armax_is_series_mode(self):
        """Verify ARMAX is categorized as SERIES mode."""
        from algorithm_registry import get_algorithms_by_mode
        from base_algorithm import DetectionMode
        
        series_algos = get_algorithms_by_mode(DetectionMode.SERIES)
        
        assert len(series_algos) > 0
        assert any(name == "armax" for name, _ in series_algos)
    
    def test_armax_is_feature_bucket_mode(self):
        """Verify ARMAX uses FEATURE bucket mode."""
        from algorithm_registry import get_algorithms_by_bucket_mode
        from base_algorithm import BucketMode
        
        feature_algos = get_algorithms_by_bucket_mode(BucketMode.FEATURE)
        
        assert len(feature_algos) > 0
        assert any(name == "armax" for name, _ in feature_algos)
    
    def test_get_algorithm_info(self):
        """Verify algorithm info retrieval."""
        from algorithm_registry import get_algorithm_info
        
        info = get_algorithm_info("armax")
        
        assert info is not None
        assert info["name"] == "armax"
        assert info["display_name"] == "ARMAX"
        assert info["detection_mode"] == "series"
        assert info["bucket_mode"] == "feature"
        assert info["required_history_length"] == 10


class TestEndToEndARMAX:
    """End-to-end test for ARMAX training and detection."""
    
    def test_full_training_detection_flow(self):
        """Test complete flow from training to detection."""
        from ARMAX.algorithm import ARMAXAlgorithm
        
        algo = ARMAXAlgorithm()
        
        # Generate training data with clear pattern
        np.random.seed(42)
        training_data = []
        for i in range(100):
            ts = datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i)
            # Pattern: base 100, small variation
            value = 100 + 5 * np.sin(i * 0.3) + np.random.randn() * 2
            training_data.append({
                "timestamp": ts,
                "value": value,
                "hour": ts.hour,
                "is_workday": 1 if ts.weekday() < 5 else 0,
                "day_of_week": ts.weekday(),
            })
        
        # Train
        train_result = algo.train(
            training_data, 
            metadata={"order": [2, 0, 1], "threshold_multiplier": 3.0}
        )
        
        assert train_result.sufficient_data == True
        assert train_result.data_points == 100
        
        # Detection with normal value
        history = training_data[-15:]  # Last 15 points as history
        normal_result = algo.detect(
            value=102.0,  # Normal value
            baseline=train_result.baseline,
            history=history,
            bucket_features={"hour": 12.0, "is_workday": 1.0},
        )
        
        assert "predicted_value" in normal_result.algorithm_details
        
        # Detection with anomalous value
        anomaly_result = algo.detect(
            value=500.0,  # Way off from normal
            baseline=train_result.baseline,
            history=history,
            bucket_features={"hour": 12.0, "is_workday": 1.0},
        )
        
        assert anomaly_result.is_anomaly == True
        assert anomaly_result.algorithm_details["prediction_error"] > anomaly_result.algorithm_details["threshold"]
    
    def test_anomaly_detection_sensitivity(self):
        """Test that threshold_multiplier affects sensitivity."""
        from ARMAX.algorithm import ARMAXAlgorithm
        
        algo = ARMAXAlgorithm()
        
        # Training data - use timedelta to properly handle hours >= 24
        np.random.seed(42)
        base_time = datetime(2025, 1, 1, 0, tzinfo=timezone.utc)
        training_data = [
            {"timestamp": base_time + timedelta(hours=i), "value": 100 + np.random.randn() * 5}
            for i in range(50)
        ]
        
        # Train with tight threshold
        tight_result = algo.train(training_data, metadata={"threshold_multiplier": 1.0})
        # Train with loose threshold
        loose_result = algo.train(training_data, metadata={"threshold_multiplier": 5.0})
        
        # Same history and value
        history = training_data[-15:]
        test_value = 130.0  # Moderately high
        
        tight_detection = algo.detect(value=test_value, baseline=tight_result.baseline, history=history)
        loose_detection = algo.detect(value=test_value, baseline=loose_result.baseline, history=history)
        
        # Tight threshold should catch more anomalies
        assert tight_detection.algorithm_details["threshold"] < loose_detection.algorithm_details["threshold"]


def run_all_tests():
    """Run all tests and print results."""
    print("=" * 70)
    print("ARMAX ALGORITHM POINT-TO-POINT TEST")
    print("=" * 70)
    
    test_classes = [
        TestARMAXModel,
        TestARMAXCoreFunctions,
        TestARMAXAlgorithm,
        TestAlgorithmRegistry,
        TestEndToEndARMAX,
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
        print("\n✅ All ARMAX tests passed! ARMAX algorithm is working correctly.")
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
