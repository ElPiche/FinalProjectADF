"""Tests for the IQR (Interquartile Range) anomaly detection algorithm.

These tests verify the correctness of the IQR-based outlier detection
which is robust to non-normal distributions.
"""

import pytest
from MotorDA.Dispatcher.algorithms.iqr.iqr import IQRAlgorithm


@pytest.fixture
def iqr_algo():
    """Create IQR algorithm instance."""
    return IQRAlgorithm()


class TestIQRTrain:
    """Test training functionality."""
    
    def test_train_basic(self, iqr_algo):
        """Train on simple values with known quartiles."""
        # Values: 1,2,3,4,5,6,7,8,9,10
        # Q1=3.25, Q3=7.75, IQR=4.5
        # Lower=3.25-1.5*4.5=-3.5, Upper=7.75+1.5*4.5=14.5
        values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        baseline = iqr_algo.train(values)
        
        assert baseline["q1"] == pytest.approx(3.25, rel=0.01)
        assert baseline["q3"] == pytest.approx(7.75, rel=0.01)
        assert baseline["iqr"] == pytest.approx(4.5, rel=0.01)
        assert baseline["lower_bound"] < 0
        assert baseline["upper_bound"] > 10
        assert baseline["data_points"] == 10
    
    def test_train_insufficient_data(self, iqr_algo):
        """Less than 4 values should use fallback."""
        values = [5, 10, 15]
        baseline = iqr_algo.train(values)
        
        assert baseline["iqr"] == 0.0
        assert baseline["data_points"] == 3
    
    def test_train_custom_multiplier(self, iqr_algo):
        """Custom multiplier should affect bounds."""
        values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        
        baseline_normal = iqr_algo.train(values, multiplier=1.5)
        baseline_strict = iqr_algo.train(values, multiplier=3.0)
        
        # Larger multiplier = wider bounds
        assert baseline_strict["upper_bound"] > baseline_normal["upper_bound"]
        assert baseline_strict["lower_bound"] < baseline_normal["lower_bound"]
    
    def test_train_with_outliers(self, iqr_algo):
        """IQR should be robust to outliers."""
        # Most values around 100, but one extreme outlier
        values = [95, 98, 100, 102, 105, 100, 99, 101, 103, 1000]
        baseline = iqr_algo.train(values)
        
        # Q1 and Q3 should not be heavily affected by the 1000 outlier
        assert baseline["q1"] < 150
        assert baseline["q3"] < 150


class TestIQRDetect:
    """Test detection functionality."""
    
    def test_detect_normal_value(self, iqr_algo):
        """Value within bounds should not be anomaly."""
        baseline = {
            "q1": 25.0,
            "q3": 75.0,
            "iqr": 50.0,
            "lower_bound": -50.0,
            "upper_bound": 150.0,
            "multiplier": 1.5,
        }
        
        result = iqr_algo.detect(50.0, baseline)
        
        assert result["is_anomaly"] is False
        assert result["value"] == 50.0
        assert result["distance_from_bounds"] == 0.0
    
    def test_detect_high_anomaly(self, iqr_algo):
        """Value above upper bound should be anomaly."""
        baseline = {
            "q1": 25.0,
            "q3": 75.0,
            "iqr": 50.0,
            "lower_bound": -50.0,
            "upper_bound": 150.0,
            "multiplier": 1.5,
        }
        
        result = iqr_algo.detect(200.0, baseline)
        
        assert result["is_anomaly"] is True
        assert result["distance_from_bounds"] == 50.0  # 200 - 150 = 50
    
    def test_detect_low_anomaly(self, iqr_algo):
        """Value below lower bound should be anomaly."""
        baseline = {
            "q1": 25.0,
            "q3": 75.0,
            "iqr": 50.0,
            "lower_bound": -50.0,
            "upper_bound": 150.0,
            "multiplier": 1.5,
        }
        
        result = iqr_algo.detect(-100.0, baseline)
        
        assert result["is_anomaly"] is True
        assert result["distance_from_bounds"] == 50.0  # -50 - (-100) = 50
    
    def test_detect_at_boundary(self, iqr_algo):
        """Value exactly at boundary should not be anomaly."""
        baseline = {
            "q1": 25.0,
            "q3": 75.0,
            "iqr": 50.0,
            "lower_bound": 0.0,
            "upper_bound": 100.0,
            "multiplier": 1.5,
        }
        
        # At lower boundary
        result = iqr_algo.detect(0.0, baseline)
        assert result["is_anomaly"] is False
        
        # At upper boundary
        result = iqr_algo.detect(100.0, baseline)
        assert result["is_anomaly"] is False


