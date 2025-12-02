"""Tests for the Mock anomaly detection algorithm.

The Mock algorithm is for testing and demonstration purposes.
These tests verify the basic threshold-based detection works correctly.
"""

import pytest
from MotorDA.Dispatcher.algorithms.mock.mock import MockAlgorithm


@pytest.fixture
def mock_algo():
    """Create Mock algorithm instance."""
    return MockAlgorithm()


class TestMockTrain:
    """Test training functionality."""
    
    def test_train_basic(self, mock_algo):
        """Train on simple values."""
        values = [10, 20, 30, 40, 50]
        baseline = mock_algo.train(values)
        
        assert baseline["mean"] == 30.0
        assert "threshold" in baseline
        assert baseline["data_points"] == 5
    
    def test_train_empty(self, mock_algo):
        """Empty values should use defaults."""
        baseline = mock_algo.train([])
        
        assert baseline["mean"] == 0.0
        assert baseline["threshold"] == 10.0
    
    def test_train_custom_percentile(self, mock_algo):
        """Custom percentile affects threshold."""
        values = [10, 20, 30]
        
        baseline_low = mock_algo.train(values, percentile=50.0)
        baseline_high = mock_algo.train(values, percentile=99.0)
        
        assert baseline_high["threshold"] > baseline_low["threshold"]


class TestMockDetect:
    """Test detection functionality."""
    
    def test_detect_normal_value(self, mock_algo):
        """Value close to mean should not be anomaly."""
        baseline = {"mean": 100.0, "threshold": 20.0}
        
        result = mock_algo.detect(105.0, baseline)
        
        assert result["is_anomaly"] is False
        assert result["value"] == 105.0
        assert result["deviation"] == 5.0
    
    def test_detect_anomaly(self, mock_algo):
        """Value far from mean should be anomaly."""
        baseline = {"mean": 100.0, "threshold": 20.0}
        
        result = mock_algo.detect(150.0, baseline)
        
        assert result["is_anomaly"] is True
        assert result["deviation"] == 50.0
    
    def test_detect_boundary(self, mock_algo):
        """Value at threshold boundary."""
        baseline = {"mean": 100.0, "threshold": 20.0}
        
        # Exactly at threshold
        result = mock_algo.detect(120.0, baseline)
        assert result["is_anomaly"] is False  # deviation equals threshold, not greater
        
        # Just over threshold
        result = mock_algo.detect(121.0, baseline)
        assert result["is_anomaly"] is True


class TestMockDetectBatch:
    """Test batch detection."""
    
    def test_detect_batch_mixed(self, mock_algo):
        """Batch with normal and anomalous values."""
        baseline = {"mean": 100.0, "threshold": 20.0}
        
        values = [100.0, 110.0, 150.0, 50.0]  # normal, normal, anomaly, anomaly
        results = mock_algo.detect_batch(values, baseline)
        
        assert len(results) == 4
        assert results[0]["is_anomaly"] is False
        assert results[1]["is_anomaly"] is False
        assert results[2]["is_anomaly"] is True
        assert results[3]["is_anomaly"] is True


class TestMockMultiDimension:
    """Test multi-dimension training and detection."""
    
    def test_train_multi_dimension(self, mock_algo):
        """Train on multiple dimensions."""
        observations = [
            {"requests": 100, "latency": 50},
            {"requests": 110, "latency": 55},
            {"requests": 105, "latency": 52},
        ]
        parameters = [
            {"dimension": "requests"},
            {"dimension": "latency"},
        ]
        
        result = mock_algo.train_multi_dimension(observations, parameters)
        
        assert "requests" in result
        assert "latency" in result
        assert result["requests"]["mean"] == pytest.approx(105.0, rel=0.01)
        assert result["latency"]["mean"] == pytest.approx(52.33, rel=0.01)
    
    def test_detect_multi_dimension(self, mock_algo):
        """Detect anomalies across multiple dimensions."""
        baselines = {
            "requests": {"mean": 100.0, "threshold": 20.0},
            "latency": {"mean": 50.0, "threshold": 10.0},
        }
        parameters = [
            {"dimension": "requests"},
            {"dimension": "latency"},
        ]
        
        # Normal observation
        result = mock_algo.detect_multi_dimension(
            {"requests": 100, "latency": 50},
            baselines,
            parameters
        )
        assert result["is_anomaly"] is False
        
        # Anomalous latency
        result = mock_algo.detect_multi_dimension(
            {"requests": 100, "latency": 100},
            baselines,
            parameters
        )
        assert result["is_anomaly"] is True


class TestEndToEnd:
    """End-to-end tests."""
    
    def test_train_and_detect(self, mock_algo):
        """Full train-then-detect workflow."""
        training_values = [100, 105, 98, 110, 95, 102, 108, 97, 103, 99]
        
        baseline = mock_algo.train(training_values)
        
        # Normal values
        assert mock_algo.detect(100, baseline)["is_anomaly"] is False
        
        # Extreme values
        assert mock_algo.detect(200, baseline)["is_anomaly"] is True
