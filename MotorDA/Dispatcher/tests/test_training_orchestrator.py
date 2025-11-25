"""Tests for Training Orchestrator.

Tests the integration of BucketResolver with pure ZScore algorithm.
Bucket logic is in the orchestrator, NOT in ZScore.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone as tz, timedelta
from unittest.mock import Mock, MagicMock, patch

from MotorDA.Dispatcher.training_orchestrator import (
    TrainingOrchestrator,
    DetectionOrchestrator,
    run_zscore_training_bucketed,
)
from MotorDA.Dispatcher.bucket_resolver import (
    BucketResolver, 
    BucketProfile,
    ScheduleRule,
    FallbackRule,
)


def create_workday_weekend_profile(profile_id: str = "test") -> BucketProfile:
    """Helper to create a standard workday/weekend profile."""
    return BucketProfile(
        profile_id=profile_id,
        timezone="UTC",
        schedule=[
            ScheduleRule(
                bucket_base_key="workday",
                days=[1, 2, 3, 4, 5],
                granularity="block",
            ),
            ScheduleRule(
                bucket_base_key="weekend",
                days=[6, 7],
                granularity="block",
            ),
        ],
    )


class TestTrainingOrchestratorGrouping:
    """Test bucket grouping functionality."""
    
    def test_group_without_resolver_uses_global_default(self):
        """Without resolver, all data goes to global_default bucket."""
        orchestrator = TrainingOrchestrator(
            bucket_resolver=None,
            bucket_profile_id=None,
        )
        
        df = pd.DataFrame({
            "timestamp": pd.date_range("2025-11-25 10:00", periods=5, freq="h"),
            "value": [10, 20, 30, 40, 50],
        })
        
        grouped = orchestrator.group_by_bucket(df)
        
        assert len(grouped) == 1
        assert "global_default" in grouped
        assert len(grouped["global_default"]) == 5
    
    def test_group_with_simple_resolver(self):
        """With resolver, data is grouped by resolved bucket keys."""
        profile = create_workday_weekend_profile()
        resolver = BucketResolver(profile)
        
        orchestrator = TrainingOrchestrator(
            bucket_resolver=resolver,
            bucket_profile_id="test",
        )
        
        # Monday and Saturday data
        df = pd.DataFrame({
            "timestamp": [
                datetime(2025, 11, 24, 10, 0, tzinfo=tz.utc),  # Monday
                datetime(2025, 11, 24, 14, 0, tzinfo=tz.utc),  # Monday
                datetime(2025, 11, 29, 10, 0, tzinfo=tz.utc),  # Saturday
            ],
            "value": [100, 110, 200],
        })
        
        grouped = orchestrator.group_by_bucket(df)
        
        assert "workday" in grouped
        assert "weekend" in grouped
        assert len(grouped["workday"]) == 2
        assert len(grouped["weekend"]) == 1
    
    def test_group_empty_dataframe(self):
        """Empty DataFrame returns empty dict."""
        orchestrator = TrainingOrchestrator(
            bucket_resolver=None,
            bucket_profile_id=None,
        )
        
        df = pd.DataFrame({"timestamp": [], "value": []})
        grouped = orchestrator.group_by_bucket(df)
        
        assert grouped == {}


class TestTrainingOrchestratorTraining:
    """Test training with bucket grouping."""
    
    def test_train_dimension_single_bucket(self):
        """Training with single bucket (global_default)."""
        orchestrator = TrainingOrchestrator(
            bucket_resolver=None,
            bucket_profile_id=None,
        )
        
        np.random.seed(42)
        df = pd.DataFrame({
            "timestamp": pd.date_range("2025-11-25", periods=100, freq="h"),
            "value": np.random.normal(100, 10, 100),
        })
        
        result = orchestrator.train_dimension(
            kb_id="test_kb",
            dimension="request_count",
            df_train=df,
        )
        
        assert result["kb_id"] == "test_kb"
        assert result["dimension"] == "request_count"
        assert result["bucket_profile_id"] is None
        assert "global_default" in result["buckets"]
        assert result["buckets"]["global_default"]["mean"] == pytest.approx(100, rel=0.1)
        assert result["global_fallback"] is not None
    
    def test_train_dimension_multiple_buckets(self):
        """Training with multiple buckets."""
        profile = create_workday_weekend_profile()
        resolver = BucketResolver(profile)
        
        orchestrator = TrainingOrchestrator(
            bucket_resolver=resolver,
            bucket_profile_id="test",
        )
        
        # Generate data for full week
        np.random.seed(42)
        dates = pd.date_range("2025-11-24", periods=168, freq="h")  # Full week starting Monday
        values = np.random.normal(100, 10, 168)
        
        df = pd.DataFrame({
            "timestamp": dates,
            "value": values,
        })
        
        result = orchestrator.train_dimension(
            kb_id="test_kb",
            dimension="request_count",
            df_train=df,
        )
        
        assert "workday" in result["buckets"]
        assert "weekend" in result["buckets"]
        # 5 workdays * 24 hours = 120 hours
        assert result["buckets"]["workday"]["data_points"] == 120
        # 2 weekend days * 24 hours = 48 hours
        assert result["buckets"]["weekend"]["data_points"] == 48
    
    def test_train_dimension_empty_df(self):
        """Training with empty DataFrame."""
        orchestrator = TrainingOrchestrator(
            bucket_resolver=None,
            bucket_profile_id=None,
        )
        
        df = pd.DataFrame({"timestamp": [], "value": []})
        
        result = orchestrator.train_dimension(
            kb_id="test_kb",
            dimension="request_count",
            df_train=df,
        )
        
        assert result["buckets"] == {}
        assert result["global_fallback"] is None
    
    def test_train_insufficient_data_uses_fallback(self):
        """Buckets with <3 points use global fallback."""
        profile = create_workday_weekend_profile()
        resolver = BucketResolver(profile)
        
        orchestrator = TrainingOrchestrator(
            bucket_resolver=resolver,
            bucket_profile_id="test",
        )
        
        # Only workday data - weekend will have only 1 point
        df = pd.DataFrame({
            "timestamp": [
                datetime(2025, 11, 24, 10, 0, tzinfo=tz.utc),  # Monday
                datetime(2025, 11, 24, 11, 0, tzinfo=tz.utc),
                datetime(2025, 11, 24, 12, 0, tzinfo=tz.utc),
                datetime(2025, 11, 24, 13, 0, tzinfo=tz.utc),
                datetime(2025, 11, 24, 14, 0, tzinfo=tz.utc),
                datetime(2025, 11, 29, 10, 0, tzinfo=tz.utc),  # Saturday - only 1 point
            ],
            "value": [100, 110, 90, 105, 95, 200],
        })
        
        result = orchestrator.train_dimension(
            kb_id="test_kb",
            dimension="request_count",
            df_train=df,
        )
        
        assert result["buckets"]["workday"]["sufficient_data"] is True
        assert result["buckets"]["weekend"]["sufficient_data"] is False
        # Weekend uses global fallback
        assert result["buckets"]["weekend"]["mean"] == result["global_fallback"]["mean"]


class TestDetectionOrchestrator:
    """Test detection with bucket-aware baseline lookup."""
    
    def test_detect_single_value(self):
        """Detect a single value."""
        baselines = {
            "request_count": {
                "kb_id": "test",
                "dimension": "request_count",
                "bucket_profile_id": None,
                "buckets": {
                    "global_default": {
                        "mean": 100.0,
                        "std": 10.0,
                        "threshold": 2.5,
                        "data_points": 100,
                        "percentile": 99.5,
                    }
                },
                "global_fallback": None,
            }
        }
        
        orchestrator = DetectionOrchestrator(
            bucket_resolver=None,
            baselines=baselines,
        )
        
        # Normal value
        result = orchestrator.detect(
            dimension="request_count",
            timestamp=datetime(2025, 11, 25, 10, 0, tzinfo=tz.utc),
            value=105.0,
        )
        
        assert result["bucket_key"] == "global_default"
        assert result["is_anomaly"] is False
        assert result["z_score"] == pytest.approx(0.5)
    
    def test_detect_anomaly(self):
        """Detect an anomalous value."""
        baselines = {
            "request_count": {
                "buckets": {
                    "global_default": {
                        "mean": 100.0,
                        "std": 10.0,
                        "threshold": 2.0,
                        "data_points": 100,
                        "percentile": 99.5,
                    }
                },
                "global_fallback": None,
            }
        }
        
        orchestrator = DetectionOrchestrator(
            bucket_resolver=None,
            baselines=baselines,
        )
        
        # Anomalous value (z-score = 5.0 > threshold 2.0)
        result = orchestrator.detect(
            dimension="request_count",
            timestamp=datetime(2025, 11, 25, 10, 0, tzinfo=tz.utc),
            value=150.0,
        )
        
        assert result["is_anomaly"] is True
        assert result["z_score"] == pytest.approx(5.0)
    
    def test_detect_missing_dimension(self):
        """Detect with missing dimension returns error."""
        orchestrator = DetectionOrchestrator(
            bucket_resolver=None,
            baselines={},
        )
        
        result = orchestrator.detect(
            dimension="unknown",
            timestamp=datetime(2025, 11, 25, 10, 0, tzinfo=tz.utc),
            value=100.0,
        )
        
        assert "error" in result
        assert result["is_anomaly"] is False
    
    def test_detect_with_bucket_resolver(self):
        """Detect with bucket resolver uses correct bucket."""
        profile = create_workday_weekend_profile()
        resolver = BucketResolver(profile)
        
        baselines = {
            "request_count": {
                "buckets": {
                    "workday": {
                        "mean": 100.0,
                        "std": 10.0,
                        "threshold": 2.0,
                        "data_points": 100,
                        "percentile": 99.5,
                    },
                    "weekend": {
                        "mean": 50.0,  # Different baseline for weekend
                        "std": 5.0,
                        "threshold": 2.0,
                        "data_points": 50,
                        "percentile": 99.5,
                    },
                },
                "global_fallback": None,
            }
        }
        
        orchestrator = DetectionOrchestrator(
            bucket_resolver=resolver,
            baselines=baselines,
        )
        
        # Monday - uses workday baseline
        result = orchestrator.detect(
            dimension="request_count",
            timestamp=datetime(2025, 11, 24, 10, 0, tzinfo=tz.utc),  # Monday
            value=100.0,
        )
        assert result["bucket_key"] == "workday"
        assert result["z_score"] == pytest.approx(0.0)
        
        # Saturday - uses weekend baseline  
        result = orchestrator.detect(
            dimension="request_count",
            timestamp=datetime(2025, 11, 29, 10, 0, tzinfo=tz.utc),  # Saturday
            value=50.0,
        )
        assert result["bucket_key"] == "weekend"
        assert result["z_score"] == pytest.approx(0.0)
    
    def test_detect_missing_bucket_uses_fallback(self):
        """Detection with missing bucket uses global fallback."""
        baselines = {
            "request_count": {
                "buckets": {
                    "workday": {
                        "mean": 100.0,
                        "std": 10.0,
                        "threshold": 2.0,
                        "data_points": 100,
                        "percentile": 99.5,
                    },
                },
                "global_fallback": {
                    "mean": 75.0,
                    "std": 15.0,
                    "threshold": 2.5,
                    "data_points": 200,
                    "percentile": 99.5,
                },
            }
        }
        
        # Create profile with weekend that wasn't trained
        profile = create_workday_weekend_profile()
        resolver = BucketResolver(profile)
        
        orchestrator = DetectionOrchestrator(
            bucket_resolver=resolver,
            baselines=baselines,
        )
        
        # Saturday - weekend bucket not in baselines, uses global_fallback
        result = orchestrator.detect(
            dimension="request_count",
            timestamp=datetime(2025, 11, 29, 10, 0, tzinfo=tz.utc),  # Saturday
            value=75.0,
        )
        
        assert result["bucket_key"] == "weekend"
        assert result["z_score"] == pytest.approx(0.0)  # Uses fallback mean of 75
    
    def test_detect_batch(self):
        """Batch detection."""
        baselines = {
            "request_count": {
                "buckets": {
                    "global_default": {
                        "mean": 100.0,
                        "std": 10.0,
                        "threshold": 2.0,
                        "data_points": 100,
                        "percentile": 99.5,
                    }
                },
                "global_fallback": None,
            }
        }
        
        orchestrator = DetectionOrchestrator(
            bucket_resolver=None,
            baselines=baselines,
        )
        
        df = pd.DataFrame({
            "timestamp": pd.date_range("2025-11-25 10:00", periods=3, freq="h"),
            "value": [100.0, 105.0, 150.0],  # normal, normal, anomaly
        })
        
        results = orchestrator.detect_batch("request_count", df)
        
        assert len(results) == 3
        assert results[0]["is_anomaly"] is False
        assert results[1]["is_anomaly"] is False
        assert results[2]["is_anomaly"] is True


class TestEndToEndOrchestration:
    """End-to-end tests of training and detection."""
    
    def test_train_then_detect(self):
        """Full workflow: train then detect."""
        # Create orchestrator without resolver (global_default)
        train_orch = TrainingOrchestrator(
            bucket_resolver=None,
            bucket_profile_id=None,
        )
        
        # Generate training data
        np.random.seed(42)
        df_train = pd.DataFrame({
            "timestamp": pd.date_range("2025-11-01", periods=500, freq="h"),
            "value": np.random.normal(100, 10, 500),
        })
        
        # Train
        baseline_result = train_orch.train_dimension(
            kb_id="test_kb",
            dimension="request_count",
            df_train=df_train,
        )
        
        # Setup detection
        detect_orch = DetectionOrchestrator(
            bucket_resolver=None,
            baselines={"request_count": baseline_result},
        )
        
        # Normal detection
        result = detect_orch.detect(
            dimension="request_count",
            timestamp=datetime(2025, 11, 25, 10, 0, tzinfo=tz.utc),
            value=105.0,
        )
        assert result["is_anomaly"] is False
        
        # Anomaly detection
        result = detect_orch.detect(
            dimension="request_count",
            timestamp=datetime(2025, 11, 25, 10, 0, tzinfo=tz.utc),
            value=200.0,  # Way outside normal range
        )
        assert result["is_anomaly"] is True
    
    def test_train_then_detect_with_buckets(self):
        """Full workflow with bucket profile."""
        profile = create_workday_weekend_profile("business_hours")
        resolver = BucketResolver(profile)
        
        # Training orchestrator
        train_orch = TrainingOrchestrator(
            bucket_resolver=resolver,
            bucket_profile_id="business_hours",
        )
        
        # Generate training data - different patterns for workday/weekend
        np.random.seed(42)
        dates = pd.date_range("2025-11-03", periods=336, freq="h")  # 2 weeks
        
        # Higher traffic on workdays
        values = []
        for dt in dates:
            if dt.dayofweek < 5:  # Workday
                values.append(np.random.normal(1000, 100, 1)[0])
            else:  # Weekend
                values.append(np.random.normal(500, 50, 1)[0])
        
        df_train = pd.DataFrame({
            "timestamp": dates,
            "value": values,
        })
        
        # Train
        baseline_result = train_orch.train_dimension(
            kb_id="test_kb",
            dimension="request_count",
            df_train=df_train,
        )
        
        # Verify different baselines
        assert baseline_result["buckets"]["workday"]["mean"] > 900
        assert baseline_result["buckets"]["weekend"]["mean"] < 600
        
        # Detection orchestrator
        detect_orch = DetectionOrchestrator(
            bucket_resolver=resolver,
            baselines={"request_count": baseline_result},
        )
        
        # Monday - 1000 is normal
        result = detect_orch.detect(
            dimension="request_count",
            timestamp=datetime(2025, 11, 24, 10, 0, tzinfo=tz.utc),  # Monday
            value=1000.0,
        )
        assert result["bucket_key"] == "workday"
        assert result["is_anomaly"] is False
        
        # Saturday - 1000 is anomaly (weekend expects ~500)
        result = detect_orch.detect(
            dimension="request_count",
            timestamp=datetime(2025, 11, 29, 10, 0, tzinfo=tz.utc),  # Saturday
            value=1000.0,
        )
        assert result["bucket_key"] == "weekend"
        assert result["is_anomaly"] is True
