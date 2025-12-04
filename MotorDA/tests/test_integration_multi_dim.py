#!/usr/bin/env python3
"""
Phase 8: Integration Tests for Multi-Dimensional Algorithm Implementation

Tests cover:
1. End-to-end single-dimensional training and detection
2. Observation buffering and completion
3. Incomplete observation discard behavior
4. Multiple KBWorkers in parallel (mocked)
5. Training result persistence format
"""
import sys
import pytest
import time
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch
from typing import Dict, Any, List

# Add parent path for imports when running directly
sys.path.insert(0, '/app')

from MotorDA.Dispatcher.algorithm_interface import get_algorithm, list_algorithms
from MotorDA.Dispatcher.training_orchestrator import TrainingOrchestrator, DetectionOrchestrator
from MotorDA.Dispatcher.kb_worker import ObservationBuffer, KBWorker, DispatcherManager


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_training_data():
    """Generate sample training data for tests."""
    base_time = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
    return [
        {"timestamp": base_time.replace(hour=10), "cpu": 45.0, "memory": 1024.0, "requests": 100},
        {"timestamp": base_time.replace(hour=11), "cpu": 50.0, "memory": 1100.0, "requests": 120},
        {"timestamp": base_time.replace(hour=12), "cpu": 55.0, "memory": 1200.0, "requests": 150},
        {"timestamp": base_time.replace(hour=13), "cpu": 48.0, "memory": 1050.0, "requests": 110},
        {"timestamp": base_time.replace(hour=14), "cpu": 52.0, "memory": 1150.0, "requests": 130},
    ]


@pytest.fixture
def sample_parameters():
    """Sample algorithm parameters."""
    return [
        {"dimension": "cpu", "is_active": True},
        {"dimension": "memory", "is_active": True},
        {"dimension": "requests", "is_active": True},
    ]


@pytest.fixture
def sample_kb_config():
    """Sample KB configuration."""
    return {
        "_id": "test_config_001",
        "name": "Test Config",
        "algorithm": {
            "name": "zscore",
            "parameters": [
                {"dimension": "cpu", "is_active": True},
                {"dimension": "memory", "is_active": True},
            ]
        },
        "query_mode": {
            "timestamp_field": "timestamp"
        },
        "scheduling": {
            "detection_config": {"is_active": True}
        }
    }


# =============================================================================
# Test 1: End-to-End Single-Dimensional Training & Detection
# =============================================================================

class TestEndToEndSingleDimensional:
    """Test complete training and detection workflow for single-dimensional algorithm."""
    
    def test_train_then_detect_normal(self, sample_training_data, sample_parameters):
        """Train model and detect normal observation."""
        
        # Train
        train_orchestrator = TrainingOrchestrator(
            algorithm_name="zscore",
            parameters=sample_parameters,
            bucket_profile=None,
            is_multi_dimensional=False
        )
        
        training_result = train_orchestrator.train(
            observed_values=sample_training_data,
            timestamp_field="timestamp"
        )
        
        # Verify training result structure
        assert "algorithm" in training_result
        assert training_result["algorithm"] == "zscore"
        assert "is_multi_dimensional" in training_result
        assert training_result["is_multi_dimensional"] is False
        assert "global_fallback" in training_result
        assert "buckets" in training_result
        
        # Detect
        detect_orchestrator = DetectionOrchestrator(
            algorithm_name="zscore",
            parameters=sample_parameters,
            training_result=training_result,
            bucket_profile=None,
            is_multi_dimensional=False
        )
        
        # Normal observation (within training range)
        normal_obs = {
            "timestamp": datetime(2025, 1, 1, 15, 0, tzinfo=timezone.utc),
            "cpu": 50.0,
            "memory": 1100.0,
            "requests": 120.0
        }
        
        result = detect_orchestrator.detect(normal_obs, timestamp_field="timestamp")
        
        # Should not be anomaly
        assert "is_anomaly" in result
        assert result["is_anomaly"] is False
        assert "dimensions" in result
        assert "cpu" in result["dimensions"]
        assert "memory" in result["dimensions"]
        assert "requests" in result["dimensions"]
    
    def test_train_then_detect_anomaly(self, sample_training_data, sample_parameters):
        """Train model and detect anomalous observation."""
        
        # Train
        train_orchestrator = TrainingOrchestrator(
            algorithm_name="zscore",
            parameters=sample_parameters,
            bucket_profile=None,
            is_multi_dimensional=False
        )
        
        training_result = train_orchestrator.train(
            observed_values=sample_training_data,
            timestamp_field="timestamp"
        )
        
        # Detect
        detect_orchestrator = DetectionOrchestrator(
            algorithm_name="zscore",
            parameters=sample_parameters,
            training_result=training_result,
            bucket_profile=None,
            is_multi_dimensional=False
        )
        
        # Anomalous observation (extreme values)
        anomaly_obs = {
            "timestamp": datetime(2025, 1, 1, 15, 0, tzinfo=timezone.utc),
            "cpu": 500.0,  # Way outside normal range
            "memory": 10000.0,  # Way outside normal range
            "requests": 5000.0  # Way outside normal range
        }
        
        result = detect_orchestrator.detect(anomaly_obs, timestamp_field="timestamp")
        
        # Should be anomaly
        assert result["is_anomaly"] is True


