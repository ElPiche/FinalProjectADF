"""
Log Generator Unit Tests

Tests the log generator infrastructure without Docker dependencies.

Run:
    cd MotorDA
    python tests/test_log_generator.py
"""

import sys
import os
from datetime import datetime, timedelta, timezone

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestValuePatterns:
    """Test value generation patterns."""
    
    def test_constant_pattern(self):
        from tests.log_generator.patterns import ConstantPattern
        
        pattern = ConstantPattern(value="test_value")
        ts = datetime.now(timezone.utc)
        
        assert pattern.generate(ts) == "test_value"
        assert pattern.generate(ts) == "test_value"  # Always same
    
    def test_random_pattern_int(self):
        from tests.log_generator.patterns import RandomPattern
        
        pattern = RandomPattern(min_value=1, max_value=100, value_type="int")
        ts = datetime.now(timezone.utc)
        
        for _ in range(100):
            value = pattern.generate(ts)
            assert isinstance(value, int)
            assert 1 <= value <= 100
    
    def test_random_pattern_float(self):
        from tests.log_generator.patterns import RandomPattern
        
        pattern = RandomPattern(min_value=0.0, max_value=1.0, value_type="float")
        ts = datetime.now(timezone.utc)
        
        for _ in range(100):
            value = pattern.generate(ts)
            assert isinstance(value, float)
            assert 0.0 <= value <= 1.0
    
    def test_choice_pattern(self):
        from tests.log_generator.patterns import ChoicePattern
        
        choices = [200, 404, 500]
        pattern = ChoicePattern(choices=choices)
        ts = datetime.now(timezone.utc)
        
        for _ in range(100):
            value = pattern.generate(ts)
            assert value in choices
    
    def test_choice_pattern_weighted(self):
        from tests.log_generator.patterns import ChoicePattern
        import random
        
        random.seed(42)
        pattern = ChoicePattern(
            choices=["A", "B"],
            weights=[0.9, 0.1]
        )
        ts = datetime.now(timezone.utc)
        
        counts = {"A": 0, "B": 0}
        for _ in range(1000):
            value = pattern.generate(ts)
            counts[value] += 1
        
        # A should be much more common
        assert counts["A"] > counts["B"] * 5
    
    def test_time_series_pattern_base(self):
        from tests.log_generator.patterns import TimeSeriesPattern
        
        pattern = TimeSeriesPattern(base_value=100.0, noise_std=0.0)
        ts = datetime.now(timezone.utc)
        
        value = pattern.generate(ts)
        assert value == 100.0
    
    def test_time_series_pattern_daily(self):
        from tests.log_generator.patterns import TimeSeriesPattern
        
        pattern = TimeSeriesPattern(
            base_value=100.0,
            noise_std=0.0,
            daily_pattern={"9": 2.0, "21": 0.5}
        )
        
        morning = datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc)
        night = datetime(2025, 1, 1, 21, 0, tzinfo=timezone.utc)
        
        assert pattern.generate(morning) == 200.0  # 100 * 2.0
        assert pattern.generate(night) == 50.0     # 100 * 0.5
    
    def test_time_series_pattern_anomaly(self):
        from tests.log_generator.patterns import TimeSeriesPattern
        
        pattern = TimeSeriesPattern(
            base_value=100.0,
            noise_std=0.0,
            anomaly_probability=0.0,  # Disabled by default
            anomaly_multiplier=10.0,
        )
        
        ts = datetime.now(timezone.utc)
        context = {"force_anomaly": True}
        
        value = pattern.generate(ts, context)
        # Should be much higher or lower than 100
        assert abs(value - 100.0) > 500
        assert context.get("is_anomaly") == True
    
    def test_sequence_pattern(self):
        from tests.log_generator.patterns import SequencePattern
        
        pattern = SequencePattern(start=1, step=1, prefix="ID-")
        ts = datetime.now(timezone.utc)
        
        assert pattern.generate(ts) == "ID-1"
        assert pattern.generate(ts) == "ID-2"
        assert pattern.generate(ts) == "ID-3"
    
    def test_template_pattern(self):
        from tests.log_generator.patterns import TemplatePattern
        
        pattern = TemplatePattern(
            template="{client_ip} requested {path} at {hour}:{minute}",
        )
        
        ts = datetime(2025, 1, 1, 14, 30, tzinfo=timezone.utc)
        context = {"client_ip": "192.168.1.1", "path": "/api/users"}
        
        result = pattern.generate(ts, context)
        assert "192.168.1.1" in result
        assert "/api/users" in result
        assert "14" in result
    
    def test_pattern_serialization(self):
        from tests.log_generator.patterns import (
            ValuePattern, ConstantPattern, RandomPattern, TimeSeriesPattern
        )
        
        patterns = [
            ConstantPattern(value="test"),
            RandomPattern(min_value=1, max_value=10),
            TimeSeriesPattern(base_value=50, daily_pattern={"12": 1.5}),
        ]
        
        for pattern in patterns:
            serialized = pattern.to_dict()
            restored = ValuePattern.from_dict(serialized)
            
            assert type(restored) == type(pattern)
            assert restored.to_dict() == serialized


