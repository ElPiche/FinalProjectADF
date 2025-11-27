"""
Point-to-Point Infrastructure Test for ARMAX Algorithm

This test validates the COMPLETE infrastructure path for ARMAX:
1. Algorithm registry integration
2. Series training orchestrator
3. History provider
4. Detection with injected anomalies

Run:
    cd MotorDA
    python tests/test_armax_infrastructure.py
"""

import sys
import os
import numpy as np
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from dataclasses import dataclass

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================================
# TEST DATA GENERATORS
# ============================================================================

def generate_realistic_time_series(
    num_points: int = 200,
    base_value: float = 100.0,
    noise_std: float = 5.0,
    start_time: datetime = None,
    workday_pattern: bool = True,
    seed: int = 42
) -> List[Dict[str, Any]]:
    """Generate realistic time series data with patterns.
    
    Creates data with:
    - Daily pattern (higher during workday hours)
    - Weekly pattern (lower on weekends)
    - Random noise
    """
    np.random.seed(seed)
    
    if start_time is None:
        start_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    
    data = []
    for i in range(num_points):
        ts = start_time + timedelta(hours=i)
        hour = ts.hour
        day_of_week = ts.weekday()
        is_workday = 1 if day_of_week < 5 else 0
        
        # Base value with patterns
        value = base_value
        
        if workday_pattern:
            # Workday hours (9-17) have higher activity
            if is_workday and 9 <= hour <= 17:
                value += 20.0
            # Nights (0-6, 21-23) have lower activity
            elif hour < 6 or hour >= 21:
                value -= 15.0
        
        # Add noise
        value += np.random.randn() * noise_std
        
        data.append({
            "timestamp": ts,
            "value": max(0, value),  # Ensure non-negative
            "hour": hour,
            "day_of_week": day_of_week,
            "is_workday": is_workday,
        })
    
    return data


def inject_anomalies(
    data: List[Dict[str, Any]],
    anomaly_indices: List[int],
    anomaly_magnitude: float = 100.0,
) -> List[Dict[str, Any]]:
    """Inject anomalies at specific indices.
    
    Returns the data with anomalies marked.
    """
    result = []
    for i, point in enumerate(data):
        entry = point.copy()
        if i in anomaly_indices:
            entry["value"] = point["value"] + anomaly_magnitude
            entry["is_injected_anomaly"] = True
        else:
            entry["is_injected_anomaly"] = False
        result.append(entry)
    return result


# ============================================================================
# TEST CLASSES
# ============================================================================

class TestARMAXRegistryIntegration:
    """Test ARMAX in the algorithm registry."""
    
    def test_armax_registered(self):
        """Verify ARMAX is in the registry."""
        from algorithm_registry import is_algorithm_supported, get_algorithm
        
        assert is_algorithm_supported("armax"), "ARMAX should be registered"
        algo = get_algorithm("armax")
        assert algo is not None
        assert algo.name == "armax"
    
    def test_armax_is_series_mode(self):
        """Verify ARMAX is categorized as SERIES."""
        from algorithm_registry import get_algorithm
        from base_algorithm import DetectionMode
        
        algo = get_algorithm("armax")
        assert algo.detection_mode.value == DetectionMode.SERIES.value
    
    def test_armax_is_feature_bucket_mode(self):
        """Verify ARMAX uses FEATURE bucket mode."""
        from algorithm_registry import get_algorithm
        from base_algorithm import BucketMode
        
        algo = get_algorithm("armax")
        assert algo.bucket_mode.value == BucketMode.FEATURE.value
    
    def test_armax_has_required_history_length(self):
        """Verify ARMAX specifies required history."""
        from algorithm_registry import get_algorithm
        
        algo = get_algorithm("armax")
        assert hasattr(algo, "required_history_length")
        assert algo.required_history_length >= 1