# =============================================================================
# Test 2: Observation Buffer Behavior
# =============================================================================

class TestObservationBuffer:
    """Test observation buffering for multi-dimensional assembly."""
    
    def test_buffer_collects_dimensions(self):
        """Buffer should collect dimensions until complete."""
        
        buffer = ObservationBuffer(
            expected_dimensions={"cpu", "memory", "requests"}
        )
        
        ts = "2025-01-01T10:00:00Z"
        
        # Add first dimension
        result = buffer.add_dimension(ts, "cpu", 45.0)
        assert result is None  # Not complete yet
        
        # Add second dimension
        result = buffer.add_dimension(ts, "memory", 1024.0)
        assert result is None  # Not complete yet
        
        # Add third dimension - should complete
        result = buffer.add_dimension(ts, "requests", 100)
        assert result is not None
        assert result["cpu"] == 45.0
        assert result["memory"] == 1024.0
        assert result["requests"] == 100
        assert result["timestamp"] == ts
    
    def test_buffer_handles_multiple_timestamps(self):
        """Buffer should track multiple timestamps independently."""
        
        buffer = ObservationBuffer(
            expected_dimensions={"cpu", "memory"}
        )
        
        ts1 = "2025-01-01T10:00:00Z"
        ts2 = "2025-01-01T11:00:00Z"
        
        # Interleaved dimension arrivals
        buffer.add_dimension(ts1, "cpu", 45.0)
        buffer.add_dimension(ts2, "cpu", 50.0)
        buffer.add_dimension(ts1, "memory", 1024.0)  # ts1 should complete
        
        # ts1 is complete, ts2 still buffered
        assert len(buffer.buffer) == 1
        assert ts2 in buffer.buffer
    
    def test_buffer_cleanup_stale(self):
        """Buffer should discard stale incomplete entries."""
        
        buffer = ObservationBuffer(
            expected_dimensions={"cpu", "memory", "requests"}
        )
        
        ts = "2025-01-01T10:00:00Z"
        
        # Add partial observation
        buffer.add_dimension(ts, "cpu", 45.0)
        buffer.add_dimension(ts, "memory", 1024.0)
        # Missing: requests
        
        # Manually set first_seen to be old
        buffer.buffer[ts]["_first_seen"] = time.time() - 1.0  # 1 second old
        
        # Cleanup with 500ms timeout
        discarded = buffer.cleanup_stale(timeout_ms=500)
        
        # Should have discarded the entry
        assert len(discarded) == 1
        assert discarded[0]["timestamp"] == ts
        assert "requests" in discarded[0]["missing_dims"]
        
        # Buffer should be empty
        assert len(buffer.buffer) == 0
    
    def test_buffer_complete_observation_removed(self):
        """Completed observation should be removed from buffer."""
        
        buffer = ObservationBuffer(
            expected_dimensions={"cpu", "memory"}
        )
        
        ts = "2025-01-01T10:00:00Z"
        
        buffer.add_dimension(ts, "cpu", 45.0)
        buffer.add_dimension(ts, "memory", 1024.0)
        
        # After completion, buffer should be empty
        assert len(buffer.buffer) == 0