class TestLogSchema:
    """Test log schema definition."""
    
    def test_schema_creation(self):
        from tests.log_generator.log_schema import LogSchema, FieldDefinition, FieldType
        from tests.log_generator.patterns import ConstantPattern
        
        schema = LogSchema(
            name="test_schema",
            index_name="test-index",
            fields=[
                FieldDefinition(
                    name="status",
                    field_type=FieldType.INTEGER,
                    pattern=ConstantPattern(value=200),
                )
            ]
        )
        
        assert schema.name == "test_schema"
        assert schema.index_name == "test-index"
        assert len(schema.fields) == 1
    
    def test_schema_generate_document(self):
        from tests.log_generator.log_schema import LogSchema, FieldDefinition, FieldType
        from tests.log_generator.patterns import ConstantPattern, RandomPattern
        
        schema = LogSchema(
            name="test",
            timestamp_field="@timestamp",
            fields=[
                FieldDefinition(
                    name="status",
                    field_type=FieldType.INTEGER,
                    pattern=ConstantPattern(value=200),
                ),
                FieldDefinition(
                    name="bytes",
                    field_type=FieldType.INTEGER,
                    pattern=RandomPattern(min_value=100, max_value=1000, value_type="int"),
                ),
            ]
        )
        
        ts = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
        doc = schema.generate_document(ts)
        
        assert "@timestamp" in doc
        assert doc["status"] == 200
        assert 100 <= doc["bytes"] <= 1000
    
    def test_schema_nested_fields(self):
        from tests.log_generator.log_schema import LogSchema, FieldDefinition, FieldType
        from tests.log_generator.patterns import ConstantPattern
        
        schema = LogSchema(
            name="nested_test",
            fields=[
                FieldDefinition(
                    name="geo.country",
                    field_type=FieldType.STRING,
                    pattern=ConstantPattern(value="US"),
                ),
                FieldDefinition(
                    name="geo.city",
                    field_type=FieldType.STRING,
                    pattern=ConstantPattern(value="NYC"),
                ),
            ]
        )
        
        ts = datetime.now(timezone.utc)
        doc = schema.generate_document(ts)
        
        assert "geo" in doc
        assert doc["geo"]["country"] == "US"
        assert doc["geo"]["city"] == "NYC"
    
    def test_schema_es_mapping(self):
        from tests.log_generator.log_schema import LogSchema, FieldDefinition, FieldType
        from tests.log_generator.patterns import ConstantPattern
        
        schema = LogSchema(
            name="mapping_test",
            timestamp_field="@timestamp",
            fields=[
                FieldDefinition(
                    name="status",
                    field_type=FieldType.INTEGER,
                    pattern=ConstantPattern(value=200),
                ),
            ]
        )
        
        mapping = schema.get_es_mapping()
        
        assert "mappings" in mapping
        assert "properties" in mapping["mappings"]
        assert "@timestamp" in mapping["mappings"]["properties"]
        assert mapping["mappings"]["properties"]["status"]["type"] == "integer"
    
    def test_prebuilt_http_schema(self):
        from tests.log_generator.log_schema import create_http_access_schema
        
        schema = create_http_access_schema(index_name="my-http-logs")
        
        assert schema.name == "http_access_logs"
        assert schema.index_name == "my-http-logs"
        
        field_names = [f.name for f in schema.fields]
        assert "response" in field_names
        assert "bytes" in field_names
        assert "method" in field_names
    
    def test_prebuilt_aggregated_schema(self):
        from tests.log_generator.log_schema import create_aggregated_metrics_schema
        
        schema = create_aggregated_metrics_schema()
        
        field_names = [f.name for f in schema.fields]
        assert "request_count" in field_names
        assert "error_count" in field_names