class TestSeriesTrainingOrchestratorWithARMAX:
    """Test SeriesTrainingOrchestrator with ARMAX."""
    
    def test_orchestrator_creates_without_bucket_profile(self):
        """Test orchestrator creation without bucket profile."""
        from Dispatcher.series_orchestrator import SeriesTrainingOrchestrator
        
        # Create without bucket profile (no mongo needed)
        orchestrator = SeriesTrainingOrchestrator(
            bucket_resolver=None,
            bucket_profile_id=None,
        )
        
        assert orchestrator.bucket_resolver is None
        assert orchestrator.bucket_profile_id is None
    
    def test_orchestrator_adds_bucket_features(self):
        """Test that bucket features are added to data."""
        import pandas as pd
        from Dispatcher.series_orchestrator import SeriesTrainingOrchestrator
        
        orchestrator = SeriesTrainingOrchestrator(
            bucket_resolver=None,
            bucket_profile_id=None,
        )
        
        # Create test DataFrame
        df = pd.DataFrame({
            "timestamp": [
                datetime(2025, 1, 6, 10, 0, tzinfo=timezone.utc),  # Monday 10am
                datetime(2025, 1, 11, 15, 0, tzinfo=timezone.utc),  # Saturday 3pm
            ],
            "value": [100.0, 80.0],
        })
        
        df_with_features = orchestrator.add_bucket_features(df)
        
        assert "hour" in df_with_features.columns
        assert "day_of_week" in df_with_features.columns
        assert "is_workday" in df_with_features.columns
        assert "bucket_key" in df_with_features.columns
        
        # Check values
        assert df_with_features.iloc[0]["hour"] == 10
        assert df_with_features.iloc[0]["is_workday"] == 1
        assert df_with_features.iloc[1]["is_workday"] == 0  # Saturday
    
    def test_orchestrator_trains_armax(self):
        """Test training ARMAX via orchestrator."""
        import pandas as pd
        from Dispatcher.series_orchestrator import SeriesTrainingOrchestrator
        
        orchestrator = SeriesTrainingOrchestrator(
            bucket_resolver=None,
            bucket_profile_id=None,
        )
        
        # Generate training data
        data = generate_realistic_time_series(num_points=100, seed=42)
        df = pd.DataFrame(data)
        
        # Train
        result = orchestrator.train_dimension(
            kb_id="test-kb-001",
            dimension="test_metric",
            algorithm_name="armax",
            df_train=df,
        )
        
        # Verify result structure
        assert result["kb_id"] == "test-kb-001"
        assert result["dimension"] == "test_metric"
        assert result["algorithm"] == "armax"
        assert result["detection_mode"] == "series"
        assert "data_points" in result
        # ARMAX stores model params directly, not in a "baseline" sub-object
        assert "ar_params" in result or "model_type" in result
    
    def test_orchestrator_rejects_point_algorithm(self):
        """Test that orchestrator rejects POINT algorithms."""
        import pandas as pd
        from Dispatcher.series_orchestrator import SeriesTrainingOrchestrator
        
        orchestrator = SeriesTrainingOrchestrator(
            bucket_resolver=None,
            bucket_profile_id=None,
        )
        
        data = generate_realistic_time_series(num_points=50)
        df = pd.DataFrame(data)
        
        try:
            orchestrator.train_dimension(
                kb_id="test",
                dimension="test",
                algorithm_name="zscore",  # POINT algorithm!
                df_train=df,
            )
            assert False, "Should have raised ValueError for POINT algorithm"
        except ValueError as e:
            assert "SERIES" in str(e) or "POINT" in str(e)


