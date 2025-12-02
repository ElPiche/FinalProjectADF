"""Tests for the pure Z-Score algorithm.

These tests verify the statistical correctness of the Z-Score algorithm
WITHOUT any bucket/time logic - that's the Dispatcher's job.
"""

import pytest
import numpy as np
from MotorDA.Dispatcher.algorithms.zscore.zscore_algorithm import (
    train,
    detect,
    detect_batch,
    train_from_dict,
    detect_from_dict,
    create_global_fallback,
    ZScoreBaseline,
    AnomalyResult,
)


class TestZScoreTrain:
    """Test training functionality."""
    
    def test_train_basic(self):
        """Train on simple values."""
        values = [10.0, 12.0, 11.0, 10.5, 11.5]
        baseline = train(values)
        
        assert baseline.mean == pytest.approx(11.0, rel=0.01)
        assert baseline.std > 0
        assert baseline.threshold > 0
        assert baseline.data_points == 5
        assert baseline.percentile == 99.5
    
    def test_train_empty_raises(self):
        """Empty values should raise ValueError."""
        with pytest.raises(ValueError, match="Cannot train on empty"):
            train([])
    
    def test_train_single_value(self):
        """Single value should use fallback std."""
        baseline = train([42.0])
        
        assert baseline.mean == 42.0
        assert baseline.std == pytest.approx(1e-6)  # Fallback
        assert baseline.data_points == 1
    
    def test_train_identical_values(self):
        """Identical values should use fallback std."""
        baseline = train([5.0, 5.0, 5.0, 5.0])
        
        assert baseline.mean == 5.0
        assert baseline.std == pytest.approx(1e-6)  # Fallback
        assert baseline.data_points == 4
    
    def test_train_custom_percentile(self):
        """Custom percentile should be stored."""
        baseline = train([1, 2, 3, 4, 5], percentile=95.0)
        
        assert baseline.percentile == 95.0
    
    def test_train_threshold_calculation(self):
        """Threshold should be based on percentile of z-scores."""
        # Normal distribution values
        np.random.seed(42)
        values = list(np.random.normal(100, 10, 1000))
        
        baseline = train(values, percentile=99.0)
        
        # For normal distribution, 99th percentile z-score ~ 2.33
        assert baseline.threshold > 2.0
        assert baseline.threshold < 3.5


class TestZScoreDetect:
    """Test detection functionality."""
    
    def test_detect_normal_value(self):
        """Normal value should not be flagged as anomaly."""
        baseline = ZScoreBaseline(
            mean=100.0,
            std=10.0,
            threshold=3.0,
            data_points=100,
            percentile=99.5,
        )
        
        result = detect(105.0, baseline)
        
        assert result.value == 105.0
        assert result.z_score == pytest.approx(0.5)
        assert result.is_anomaly is False
    
    def test_detect_anomaly_high(self):
        """High value should be flagged as anomaly."""
        baseline = ZScoreBaseline(
            mean=100.0,
            std=10.0,
            threshold=2.0,
            data_points=100,
            percentile=99.5,
        )
        
        result = detect(150.0, baseline)  # z-score = 5.0
        
        assert result.z_score == pytest.approx(5.0)
        assert result.is_anomaly is True
    
    def test_detect_anomaly_low(self):
        """Low value should be flagged as anomaly."""
        baseline = ZScoreBaseline(
            mean=100.0,
            std=10.0,
            threshold=2.0,
            data_points=100,
            percentile=99.5,
        )
        
        result = detect(50.0, baseline)  # z-score = -5.0
        
        assert result.z_score == pytest.approx(-5.0)
        assert result.is_anomaly is True
    
    def test_detect_boundary(self):
        """Value at threshold boundary."""
        baseline = ZScoreBaseline(
            mean=100.0,
            std=10.0,
            threshold=2.0,
            data_points=100,
            percentile=99.5,
        )
        
        # Exactly at threshold
        result = detect(120.0, baseline)  # z-score = 2.0
        assert result.is_anomaly is False  # Not strictly greater
        
        # Just above threshold
        result = detect(120.1, baseline)
        assert result.is_anomaly is True


