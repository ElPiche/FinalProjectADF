"""Log Generator Package

A flexible log generation system that can create logs of any format
and inject them into Elasticsearch for testing the anomaly detection pipeline.

Similar in design philosophy to the bucket profile system:
- Schema-based configuration
- Reusable profiles
- Pattern-based value generation
"""

from .log_schema import LogSchema, FieldDefinition, FieldType
from .log_generator import LogGenerator
from .patterns import ValuePattern, ConstantPattern, RandomPattern, TimeSeriesPattern
from .injector import ElasticsearchInjector

__all__ = [
    "LogSchema",
    "FieldDefinition", 
    "FieldType",
    "LogGenerator",
    "ValuePattern",
    "ConstantPattern",
    "RandomPattern",
    "TimeSeriesPattern",
    "ElasticsearchInjector",
]