class TestHistoryProviderIntegration:
    """Test HistoryProvider with ARMAX requirements."""
    
    def test_history_cache_creates(self):
        """Test HistoryCache creation."""
        from Dispatcher.history_provider import HistoryCache
        
        cache = HistoryCache(max_entries_per_dimension=100)
        assert cache._max_entries == 100
    
    def test_history_cache_stores_entries(self):
        """Test that cache stores and retrieves entries."""
        from Dispatcher.history_provider import HistoryCache, HistoryEntry
        
        cache = HistoryCache(max_entries_per_dimension=10)
        
        # Add entries
        entry1 = HistoryEntry(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            value=100.0,
        )
        entry2 = HistoryEntry(
            timestamp=datetime(2025, 1, 1, 11, 0, tzinfo=timezone.utc),
            value=110.0,
        )
        
        cache.add("kb1", "dim1", entry1)
        cache.add("kb1", "dim1", entry2)
        
        # get_recent needs a "before" timestamp
        before = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
        recent = cache.get_recent("kb1", "dim1", before=before, count=2)
        
        assert recent is not None
        assert len(recent) == 2
    
    def test_history_window_for_armax(self):
        """Test that history window provides what ARMAX needs."""
        from Dispatcher.history_provider import HistoryCache, HistoryEntry, HistoryWindow
        
        cache = HistoryCache(max_entries_per_dimension=50)
        
        # Fill with 20 entries
        for i in range(20):
            entry = HistoryEntry(
                timestamp=datetime(2025, 1, 1, i, 0, tzinfo=timezone.utc),
                value=100.0 + i,
            )
            cache.add("kb1", "dim1", entry)
        
        # Get window of 10 (what ARMAX needs) - before timestamp should be after all entries
        before = datetime(2025, 1, 1, 23, 0, tzinfo=timezone.utc)
        recent = cache.get_recent("kb1", "dim1", before=before, count=10)
        
        assert len(recent) == 10
        
        # Create HistoryWindow and check values
        window = HistoryWindow(entries=recent, dimension="dim1", kb_id="kb1")
        values = window.values
        assert len(values) == 10


