"""Log Schema Definition

Defines the structure of logs to be generated. Similar to bucket profiles,
log schemas are reusable configurations that define:
- Field names and types
- Value generation patterns per field
- Timestamp configuration
- Index naming

Usage:
    schema = LogSchema(
        name="web_access_logs",
        index_name="test-web-logs",
        timestamp_field="@timestamp",
        fields=[
            FieldDefinition(
                name="response_code",
                field_type=FieldType.INTEGER,
                pattern=ChoicePattern(choices=[200, 404, 500], weights=[0.9, 0.08, 0.02])
            ),
            FieldDefinition(
                name="bytes",
                field_type=FieldType.INTEGER,
                pattern=RandomPattern(min_value=100, max_value=50000, value_type="int")
            ),
        ]
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

try:
    from .patterns import ValuePattern, ConstantPattern
except ImportError:
    from patterns import ValuePattern, ConstantPattern


class FieldType(Enum):
    """Elasticsearch field types."""
    STRING = "keyword"
    TEXT = "text"
    INTEGER = "integer"
    LONG = "long"
    FLOAT = "float"
    DOUBLE = "double"
    BOOLEAN = "boolean"
    DATE = "date"
    OBJECT = "object"
    NESTED = "nested"
    GEO_POINT = "geo_point"
    IP = "ip"


@dataclass
class FieldDefinition:
    """Definition of a single field in the log schema.
    
    Attributes:
        name: Field name (can use dot notation for nested: "geo.location")
        field_type: Elasticsearch field type
        pattern: Value generation pattern
        required: Whether field must be present
        es_mapping: Optional custom Elasticsearch mapping properties
    """
    name: str
    field_type: FieldType
    pattern: ValuePattern
    required: bool = True
    es_mapping: Optional[Dict[str, Any]] = None
    
    def generate_value(self, timestamp: datetime, context: Dict[str, Any] = None) -> Any:
        """Generate a value for this field."""
        return self.pattern.generate(timestamp, context)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "field_type": self.field_type.value,
            "pattern": self.pattern.to_dict(),
            "required": self.required,
            "es_mapping": self.es_mapping,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FieldDefinition":
        return cls(
            name=data["name"],
            field_type=FieldType(data["field_type"]),
            pattern=ValuePattern.from_dict(data["pattern"]),
            required=data.get("required", True),
            es_mapping=data.get("es_mapping"),
        )


@dataclass
class LogSchema:
    """Complete schema for log generation.
    
    This is the main configuration object, similar to a bucket profile.
    It defines what logs look like and how they're stored.
    
    Attributes:
        name: Human-readable schema name
        description: What these logs represent
        index_name: Elasticsearch index to write to
        timestamp_field: Field name for the log timestamp
        fields: List of field definitions
        index_settings: Optional Elasticsearch index settings
    """
    name: str
    description: str = ""
    index_name: str = "generated-logs"
    timestamp_field: str = "@timestamp"
    fields: List[FieldDefinition] = field(default_factory=list)
    index_settings: Optional[Dict[str, Any]] = None
    
    def generate_document(
        self, 
        timestamp: datetime,
        overrides: Optional[Dict[str, Any]] = None,
        force_anomaly: bool = False,
    ) -> Dict[str, Any]:
        """Generate a single log document.
        
        Args:
            timestamp: Timestamp for this log entry
            overrides: Optional field value overrides
            force_anomaly: Force anomaly generation in time series patterns
        
        Returns:
            Dict representing the log document
        """
        overrides = overrides or {}
        
        # Context shared between fields
        context = {
            "force_anomaly": force_anomaly,
            "timestamp": timestamp,
        }
        
        doc = {}
        
        # Add timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        doc[self.timestamp_field] = timestamp.isoformat()
        
        # Generate each field
        for field_def in self.fields:
            if field_def.name in overrides:
                value = overrides[field_def.name]
            else:
                value = field_def.generate_value(timestamp, context)
            
            # Handle nested fields (e.g., "geo.location")
            self._set_nested_value(doc, field_def.name, value)
            
            # Add to context for template patterns
            context[field_def.name] = value
        
        # Mark if this was an anomaly (for generator tracking)
        if context.get("is_anomaly"):
            doc["_is_anomaly"] = True
        
        return doc
    
    def _set_nested_value(self, doc: Dict, path: str, value: Any) -> None:
        """Set a nested value using dot notation."""
        parts = path.split(".")
        current = doc
        
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        
        current[parts[-1]] = value
    
    def get_es_mapping(self) -> Dict[str, Any]:
        """Generate Elasticsearch mapping for this schema."""
        properties = {
            self.timestamp_field: {"type": "date"}
        }
        
        for field_def in self.fields:
            mapping = field_def.es_mapping or {"type": field_def.field_type.value}
            
            # Handle nested paths
            parts = field_def.name.split(".")
            if len(parts) == 1:
                properties[field_def.name] = mapping
            else:
                # Build nested structure
                current = properties
                for part in parts[:-1]:
                    if part not in current:
                        current[part] = {"type": "object", "properties": {}}
                    if "properties" not in current[part]:
                        current[part]["properties"] = {}
                    current = current[part]["properties"]
                current[parts[-1]] = mapping
        
        return {
            "mappings": {
                "properties": properties
            }
        }
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "index_name": self.index_name,
            "timestamp_field": self.timestamp_field,
            "fields": [f.to_dict() for f in self.fields],
            "index_settings": self.index_settings,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LogSchema":
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            index_name=data.get("index_name", "generated-logs"),
            timestamp_field=data.get("timestamp_field", "@timestamp"),
            fields=[FieldDefinition.from_dict(f) for f in data.get("fields", [])],
            index_settings=data.get("index_settings"),
        )


# ============================================================================
# PRE-BUILT SCHEMAS (like pre-built bucket profiles)
# ============================================================================

def create_simple_metrics_schema(
    index_name: str = "test-metrics",
    metric_name: str = "value",
    base_value: float = 100.0,
    noise_std: float = 10.0,
) -> LogSchema:
    """Create a simple metrics log schema.
    
    Good for testing basic anomaly detection.
    
    Fields:
        - @timestamp: Log timestamp
        - metric_name: Numeric metric value
        - host: Server hostname
    """
    try:
        from .patterns import TimeSeriesPattern, ChoicePattern
    except ImportError:
        from patterns import TimeSeriesPattern, ChoicePattern
    
    return LogSchema(
        name="simple_metrics",
        description="Simple numeric metrics for testing",
        index_name=index_name,
        timestamp_field="@timestamp",
        fields=[
            FieldDefinition(
                name=metric_name,
                field_type=FieldType.FLOAT,
                pattern=TimeSeriesPattern(
                    base_value=base_value,
                    noise_std=noise_std,
                )
            ),
            FieldDefinition(
                name="host",
                field_type=FieldType.STRING,
                pattern=ChoicePattern(choices=["server-1", "server-2", "server-3"])
            ),
        ]
    )


def create_http_access_schema(
    index_name: str = "test-http-logs",
    error_rate: float = 0.05,
) -> LogSchema:
    """Create an HTTP access log schema.
    
    Fields:
        - @timestamp: Request timestamp
        - response: HTTP status code (200, 404, 500, etc.)
        - bytes: Response size
        - method: HTTP method
        - path: Request path
        - client_ip: Client IP address
        - response_time_ms: Response time in milliseconds
    """
    try:
        from .patterns import ChoicePattern, RandomPattern, TimeSeriesPattern
    except ImportError:
        from patterns import ChoicePattern, RandomPattern, TimeSeriesPattern
    
    # Status code distribution
    success_weight = 1.0 - error_rate
    error_weight = error_rate
    
    return LogSchema(
        name="http_access_logs",
        description="HTTP access logs with status codes and response times",
        index_name=index_name,
        timestamp_field="@timestamp",
        fields=[
            FieldDefinition(
                name="response",
                field_type=FieldType.INTEGER,
                pattern=ChoicePattern(
                    choices=[200, 201, 204, 301, 302, 400, 401, 403, 404, 500, 502, 503],
                    weights=[
                        success_weight * 0.85,  # 200
                        success_weight * 0.05,  # 201
                        success_weight * 0.05,  # 204
                        success_weight * 0.025, # 301
                        success_weight * 0.025, # 302
                        error_weight * 0.1,     # 400
                        error_weight * 0.1,     # 401
                        error_weight * 0.1,     # 403
                        error_weight * 0.4,     # 404
                        error_weight * 0.15,    # 500
                        error_weight * 0.1,     # 502
                        error_weight * 0.05,    # 503
                    ]
                )
            ),
            FieldDefinition(
                name="bytes",
                field_type=FieldType.INTEGER,
                pattern=RandomPattern(min_value=100, max_value=50000, value_type="int")
            ),
            FieldDefinition(
                name="method",
                field_type=FieldType.STRING,
                pattern=ChoicePattern(
                    choices=["GET", "POST", "PUT", "DELETE", "PATCH"],
                    weights=[0.7, 0.15, 0.08, 0.05, 0.02]
                )
            ),
            FieldDefinition(
                name="path",
                field_type=FieldType.STRING,
                pattern=ChoicePattern(
                    choices=["/", "/api/users", "/api/orders", "/api/products", "/health", "/metrics"],
                    weights=[0.1, 0.25, 0.25, 0.25, 0.1, 0.05]
                )
            ),
            FieldDefinition(
                name="client_ip",
                field_type=FieldType.IP,
                pattern=ChoicePattern(
                    choices=["192.168.1.100", "192.168.1.101", "10.0.0.50", "172.16.0.1"]
                )
            ),
            FieldDefinition(
                name="response_time_ms",
                field_type=FieldType.FLOAT,
                pattern=TimeSeriesPattern(
                    base_value=50.0,
                    noise_std=20.0,
                    anomaly_probability=0.01,
                    anomaly_multiplier=5.0,
                )
            ),
        ]
    )


def create_aggregated_metrics_schema(
    index_name: str = "test-aggregated-metrics",
    metric_fields: Optional[List[str]] = None,
) -> LogSchema:
    """Create schema for pre-aggregated metrics (like hourly counters).
    
    This is useful for testing the KB SQL queries that use aggregation.
    
    Fields:
        - @timestamp: Bucket timestamp
        - request_count: Total requests in bucket
        - error_count: Error requests in bucket
        - avg_response_time: Average response time
    """
    try:
        from .patterns import TimeSeriesPattern
    except ImportError:
        from patterns import TimeSeriesPattern
    
    metric_fields = metric_fields or ["request_count", "error_count", "avg_response_time"]
    
    fields = []
    
    if "request_count" in metric_fields:
        fields.append(FieldDefinition(
            name="request_count",
            field_type=FieldType.INTEGER,
            pattern=TimeSeriesPattern(
                base_value=1000.0,
                noise_std=100.0,
                daily_pattern={
                    "0": 0.3, "1": 0.2, "2": 0.2, "3": 0.2, "4": 0.3, "5": 0.5,
                    "6": 0.7, "7": 0.9, "8": 1.2, "9": 1.5, "10": 1.5, "11": 1.4,
                    "12": 1.3, "13": 1.4, "14": 1.5, "15": 1.4, "16": 1.3, "17": 1.2,
                    "18": 1.0, "19": 0.9, "20": 0.8, "21": 0.7, "22": 0.5, "23": 0.4,
                },
                weekly_pattern={
                    "0": 1.0, "1": 1.0, "2": 1.0, "3": 1.0, "4": 1.0,  # Mon-Fri
                    "5": 0.6, "6": 0.5,  # Sat-Sun
                }
            )
        ))
    
    if "error_count" in metric_fields:
        fields.append(FieldDefinition(
            name="error_count",
            field_type=FieldType.INTEGER,
            pattern=TimeSeriesPattern(
                base_value=10.0,
                noise_std=5.0,
                anomaly_probability=0.02,  # 2% chance of error spike
                anomaly_multiplier=10.0,
            )
        ))
    
    if "avg_response_time" in metric_fields:
        fields.append(FieldDefinition(
            name="avg_response_time",
            field_type=FieldType.FLOAT,
            pattern=TimeSeriesPattern(
                base_value=100.0,
                noise_std=20.0,
                daily_pattern={
                    "9": 1.2, "10": 1.3, "11": 1.2, "12": 1.1,
                    "13": 1.2, "14": 1.3, "15": 1.2, "16": 1.1,
                },
            )
        ))
    
    return LogSchema(
        name="aggregated_metrics",
        description="Pre-aggregated metrics for time-series anomaly detection",
        index_name=index_name,
        timestamp_field="@timestamp",
        fields=fields,
    )