class TestIQRDetectBatch:
    """Test batch detection."""
    
    def test_detect_batch_mixed(self, iqr_algo):
        """Batch with normal and anomalous values."""
        baseline = {
            "q1": 25.0,
            "q3": 75.0,
            "iqr": 50.0,
            "lower_bound": 0.0,
            "upper_bound": 100.0,
            "multiplier": 1.5,
        }
        
        values = [50.0, 75.0, 150.0, -50.0]  # normal, normal, anomaly, anomaly
        results = iqr_algo.detect_batch(values, baseline)
        
        assert len(results) == 4
        assert results[0]["is_anomaly"] is False
        assert results[1]["is_anomaly"] is False
        assert results[2]["is_anomaly"] is True
        assert results[3]["is_anomaly"] is True


class TestIQRMultiDimension:
    """Test multi-dimension training and detection."""
    
    def test_train_multi_dimension(self, iqr_algo):
        """Train on multiple dimensions."""
        observations = [
            {"requests": 100, "errors": 5},
            {"requests": 110, "errors": 3},
            {"requests": 105, "errors": 4},
            {"requests": 95, "errors": 6},
            {"requests": 108, "errors": 5},
        ]
        parameters = [
            {"dimension": "requests"},
            {"dimension": "errors"},
        ]
        
        result = iqr_algo.train_multi_dimension(observations, parameters)
        
        assert "requests" in result
        assert "errors" in result
        assert result["requests"]["data_points"] == 5
        assert result["errors"]["data_points"] == 5
    
    def test_detect_multi_dimension(self, iqr_algo):
        """Detect anomalies across multiple dimensions."""
        baselines = {
            "requests": {
                "q1": 95.0,
                "q3": 110.0,
                "iqr": 15.0,
                "lower_bound": 72.5,
                "upper_bound": 132.5,
            },
            "errors": {
                "q1": 3.0,
                "q3": 6.0,
                "iqr": 3.0,
                "lower_bound": -1.5,
                "upper_bound": 10.5,
            },
        }
        parameters = [
            {"dimension": "requests"},
            {"dimension": "errors"},
        ]
        
        # Normal observation
        result = iqr_algo.detect_multi_dimension(
            {"requests": 100, "errors": 5},
            baselines,
            parameters
        )
        assert result["is_anomaly"] is False
        
        # Anomalous requests
        result = iqr_algo.detect_multi_dimension(
            {"requests": 200, "errors": 5},
            baselines,
            parameters
        )
        assert result["is_anomaly"] is True


class TestEndToEnd:
    """End-to-end tests simulating real usage."""
    
    def test_train_and_detect(self, iqr_algo):
        """Full train-then-detect workflow."""
        # Simulated traffic data
        training_values = [100, 105, 98, 110, 95, 102, 108, 97, 103, 99,
                          101, 104, 96, 107, 94, 106, 100, 103, 98, 102]
        
        baseline = iqr_algo.train(training_values)
        
        # Normal values should pass
        assert iqr_algo.detect(100, baseline)["is_anomaly"] is False
        assert iqr_algo.detect(110, baseline)["is_anomaly"] is False
        
        # Extreme values should be flagged
        assert iqr_algo.detect(200, baseline)["is_anomaly"] is True
        assert iqr_algo.detect(50, baseline)["is_anomaly"] is True
    
    def test_robust_to_skewed_data(self, iqr_algo):
        """IQR should handle skewed distributions well."""
        # Right-skewed data (common in web traffic)
        values = [10, 12, 11, 15, 13, 14, 10, 11, 12, 50, 100, 200]
        
        baseline = iqr_algo.train(values, multiplier=1.5)
        
        # Very large values should be detected
        assert iqr_algo.detect(500, baseline)["is_anomaly"] is True