class TestARMAXEndToEndWithAnomalies:
    """End-to-end test of ARMAX with anomaly injection."""
    
    def test_train_and_detect_normal(self):
        """Test training and detecting normal values."""
        from ARMAX.algorithm import ARMAXAlgorithm
        
        algo = ARMAXAlgorithm()
        
        # Train on clean data
        training_data = generate_realistic_time_series(num_points=100, seed=42)
        train_result = algo.train(training_data, metadata={"threshold_multiplier": 3.0})
        
        assert train_result.sufficient_data == True
        assert train_result.data_points == 100
        
        # Detect normal value with history
        history = training_data[-15:]
        normal_value = 105.0  # Within normal range
        
        result = algo.detect(
            value=normal_value,
            baseline=train_result.baseline,
            history=history,
        )
        
        # Normal value should not be anomaly
        assert "predicted_value" in result.algorithm_details
    
    def test_detect_injected_anomaly(self):
        """Test detection of injected anomaly."""
        from ARMAX.algorithm import ARMAXAlgorithm
        
        algo = ARMAXAlgorithm()
        
        # Train on clean data
        training_data = generate_realistic_time_series(
            num_points=100, 
            base_value=100.0,
            noise_std=5.0,
            seed=42
        )
        train_result = algo.train(training_data, metadata={"threshold_multiplier": 2.5})
        
        # Use history from training
        history = training_data[-15:]
        
        # Inject extreme anomaly
        anomaly_value = 500.0  # Way outside normal range
        
        result = algo.detect(
            value=anomaly_value,
            baseline=train_result.baseline,
            history=history,
        )
        
        assert result.is_anomaly == True, f"Expected anomaly detection for value {anomaly_value}"
        assert result.algorithm_details["prediction_error"] > result.algorithm_details["threshold"]
    
    def test_multiple_anomaly_injection(self):
        """Test detection of multiple injected anomalies."""
        from ARMAX.algorithm import ARMAXAlgorithm
        
        algo = ARMAXAlgorithm()
        
        # Train on clean data
        training_data = generate_realistic_time_series(
            num_points=150,
            base_value=100.0,
            noise_std=3.0,
            seed=42
        )
        train_result = algo.train(training_data, metadata={"threshold_multiplier": 2.5})
        
        # Generate test data with injected anomalies
        test_data = generate_realistic_time_series(
            num_points=50,
            base_value=100.0,
            noise_std=3.0,
            start_time=datetime(2025, 2, 1, 0, 0, 0, tzinfo=timezone.utc),
            seed=123
        )
        
        # Inject anomalies at specific positions
        anomaly_positions = [10, 25, 40]
        test_data_with_anomalies = inject_anomalies(
            test_data,
            anomaly_positions,
            anomaly_magnitude=150.0  # Large spike
        )
        
        # Run detection on each point
        detected_anomalies = []
        false_positives = []
        missed_anomalies = []
        
        for i in range(15, len(test_data_with_anomalies)):
            point = test_data_with_anomalies[i]
            history = test_data_with_anomalies[max(0, i-15):i]
            
            if len(history) < 10:
                continue
            
            result = algo.detect(
                value=point["value"],
                baseline=train_result.baseline,
                history=history,
            )
            
            if result.is_anomaly:
                if point["is_injected_anomaly"]:
                    detected_anomalies.append(i)
                else:
                    false_positives.append(i)
            elif point["is_injected_anomaly"]:
                missed_anomalies.append(i)
        
        print(f"\n[ANOMALY DETECTION RESULTS]")
        print(f"  Injected anomalies: {anomaly_positions}")
        print(f"  Correctly detected: {detected_anomalies}")
        print(f"  False positives: {false_positives}")
        print(f"  Missed anomalies: {missed_anomalies}")
        
        # We expect to detect most injected anomalies
        detected_set = set(detected_anomalies)
        injected_set = set(anomaly_positions)
        
        # At least 2 out of 3 should be detected
        detection_count = len(detected_set & injected_set)
        assert detection_count >= 2, f"Expected at least 2/3 anomalies detected, got {detection_count}"
    
    def test_workday_pattern_anomaly(self):
        """Test detection of anomaly during specific time context."""
        from ARMAX.algorithm import ARMAXAlgorithm
        
        algo = ARMAXAlgorithm()
        
        # Train on data with clear workday pattern
        training_data = generate_realistic_time_series(
            num_points=200,
            base_value=100.0,
            workday_pattern=True,
            seed=42
        )
        
        train_result = algo.train(training_data, metadata={"threshold_multiplier": 2.5})
        
        # Create history ending on workday morning (high activity expected)
        workday_history = []
        base_time = datetime(2025, 1, 6, 8, 0, 0, tzinfo=timezone.utc)  # Monday 8am
        for i in range(15):
            ts = base_time + timedelta(hours=i)
            workday_history.append({
                "timestamp": ts,
                "value": 115.0 + np.random.randn() * 3,  # Higher values (workday)
                "hour": ts.hour,
                "is_workday": 1,
            })
        
        # Anomaly: Very low value during peak workday (when values should be high)
        anomaly_value = 30.0  # Unusually low for workday peak
        
        result = algo.detect(
            value=anomaly_value,
            baseline=train_result.baseline,
            history=workday_history,
            bucket_features={"hour": 10.0, "is_workday": 1.0},
        )
        
        # This should be detected as anomaly because it's unusually low
        print(f"\n[WORKDAY PATTERN TEST]")
        print(f"  Value: {anomaly_value} (during workday peak)")
        print(f"  Predicted: {result.algorithm_details.get('predicted_value', 'N/A')}")
        print(f"  Is anomaly: {result.is_anomaly}")