class TestZScoreDetectBatch:
    """Test batch detection."""
    
    def test_detect_batch_empty(self):
        """Empty batch should return empty list."""
        baseline = ZScoreBaseline(
            mean=100.0,
            std=10.0,
            threshold=2.0,
            data_points=100,
            percentile=99.5,
        )
        
        results = detect_batch([], baseline)
        assert results == []
    
    def test_detect_batch_mixed(self):
        """Batch with normal and anomalous values."""
        baseline = ZScoreBaseline(
            mean=100.0,
            std=10.0,
            threshold=2.0,
            data_points=100,
            percentile=99.5,
        )
        
        values = [100.0, 105.0, 150.0, 50.0]  # normal, normal, anomaly, anomaly
        results = detect_batch(values, baseline)
        
        assert len(results) == 4
        assert results[0].is_anomaly is False
        assert results[1].is_anomaly is False
        assert results[2].is_anomaly is True
        assert results[3].is_anomaly is True


class TestZScoreSerialization:
    """Test dict serialization for MongoDB."""
    
    def test_baseline_to_dict(self):
        """Baseline should serialize to dict."""
        baseline = ZScoreBaseline(
            mean=100.0,
            std=10.0,
            threshold=2.5,
            data_points=50,
            percentile=99.0,
        )
        
        d = baseline.to_dict()
        
        assert d["mean"] == 100.0
        assert d["std"] == 10.0
        assert d["threshold"] == 2.5
        assert d["data_points"] == 50
        assert d["percentile"] == 99.0
    
    def test_baseline_from_dict(self):
        """Baseline should deserialize from dict."""
        d = {
            "mean": 100.0,
            "std": 10.0,
            "threshold": 2.5,
            "data_points": 50,
            "percentile": 99.0,
        }
        
        baseline = ZScoreBaseline.from_dict(d)
        
        assert baseline.mean == 100.0
        assert baseline.std == 10.0
        assert baseline.threshold == 2.5
    
    def test_result_to_dict(self):
        """AnomalyResult should serialize to dict."""
        result = AnomalyResult(
            value=150.0,
            z_score=5.0,
            is_anomaly=True,
            mean=100.0,
            std=10.0,
            threshold=2.0,
        )
        
        d = result.to_dict()
        
        assert d["value"] == 150.0
        assert d["z_score"] == 5.0
        assert d["is_anomaly"] is True
    
    def test_train_from_dict(self):
        """train_from_dict should return dict."""
        values = [10, 20, 30, 40, 50]
        d = train_from_dict(values)
        
        assert "mean" in d
        assert "std" in d
        assert "threshold" in d
    
    def test_detect_from_dict(self):
        """detect_from_dict should work with dict baseline."""
        baseline_dict = {
            "mean": 100.0,
            "std": 10.0,
            "threshold": 2.0,
            "data_points": 100,
            "percentile": 99.5,
        }
        
        result = detect_from_dict(150.0, baseline_dict)
        
        assert result["value"] == 150.0
        assert result["is_anomaly"] is True


class TestGlobalFallback:
    """Test global fallback baseline."""
    
    def test_create_global_fallback(self):
        """Global fallback should be trainable."""
        all_values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        fallback = create_global_fallback(all_values)
        
        assert fallback.mean == pytest.approx(55.0)
        assert fallback.std > 0
        assert fallback.data_points == 10
    
    def test_create_global_fallback_empty(self):
        """Empty values should return permissive fallback."""
        fallback = create_global_fallback([])
        
        assert fallback.mean == 0.0
        assert fallback.std == 1.0
        assert fallback.threshold == 3.0
        assert fallback.data_points == 0


class TestEndToEnd:
    """End-to-end tests simulating real usage."""
    
    def test_train_and_detect(self):
        """Full train-then-detect workflow."""
        # Training data: normal request counts around 100
        np.random.seed(42)
        training_values = list(np.random.normal(100, 15, 500))
        
        # Train
        baseline = train(training_values, percentile=99.0)
        
        # Normal detection
        result = detect(110.0, baseline)
        assert result.is_anomaly is False
        
        # Anomaly detection (3x std)
        result = detect(160.0, baseline)
        assert result.is_anomaly is True
    
    def test_realistic_traffic_pattern(self):
        """Test with realistic web traffic pattern."""
        # Simulate 1 week of hourly request counts
        # Normal: ~1000 requests/hour, std ~100
        np.random.seed(123)
        training_values = list(np.random.normal(1000, 100, 168))  # 24*7 hours
        
        baseline = train(training_values, percentile=99.5)
        
        # Normal traffic
        assert detect(950, baseline).is_anomaly is False
        assert detect(1100, baseline).is_anomaly is False
        
        # Traffic spike (DDoS?)
        assert detect(1500, baseline).is_anomaly is True
        
        # Traffic drop (outage?)
        assert detect(500, baseline).is_anomaly is True