# =============================================================================
# Test 3: Incomplete Observation Discard Behavior
# =============================================================================

class TestIncompleteObservationDiscard:
    """Test that incomplete observations are properly discarded (not processed).
    
    This is CRITICAL for avoiding false positives in multi-dimensional algorithms.
    """
    
    def test_partial_observation_not_processed(self):
        """Partial observations should be discarded, not processed."""
        
        buffer = ObservationBuffer(
            expected_dimensions={"cpu", "memory", "requests"}
        )
        
        ts = "2025-01-01T10:00:00Z"
        
        # Only add 2 of 3 dimensions
        buffer.add_dimension(ts, "cpu", 45.0)
        result = buffer.add_dimension(ts, "memory", 1024.0)
        
        # Should NOT return an observation (incomplete)
        assert result is None
        
        # Verify it's still in buffer waiting
        assert ts in buffer.buffer
        assert len(buffer.buffer[ts]["_dims"]) == 2
    
    def test_discard_logs_missing_dimensions(self):
        """Discarded entries should log which dimensions were missing."""
        
        buffer = ObservationBuffer(
            expected_dimensions={"cpu", "memory", "requests"}
        )
        
        ts = "2025-01-01T10:00:00Z"
        buffer.add_dimension(ts, "cpu", 45.0)
        buffer.buffer[ts]["_first_seen"] = time.time() - 1.0
        
        discarded = buffer.cleanup_stale(timeout_ms=500)
        
        # Verify missing dimensions reported
        assert len(discarded) == 1
        assert set(discarded[0]["missing_dims"]) == {"memory", "requests"}
        assert discarded[0]["received_dims"] == ["cpu"]


# =============================================================================
# Test 4: Training Result Format
# =============================================================================

class TestTrainingResultFormat:
    """Test training result structure and metadata."""
    
    def test_training_result_contains_required_fields(self, sample_training_data, sample_parameters):
        """Training result should contain all required fields."""
        
        orchestrator = TrainingOrchestrator(
            algorithm_name="zscore",
            parameters=sample_parameters,
            bucket_profile=None,
            is_multi_dimensional=False
        )
        
        result = orchestrator.train(
            observed_values=sample_training_data,
            timestamp_field="timestamp"
        )
        
        # Required top-level fields
        assert "algorithm" in result
        assert "is_multi_dimensional" in result
        assert "buckets" in result
        assert "global_fallback" in result
        assert "n_total_observations" in result
        assert "parameters" in result
        
        # Verify types
        assert isinstance(result["algorithm"], str)
        assert isinstance(result["is_multi_dimensional"], bool)
        assert isinstance(result["buckets"], dict)
        assert isinstance(result["global_fallback"], dict)
        assert isinstance(result["n_total_observations"], int)
    
    def test_models_have_bucket_context(self, sample_training_data, sample_parameters):
        """All models should have bucket_context tag."""
        
        orchestrator = TrainingOrchestrator(
            algorithm_name="zscore",
            parameters=sample_parameters,
            bucket_profile=None,
            is_multi_dimensional=False
        )
        
        result = orchestrator.train(
            observed_values=sample_training_data,
            timestamp_field="timestamp"
        )
        
        # Check global fallback models
        for dim, model in result["global_fallback"].items():
            assert "bucket_context" in model
        
        # Check bucket models
        for bucket_key, bucket_data in result["buckets"].items():
            models = bucket_data.get("models", {})
            for dim, model in models.items():
                assert "bucket_context" in model


# =============================================================================
# Test 5: KBWorker Initialization (Mocked MongoDB)
# =============================================================================