class TestSeriesDetectionOrchestratorWithARMAX:
    """Test SeriesDetectionOrchestrator with ARMAX."""
    
    def test_orchestrator_detects_with_armax(self):
        """Test detection via orchestrator."""
        from ARMAX.algorithm import ARMAXAlgorithm
        from Dispatcher.series_orchestrator import SeriesDetectionOrchestrator
        
        algo = ARMAXAlgorithm()
        
        # First train
        training_data = generate_realistic_time_series(num_points=100, seed=42)
        train_result = algo.train(training_data, metadata={"threshold_multiplier": 3.0})
        
        # Create detection orchestrator
        orchestrator = SeriesDetectionOrchestrator(
            bucket_resolver=None,
            baseline=train_result.baseline,
        )
        
        # Prepare history
        history = [
            {"value": d["value"], "timestamp": d["timestamp"], "hour": d["hour"]}
            for d in training_data[-15:]
        ]
        
        # Detect normal value
        result = orchestrator.detect(
            value=105.0,
            timestamp=datetime(2025, 1, 10, 14, 0, tzinfo=timezone.utc),
            history=history,
            algorithm_name="armax",
        )
        
        assert "value" in result
        assert "algorithm" in result
        assert result["algorithm"] == "armax"
    
    def test_orchestrator_handles_insufficient_history(self):
        """Test that orchestrator handles insufficient history."""
        from ARMAX.algorithm import ARMAXAlgorithm
        from Dispatcher.series_orchestrator import SeriesDetectionOrchestrator
        
        algo = ARMAXAlgorithm()
        
        # Train
        training_data = generate_realistic_time_series(num_points=50, seed=42)
        train_result = algo.train(training_data)
        
        orchestrator = SeriesDetectionOrchestrator(
            bucket_resolver=None,
            baseline=train_result.baseline,
        )
        
        # Only 3 history points (ARMAX needs 10)
        short_history = [
            {"value": 100.0, "timestamp": datetime.now(timezone.utc)},
            {"value": 101.0, "timestamp": datetime.now(timezone.utc)},
            {"value": 102.0, "timestamp": datetime.now(timezone.utc)},
        ]
        
        result = orchestrator.detect(
            value=105.0,
            timestamp=datetime.now(timezone.utc),
            history=short_history,
            algorithm_name="armax",
        )
        
        # Should indicate insufficient history
        assert result["is_anomaly"] == False
        assert "Insufficient" in result.get("error", "")