class TestLogGenerator:
    """Test log generation."""
    
    def test_generator_single(self):
        from tests.log_generator.log_schema import create_simple_metrics_schema
        from tests.log_generator.log_generator import LogGenerator
        
        schema = create_simple_metrics_schema()
        generator = LogGenerator(schema, seed=42)
        
        ts = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
        doc = generator.generate_single(ts)
        
        assert "@timestamp" in doc
        assert "value" in doc
    
    def test_generator_batch(self):
        from tests.log_generator.log_schema import create_simple_metrics_schema
        from tests.log_generator.log_generator import LogGenerator
        
        schema = create_simple_metrics_schema()
        generator = LogGenerator(schema, seed=42)
        
        result = generator.generate_batch(
            start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2025, 1, 2, tzinfo=timezone.utc),
            count=100,
        )
        
        assert result.total_count == 100
        assert len(result.documents) == 100
    
    def test_generator_with_anomalies(self):
        from tests.log_generator.log_schema import create_simple_metrics_schema
        from tests.log_generator.log_generator import LogGenerator
        
        schema = create_simple_metrics_schema()
        generator = LogGenerator(schema, seed=42)
        
        anomaly_time = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
        
        result = generator.generate_with_anomalies(
            start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2025, 1, 2, tzinfo=timezone.utc),
            normal_count=100,
            anomaly_times=[anomaly_time],
        )
        
        assert result.total_count == 101  # 100 normal + 1 anomaly
        assert result.anomaly_count == 1
        assert len(result.anomaly_indices) == 1
    
    def test_generator_hourly_buckets(self):
        from tests.log_generator.log_schema import create_aggregated_metrics_schema
        from tests.log_generator.log_generator import LogGenerator
        
        schema = create_aggregated_metrics_schema()
        generator = LogGenerator(schema, seed=42)
        
        result = generator.generate_hourly_buckets(
            start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2025, 1, 2, tzinfo=timezone.utc),
            anomaly_hours=[12],  # Anomaly at noon
        )
        
        assert result.total_count == 24  # 24 hours
        assert result.anomaly_count == 1
        
        # Check timestamps are hourly
        for i, doc in enumerate(result.documents):
            ts_str = doc["@timestamp"]
            assert ":00:00" in ts_str


class TestSchemaSerialize:
    """Test schema serialization."""
    
    def test_schema_to_dict_and_back(self):
        from tests.log_generator.log_schema import (
            LogSchema, FieldDefinition, FieldType,
            create_http_access_schema
        )
        
        original = create_http_access_schema()
        
        serialized = original.to_dict()
        restored = LogSchema.from_dict(serialized)
        
        assert restored.name == original.name
        assert restored.index_name == original.index_name
        assert len(restored.fields) == len(original.fields)


# ============================================================================
# TEST RUNNER
# ============================================================================

def run_all_tests():
    """Run all log generator tests."""
    print("=" * 70)
    print("LOG GENERATOR UNIT TESTS")
    print("=" * 70)
    
    test_classes = [
        TestValuePatterns,
        TestLogSchema,
        TestLogGenerator,
        TestSchemaSerialize,
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
                print(f"  [PASS] {method_name}")
                total_passed += 1
            except Exception as e:
                print(f"  [FAIL] {method_name}: {e}")
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
    
    print("\n[OK] All log generator tests passed!")
    return 0


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