class TestKBWorkerInitialization:
    """Test KBWorker initialization and configuration."""
    
    def test_worker_extracts_expected_dimensions(self, sample_kb_config):
        """Worker should extract expected dimensions from parameters."""
        
        training_result = {
            "algorithm": "zscore",
            "is_multi_dimensional": False,
            "buckets": {},
            "global_fallback": {"cpu": {"mean": 50}, "memory": {"mean": 1000}}
        }
        
        mock_client = MagicMock()
        
        worker = KBWorker(
            kb_id="test_001",
            kb_config=sample_kb_config,
            training_result=training_result,
            mongo_client=mock_client
        )
        
        # Should have extracted dimensions
        assert worker._buffer is not None
        assert worker._buffer.expected_dimensions == {"cpu", "memory"}
        assert worker.is_multi_dimensional is False
    
    def test_worker_creates_detection_orchestrator(self, sample_kb_config):
        """Worker should create DetectionOrchestrator with correct parameters."""
        
        training_result = {
            "algorithm": "zscore",
            "is_multi_dimensional": False,
            "buckets": {},
            "global_fallback": {"cpu": {"mean": 50}, "memory": {"mean": 1000}}
        }
        
        mock_client = MagicMock()
        
        worker = KBWorker(
            kb_id="test_001",
            kb_config=sample_kb_config,
            training_result=training_result,
            mongo_client=mock_client
        )
        
        # Should have created orchestrator
        assert worker._detection_orchestrator is not None
        assert worker._detection_orchestrator.algorithm_name == "zscore"
        assert worker._detection_orchestrator.is_multi_dimensional is False


# =============================================================================
# Test 6: Algorithm Mode Consistency
# =============================================================================

class TestAlgorithmModeConsistency:
    """Test that algorithm mode is consistent through the pipeline."""
    
    def test_zscore_mode_consistent(self, sample_training_data):
        """ZScore should be single-dimensional throughout."""
        
        params = [{"dimension": "cpu", "is_active": True}]
        
        # Training
        train_orch = TrainingOrchestrator(
            algorithm_name="zscore",
            parameters=params,
            bucket_profile=None,
            is_multi_dimensional=False
        )
        
        training_result = train_orch.train(
            observed_values=sample_training_data,
            timestamp_field="timestamp"
        )
        
        assert training_result["is_multi_dimensional"] is False
        
        # Detection
        detect_orch = DetectionOrchestrator(
            algorithm_name="zscore",
            parameters=params,
            training_result=training_result,
            bucket_profile=None,
            is_multi_dimensional=False
        )
        
        assert detect_orch.is_multi_dimensional is False
    
    def test_iqr_mode_consistent(self, sample_training_data):
        """IQR should be single-dimensional throughout."""
        
        params = [{"dimension": "cpu", "is_active": True}]
        
        # Training
        train_orch = TrainingOrchestrator(
            algorithm_name="iqr",
            parameters=params,
            bucket_profile=None,
            is_multi_dimensional=False
        )
        
        training_result = train_orch.train(
            observed_values=sample_training_data,
            timestamp_field="timestamp"
        )
        
        assert training_result["is_multi_dimensional"] is False


# =============================================================================
# Test 7: Multiple Dimensions Detected Correctly
# =============================================================================

class TestMultipleDimensionDetection:
    """Test detection with multiple dimensions."""
    
    def test_anomaly_in_one_dimension_detected(self, sample_training_data):
        """Anomaly in one dimension should flag entire observation."""
        
        params = [
            {"dimension": "cpu", "is_active": True},
            {"dimension": "memory", "is_active": True},
        ]
        
        # Train
        train_orch = TrainingOrchestrator(
            algorithm_name="zscore",
            parameters=params,
            bucket_profile=None,
            is_multi_dimensional=False
        )
        
        training_result = train_orch.train(
            observed_values=sample_training_data,
            timestamp_field="timestamp"
        )
        
        # Detect
        detect_orch = DetectionOrchestrator(
            algorithm_name="zscore",
            parameters=params,
            training_result=training_result,
            bucket_profile=None,
            is_multi_dimensional=False
        )
        
        # One normal, one anomalous
        obs = {
            "timestamp": datetime(2025, 1, 1, 15, 0, tzinfo=timezone.utc),
            "cpu": 50.0,  # Normal
            "memory": 100000.0  # Anomalous
        }
        
        result = detect_orch.detect(obs, timestamp_field="timestamp")
        
        # Should be anomaly (due to memory)
        assert result["is_anomaly"] is True
        assert result["dimensions"]["cpu"]["is_anomaly"] is False
        assert result["dimensions"]["memory"]["is_anomaly"] is True


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