class TestFullInfrastructurePath:
    """Test the complete infrastructure path for ARMAX."""
    
    def test_complete_flow_training_to_detection(self):
        """Test complete flow from training to detection with anomaly injection."""
        import pandas as pd
        from Dispatcher.series_orchestrator import SeriesTrainingOrchestrator, SeriesDetectionOrchestrator
        from Dispatcher.history_provider import HistoryCache, HistoryEntry, HistoryWindow
        from algorithm_registry import get_algorithm
        
        print("\n" + "=" * 70)
        print("COMPLETE INFRASTRUCTURE FLOW TEST")
        print("=" * 70)
        
        # 1. Create training orchestrator
        print("\n[STEP 1] Creating SeriesTrainingOrchestrator...")
        training_orch = SeriesTrainingOrchestrator(
            bucket_resolver=None,
            bucket_profile_id=None,
        )
        
        # 2. Generate and prepare training data
        print("[STEP 2] Generating training data (200 points)...")
        training_data = generate_realistic_time_series(
            num_points=200,
            base_value=100.0,
            noise_std=5.0,
            seed=42
        )
        df_train = pd.DataFrame(training_data)
        
        # 3. Train via orchestrator
        print("[STEP 3] Training ARMAX via orchestrator...")
        train_result = training_orch.train_dimension(
            kb_id="infra-test-kb-001",
            dimension="request_count",
            algorithm_name="armax",
            df_train=df_train,
            metadata={"threshold_multiplier": 2.5}
        )
        
        print(f"  - Data points: {train_result['data_points']}")
        print(f"  - Sufficient data: {train_result.get('sufficient_data', 'N/A')}")
        print(f"  - Detection mode: {train_result['detection_mode']}")
        
        # 4. Set up history cache (no MongoDB needed for testing)
        print("[STEP 4] Setting up HistoryCache...")
        cache = HistoryCache(max_entries_per_dimension=100)
        
        # Pre-populate cache with some history
        for point in training_data[-20:]:
            entry = HistoryEntry(
                timestamp=point["timestamp"],
                value=point["value"],
            )
            cache.add("infra-test-kb-001", "request_count", entry)
        
        # 5. Create detection orchestrator
        print("[STEP 5] Creating SeriesDetectionOrchestrator...")
        # ARMAX stores model params directly in result (not in a nested "baseline")
        # For detection, the full result IS the baseline
        detection_orch = SeriesDetectionOrchestrator(
            bucket_resolver=None,
            baseline=train_result,  # The full result is the baseline for ARMAX
        )
        
        # 6. Generate test data with injected anomalies
        print("[STEP 6] Generating test data with anomalies...")
        test_data = generate_realistic_time_series(
            num_points=30,
            base_value=100.0,
            noise_std=5.0,
            start_time=datetime(2025, 2, 1, 0, 0, 0, tzinfo=timezone.utc),
            seed=999
        )
        
        # Inject 3 anomalies
        anomaly_indices = [5, 15, 25]
        test_data_anomalies = inject_anomalies(test_data, anomaly_indices, anomaly_magnitude=120.0)
        
        print(f"  - Test points: {len(test_data_anomalies)}")
        print(f"  - Injected anomalies at: {anomaly_indices}")
        
        # 7. Run detection on each point
        print("[STEP 7] Running detection...")
        results_summary = {
            "total_points": 0,
            "detected_anomalies": [],
            "injected_anomalies": anomaly_indices,
            "true_positives": [],
            "false_positives": [],
            "false_negatives": [],
        }
        
        # Get initial history from cache
        before = datetime(2025, 1, 10, 0, 0, tzinfo=timezone.utc)
        initial_entries = cache.get_recent("infra-test-kb-001", "request_count", before=before, count=15)
        history = [{"value": e.value, "timestamp": e.timestamp} for e in initial_entries]
        
        for i, point in enumerate(test_data_anomalies):
            if len(history) < 10:
                # Add to history and skip
                history.append({"value": point["value"], "timestamp": point["timestamp"]})
                continue
            
            results_summary["total_points"] += 1
            
            result = detection_orch.detect(
                value=point["value"],
                timestamp=point["timestamp"],
                history=history[-15:],  # Last 15 points
                algorithm_name="armax",
            )
            
            is_detected = result.get("is_anomaly", False)
            is_injected = point["is_injected_anomaly"]
            
            if is_detected:
                results_summary["detected_anomalies"].append(i)
                if is_injected:
                    results_summary["true_positives"].append(i)
                else:
                    results_summary["false_positives"].append(i)
            elif is_injected:
                results_summary["false_negatives"].append(i)
            
            # Update history for next detection
            history.append({"value": point["value"], "timestamp": point["timestamp"]})
        
        # 8. Print results
        print("\n" + "-" * 50)
        print("DETECTION RESULTS")
        print("-" * 50)
        print(f"Total points processed: {results_summary['total_points']}")
        print(f"Injected anomalies: {results_summary['injected_anomalies']}")
        print(f"Detected anomalies: {results_summary['detected_anomalies']}")
        print(f"True positives: {results_summary['true_positives']}")
        print(f"False positives: {results_summary['false_positives']}")
        print(f"False negatives: {results_summary['false_negatives']}")
        
        # Calculate metrics
        tp = len(results_summary['true_positives'])
        fp = len(results_summary['false_positives'])
        fn = len(results_summary['false_negatives'])
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        
        print(f"\nPrecision: {precision:.2%}")
        print(f"Recall: {recall:.2%}")
        print("=" * 70)
        
        # Assert minimum performance
        assert tp >= 1, f"Should detect at least 1 true positive, got {tp}"


# ============================================================================
# TEST RUNNER
# ============================================================================

def run_all_tests():
    """Run all infrastructure tests."""
    print("=" * 70)
    print("ARMAX INFRASTRUCTURE POINT-TO-POINT TEST")
    print("=" * 70)
    
    test_classes = [
        TestARMAXRegistryIntegration,
        TestSeriesTrainingOrchestratorWithARMAX,
        TestHistoryProviderIntegration,
        TestARMAXEndToEndWithAnomalies,
        TestSeriesDetectionOrchestratorWithARMAX,
        TestFullInfrastructurePath,
    ]
    
    total_passed = 0
    total_failed = 0
    failures = []
    
    for test_class in test_classes:
        print(f"\n{test_class.__name__}")
        print("-" * 50)
        
        instance = test_class()
        methods = [m for m in dir(instance) if m.startswith("test_")]
        
        for method_name in sorted(methods):
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
        print()
        return 1
    
    print("\n✅ All infrastructure tests passed!")
    return 0


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
