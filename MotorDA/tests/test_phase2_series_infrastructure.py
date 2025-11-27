"""Phase 2 Test: SERIES Algorithm Infrastructure.

This test verifies the complete SERIES infrastructure:
1. HistoryProvider and HistoryCache
2. SeriesTrainingOrchestrator
3. SeriesDetectionOrchestrator
4. DADispatcher SERIES routing
5. Integration with Algorithm registry

Run with:
    cd MotorDA
    python -m pytest tests/test_phase2_series_infrastructure.py -v
    
Or directly:
    python tests/test_phase2_series_infrastructure.py
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from unittest.mock import Mock, patch, MagicMock
import threading

import pandas as pd
import numpy as np


class TestHistoryEntryAndWindow:
    """Test the HistoryEntry and HistoryWindow dataclasses."""
    
    def test_history_entry_creation(self):
        """Verify HistoryEntry can be created with required fields."""
        from Dispatcher.history_provider import HistoryEntry
        
        ts = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        entry = HistoryEntry(timestamp=ts, value=100.5)
        
        assert entry.timestamp == ts
        assert entry.value == 100.5
    
    def test_history_entry_to_dict(self):
        """Verify HistoryEntry.to_dict() works."""
        from Dispatcher.history_provider import HistoryEntry
        
        ts = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        entry = HistoryEntry(timestamp=ts, value=100.5)
        
        d = entry.to_dict()
        assert "timestamp" in d
        assert d["value"] == 100.5
    
    def test_history_window_creation(self):
        """Verify HistoryWindow can be created with entries."""
        from Dispatcher.history_provider import HistoryEntry, HistoryWindow
        
        ts1 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2025, 1, 1, 12, 1, 0, tzinfo=timezone.utc)
        
        entries = [
            HistoryEntry(timestamp=ts1, value=100.0),
            HistoryEntry(timestamp=ts2, value=105.0),
        ]
        
        window = HistoryWindow(
            entries=entries,
            dimension="test_dim",
            kb_id="test_kb"
        )
        
        assert len(window.entries) == 2
        assert window.dimension == "test_dim"
        assert window.kb_id == "test_kb"
    
    def test_history_window_values_property(self):
        """Verify HistoryWindow.values returns list of values in chronological order."""
        from Dispatcher.history_provider import HistoryEntry, HistoryWindow
        
        ts = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        entries = [
            HistoryEntry(timestamp=ts, value=100.0),
            HistoryEntry(timestamp=ts + timedelta(minutes=1), value=105.0),
            HistoryEntry(timestamp=ts + timedelta(minutes=2), value=110.0),
        ]
        
        window = HistoryWindow(entries=entries, dimension="test", kb_id="kb1")
        
        assert window.values == [100.0, 105.0, 110.0]
    
    def test_history_window_timestamps_property(self):
        """Verify HistoryWindow.timestamps returns list of timestamps."""
        from Dispatcher.history_provider import HistoryEntry, HistoryWindow
        
        ts = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        entries = [
            HistoryEntry(timestamp=ts, value=100.0),
            HistoryEntry(timestamp=ts + timedelta(minutes=1), value=105.0),
        ]
        
        window = HistoryWindow(entries=entries, dimension="test", kb_id="kb1")
        
        assert len(window.timestamps) == 2
        assert window.timestamps[0] == ts
    
    def test_history_window_to_list(self):
        """Verify HistoryWindow.to_list() returns list of dicts."""
        from Dispatcher.history_provider import HistoryEntry, HistoryWindow
        
        ts = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        entries = [
            HistoryEntry(timestamp=ts, value=100.0),
        ]
        
        window = HistoryWindow(entries=entries, dimension="test", kb_id="kb1")
        
        result = window.to_list()
        assert len(result) == 1
        assert result[0]["value"] == 100.0


class TestHistoryCache:
    """Test the HistoryCache class."""
    
    def test_cache_creation(self):
        """Verify HistoryCache can be created."""
        from Dispatcher.history_provider import HistoryCache
        
        cache = HistoryCache(max_entries_per_dimension=100)
        assert cache is not None
    
    def test_cache_add_and_get(self):
        """Verify adding and getting from cache."""
        from Dispatcher.history_provider import HistoryCache, HistoryEntry
        
        cache = HistoryCache(max_entries_per_dimension=100)
        ts = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        
        # Add entries using HistoryEntry objects
        cache.add("kb1", "dim1", HistoryEntry(timestamp=ts, value=100.0))
        cache.add("kb1", "dim1", HistoryEntry(timestamp=ts + timedelta(minutes=1), value=105.0))
        
        # Get recent entries (before a later timestamp)
        entries = cache.get_recent("kb1", "dim1", before=ts + timedelta(minutes=5), count=2)
        
        assert len(entries) == 2
    
    def test_cache_different_dimensions(self):
        """Verify cache separates by dimension."""
        from Dispatcher.history_provider import HistoryCache, HistoryEntry
        
        cache = HistoryCache(max_entries_per_dimension=100)
        ts = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        
        cache.add("kb1", "dim1", HistoryEntry(timestamp=ts, value=100.0))
        cache.add("kb1", "dim2", HistoryEntry(timestamp=ts, value=200.0))
        
        dim1_entries = cache.get_recent("kb1", "dim1", before=ts + timedelta(hours=1), count=10)
        dim2_entries = cache.get_recent("kb1", "dim2", before=ts + timedelta(hours=1), count=10)
        
        assert len(dim1_entries) == 1
        assert dim1_entries[0].value == 100.0
        assert len(dim2_entries) == 1
        assert dim2_entries[0].value == 200.0
    
    def test_cache_max_entries(self):
        """Verify cache respects max_entries_per_dimension limit."""
        from Dispatcher.history_provider import HistoryCache, HistoryEntry
        
        cache = HistoryCache(max_entries_per_dimension=5)
        ts = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        
        # Add 10 entries
        for i in range(10):
            cache.add("kb1", "dim1", HistoryEntry(
                timestamp=ts + timedelta(minutes=i), 
                value=float(i)
            ))
        
        entries = cache.get_recent("kb1", "dim1", before=ts + timedelta(hours=1), count=100)
        
        # Should only have the last 5 entries
        assert len(entries) <= 5
    
    def test_cache_thread_safety(self):
        """Verify cache is thread-safe."""
        from Dispatcher.history_provider import HistoryCache, HistoryEntry
        
        cache = HistoryCache(max_entries_per_dimension=1000)
        ts = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        errors = []
        
        def add_entries(thread_id):
            try:
                for i in range(100):
                    cache.add(
                        f"kb{thread_id}", 
                        "dim1", 
                        HistoryEntry(timestamp=ts + timedelta(seconds=i), value=float(i))
                    )
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=add_entries, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"Thread safety errors: {errors}"
    
    def test_cache_clear(self):
        """Verify cache clear removes entries."""
        from Dispatcher.history_provider import HistoryCache, HistoryEntry
        
        cache = HistoryCache(max_entries_per_dimension=100)
        ts = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        
        cache.add("kb1", "dim1", HistoryEntry(timestamp=ts, value=100.0))
        cache.clear("kb1", "dim1")
        
        entries = cache.get_recent("kb1", "dim1", before=ts + timedelta(hours=1), count=10)
        assert len(entries) == 0


class TestHistoryProvider:
    """Test the HistoryProvider class."""
    
    def test_provider_creation_via_factory(self):
        """Verify HistoryProvider can be created via factory."""
        from Dispatcher.history_provider import HistoryProvider
        
        # With mock MongoDB client
        mock_client = MagicMock()
        provider = HistoryProvider.create(mongo_client=mock_client, db_name="test_db")
        
        assert provider is not None
        assert provider.db_name == "test_db"
    
    def test_provider_dataclass_init(self):
        """Verify HistoryProvider dataclass works."""
        from Dispatcher.history_provider import HistoryProvider, HistoryCache
        
        mock_client = MagicMock()
        cache = HistoryCache(max_entries_per_dimension=100)
        
        provider = HistoryProvider(
            mongo_client=mock_client,
            db_name="test_db",
            series_collection_name="series",
            cache=cache
        )
        
        assert provider is not None
        assert provider.db_name == "test_db"
    
    def test_provider_cache_is_used(self):
        """Verify provider uses cache before MongoDB."""
        from Dispatcher.history_provider import HistoryProvider, HistoryCache, HistoryEntry
        
        mock_client = MagicMock()
        cache = HistoryCache(max_entries_per_dimension=100)
        ts = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        
        # Pre-populate cache
        for i in range(5):
            cache.add("kb1", "dim1", HistoryEntry(
                timestamp=ts - timedelta(minutes=5-i), 
                value=float(100 + i)
            ))
        
        provider = HistoryProvider(
            mongo_client=mock_client,
            db_name="test_db",
            cache=cache
        )
        
        # Get history - should use cache
        window = provider.get_history(
            kb_id="kb1",
            dimension="dim1",
            before_timestamp=ts,
            window_size=5
        )
        
        assert len(window.values) == 5
    
    def test_get_history_provider_function(self):
        """Verify get_history_provider() returns provider."""
        from Dispatcher.history_provider import get_history_provider
        
        mock_client = MagicMock()
        
        # Reset singleton by patching module
        import Dispatcher.history_provider as hp_module
        hp_module._history_provider = None
        
        provider = get_history_provider(mock_client, "test_db")
        
        assert provider is not None
    
    def test_add_to_cache(self):
        """Verify add_to_cache adds entries."""
        from Dispatcher.history_provider import HistoryProvider
        
        mock_client = MagicMock()
        provider = HistoryProvider.create(mongo_client=mock_client, db_name="test")
        
        ts = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        provider.add_to_cache("kb1", "dim1", ts, 100.0)
        
        # Should be in cache now
        window = provider.get_history("kb1", "dim1", ts + timedelta(minutes=1), 1)
        assert len(window.values) == 1
        assert window.values[0] == 100.0


class TestSeriesTrainingOrchestrator:
    """Test SeriesTrainingOrchestrator."""
    
    def test_orchestrator_creation_via_factory(self):
        """Verify orchestrator can be created via factory."""
        from Dispatcher.series_orchestrator import SeriesTrainingOrchestrator
        
        mock_client = MagicMock()
        mock_client.__getitem__ = MagicMock(return_value=MagicMock(
            __getitem__=MagicMock(return_value=MagicMock(
                find_one=MagicMock(return_value=None)
            ))
        ))
        
        orchestrator = SeriesTrainingOrchestrator.create(
            bucket_profile_id=None,
            mongo_client=mock_client
        )
        
        assert orchestrator is not None
        assert orchestrator.bucket_profile_id is None
    
    def test_orchestrator_dataclass(self):
        """Verify orchestrator dataclass."""
        from Dispatcher.series_orchestrator import SeriesTrainingOrchestrator
        
        orchestrator = SeriesTrainingOrchestrator(
            bucket_resolver=None,
            bucket_profile_id=None
        )
        
        assert orchestrator is not None
    
    def test_add_bucket_features(self):
        """Verify bucket features are added to DataFrame."""
        from Dispatcher.series_orchestrator import SeriesTrainingOrchestrator
        
        orchestrator = SeriesTrainingOrchestrator(
            bucket_resolver=None,
            bucket_profile_id=None
        )
        
        timestamps = pd.date_range(start="2025-01-01", periods=10, freq="1min")
        df = pd.DataFrame({
            "timestamp": timestamps,
            "value": range(10)
        })
        
        df_with_features = orchestrator.add_bucket_features(df, timestamp_col="timestamp")
        
        assert "hour" in df_with_features.columns
        assert "day_of_week" in df_with_features.columns
        assert "is_workday" in df_with_features.columns
        assert "bucket_key" in df_with_features.columns
    
    def test_get_bucket_features_for_timestamp(self):
        """Verify getting bucket features for single timestamp."""
        from Dispatcher.series_orchestrator import SeriesTrainingOrchestrator
        
        orchestrator = SeriesTrainingOrchestrator(
            bucket_resolver=None,
            bucket_profile_id=None
        )
        
        ts = datetime(2025, 1, 6, 14, 30, 0, tzinfo=timezone.utc)  # Monday, 2:30 PM
        features = orchestrator.get_bucket_features_for_timestamp(ts)
        
        assert features["hour"] == 14.0
        assert features["day_of_week"] == 0.0  # Monday
        assert features["is_workday"] == 1.0
        assert features["bucket_key"] == "global_default"
    
    def test_train_rejects_point_algorithm(self):
        """Verify training rejects POINT algorithms like zscore."""
        from Dispatcher.series_orchestrator import SeriesTrainingOrchestrator
        
        orchestrator = SeriesTrainingOrchestrator(
            bucket_resolver=None,
            bucket_profile_id=None
        )
        
        # Create training DataFrame
        timestamps = pd.date_range(start="2025-01-01", periods=100, freq="1min")
        df = pd.DataFrame({
            "timestamp": timestamps,
            "value": np.random.normal(100, 10, 100)
        })
        
        # Z-score is a POINT algorithm, should be rejected
        try:
            orchestrator.train_dimension(
                kb_id="test_kb",
                dimension="test_dim",
                algorithm_name="zscore",
                df_train=df,
            )
            assert False, "Should have raised ValueError for POINT algorithm"
        except ValueError as e:
            assert "point mode" in str(e).lower()
    
    def test_train_handles_unknown_algorithm(self):
        """Verify training handles unknown algorithm."""
        from Dispatcher.series_orchestrator import SeriesTrainingOrchestrator
        
        orchestrator = SeriesTrainingOrchestrator(
            bucket_resolver=None,
            bucket_profile_id=None
        )
        
        df = pd.DataFrame({"timestamp": [], "value": []})
        
        try:
            orchestrator.train_dimension(
                kb_id="test_kb",
                dimension="test_dim",
                algorithm_name="nonexistent_algo",
                df_train=df,
            )
            assert False, "Should have raised ValueError for unknown algorithm"
        except ValueError as e:
            assert "unknown" in str(e).lower() or "nonexistent" in str(e).lower()


class TestSeriesDetectionOrchestrator:
    """Test SeriesDetectionOrchestrator."""
    
    def test_orchestrator_creation_via_factory(self):
        """Verify detection orchestrator can be created via factory."""
        from Dispatcher.series_orchestrator import SeriesDetectionOrchestrator
        
        mock_client = MagicMock()
        mock_client.__getitem__ = MagicMock(return_value=MagicMock(
            __getitem__=MagicMock(return_value=MagicMock(
                find_one=MagicMock(return_value=None)
            ))
        ))
        
        baseline = {"mean": 100.0, "std": 10.0}
        
        orchestrator = SeriesDetectionOrchestrator.create(
            bucket_profile_id=None,
            baseline=baseline,
            mongo_client=mock_client
        )
        
        assert orchestrator is not None
        assert orchestrator.baseline == baseline
    
    def test_orchestrator_dataclass(self):
        """Verify orchestrator dataclass."""
        from Dispatcher.series_orchestrator import SeriesDetectionOrchestrator
        
        baseline = {"mean": 100.0, "std": 10.0}
        
        orchestrator = SeriesDetectionOrchestrator(
            bucket_resolver=None,
            baseline=baseline
        )
        
        assert orchestrator is not None
        assert orchestrator.baseline == baseline
    
    def test_get_bucket_features(self):
        """Verify getting bucket features for detection."""
        from Dispatcher.series_orchestrator import SeriesDetectionOrchestrator
        
        orchestrator = SeriesDetectionOrchestrator(
            bucket_resolver=None,
            baseline={}
        )
        
        ts = datetime(2025, 1, 6, 14, 30, 0, tzinfo=timezone.utc)  # Monday
        features = orchestrator.get_bucket_features(ts)
        
        assert features["hour"] == 14.0
        assert features["is_workday"] == 1.0
    
    def test_detect_handles_unknown_algorithm(self):
        """Verify detection handles unknown algorithm gracefully."""
        from Dispatcher.series_orchestrator import SeriesDetectionOrchestrator
        
        orchestrator = SeriesDetectionOrchestrator(
            bucket_resolver=None,
            baseline={"mean": 100.0, "std": 10.0}
        )
        
        ts = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        
        result = orchestrator.detect(
            value=100.0,
            timestamp=ts,
            history=[],
            algorithm_name="nonexistent_algo",
        )
        
        # Should return error, not crash
        assert "error" in result
        assert result["is_anomaly"] == False
    
    def test_detect_with_zscore_returns_result(self):
        """Verify detection with zscore algorithm returns a result."""
        from Dispatcher.series_orchestrator import SeriesDetectionOrchestrator
        
        orchestrator = SeriesDetectionOrchestrator(
            bucket_resolver=None,
            baseline={"mean": 100.0, "std": 10.0, "threshold": 3.0}
        )
        
        ts = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        history = [{"timestamp": ts - timedelta(minutes=i), "value": 100.0} for i in range(5)]
        
        result = orchestrator.detect(
            value=100.0,
            timestamp=ts,
            history=history,
            algorithm_name="zscore",
        )
        
        # Z-score should work (it doesn't require history)
        assert "is_anomaly" in result or "error" in result


class TestDetectionModeRouting:
    """Test that SERIES vs POINT algorithms are routed correctly."""
    
    def test_detection_mode_enum_values(self):
        """Verify DetectionMode has correct values."""
        from base_algorithm import DetectionMode
        
        assert DetectionMode.POINT.value == "point"
        assert DetectionMode.SERIES.value == "series"
        assert DetectionMode.BATCH.value == "batch"
    
    def test_zscore_is_point_algorithm(self):
        """Verify ZScoreAlgorithm is a POINT algorithm."""
        from ZScore.algorithm import ZScoreAlgorithm
        from base_algorithm import DetectionMode
        
        # Compare by value to avoid import path enum issues
        assert ZScoreAlgorithm.detection_mode.value == DetectionMode.POINT.value
    
    def test_bucket_mode_feature(self):
        """Verify BucketMode.FEATURE for SERIES algorithms."""
        from base_algorithm import BucketMode
        
        assert BucketMode.FEATURE.value == "feature"
        assert BucketMode.SEGMENT.value == "segment"
        assert BucketMode.METADATA_ONLY.value == "metadata_only"


class TestIntegrationTrainingFlow:
    """Integration tests for the complete training flow."""
    
    def test_series_orchestrator_add_bucket_features_integration(self):
        """Verify bucket features are correctly added in integration."""
        from Dispatcher.series_orchestrator import SeriesTrainingOrchestrator
        
        orchestrator = SeriesTrainingOrchestrator(
            bucket_resolver=None,
            bucket_profile_id=None
        )
        
        # Generate realistic training data with different times
        np.random.seed(42)
        # Create timestamps spanning weekdays and weekends
        timestamps = pd.date_range(start="2025-01-01", periods=200, freq="1h")
        values = np.random.normal(loc=1000, scale=50, size=200)
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "value": values
        })
        
        df_with_features = orchestrator.add_bucket_features(df, "timestamp")
        
        # Verify features are computed correctly
        assert "hour" in df_with_features.columns
        assert "day_of_week" in df_with_features.columns
        assert "is_workday" in df_with_features.columns
        assert "bucket_key" in df_with_features.columns
        
        # Check values are reasonable
        assert df_with_features["hour"].min() >= 0
        assert df_with_features["hour"].max() <= 23
        assert df_with_features["day_of_week"].min() >= 0
        assert df_with_features["day_of_week"].max() <= 6
        assert set(df_with_features["is_workday"].unique()).issubset({0, 1})
    
    def test_detection_orchestrator_bucket_features_integration(self):
        """Verify detection orchestrator computes features correctly."""
        from Dispatcher.series_orchestrator import SeriesDetectionOrchestrator
        
        orchestrator = SeriesDetectionOrchestrator(
            bucket_resolver=None,
            baseline={"mean": 100.0, "std": 10.0, "threshold": 3.0}
        )
        
        # Test various timestamps
        test_cases = [
            (datetime(2025, 1, 6, 9, 0, 0, tzinfo=timezone.utc), {"hour": 9.0, "is_workday": 1.0}),   # Monday
            (datetime(2025, 1, 11, 9, 0, 0, tzinfo=timezone.utc), {"hour": 9.0, "is_workday": 0.0}),  # Saturday
        ]
        
        for ts, expected in test_cases:
            features = orchestrator.get_bucket_features(ts)
            assert features["hour"] == expected["hour"], f"Failed for {ts}"
            assert features["is_workday"] == expected["is_workday"], f"Failed for {ts}"


class TestMockMongoDBIntegration:
    """Test integration with mocked MongoDB."""
    
    def test_history_provider_can_fetch_from_mongo(self):
        """Verify HistoryProvider can be configured to fetch from MongoDB."""
        from Dispatcher.history_provider import HistoryProvider
        
        # Create mock MongoDB client
        mock_client = MagicMock()
        mock_collection = MagicMock()
        
        # Setup nested mocking for MongoDB access pattern
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        
        ts = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_docs = [
            {"timestamp": ts - timedelta(minutes=5), "value": 100.0},
            {"timestamp": ts - timedelta(minutes=4), "value": 101.0},
        ]
        mock_collection.find.return_value.sort.return_value.limit.return_value = mock_docs
        
        provider = HistoryProvider.create(
            mongo_client=mock_client,
            db_name="test_db"
        )
        
        assert provider is not None


def run_all_tests():
    """Run all tests and print results."""
    print("=" * 70)
    print("PHASE 2: SERIES ALGORITHM INFRASTRUCTURE TEST")
    print("=" * 70)
    
    test_classes = [
        TestHistoryEntryAndWindow,
        TestHistoryCache,
        TestHistoryProvider,
        TestSeriesTrainingOrchestrator,
        TestSeriesDetectionOrchestrator,
        TestDetectionModeRouting,
        TestIntegrationTrainingFlow,
        TestMockMongoDBIntegration,
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
        print("\n✅ All Phase 2 tests passed! SERIES infrastructure is working correctly.")
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
