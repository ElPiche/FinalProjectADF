"""Pydantic models and helpers for KB-MCP."""

import os
import json
from pathlib import Path
from datetime import datetime
import re
from typing import Any, Dict, List, Optional
import logging

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

logger = logging.getLogger(__name__)

# ============================================================================
# ALGORITHM REGISTRY - Read from shared volume (written by DA-Dispatcher)
# ============================================================================

ALGORITHM_REGISTRY_PATH = Path(os.environ.get(
    "ALGORITHM_REGISTRY_PATH", 
    "/app/registry/algorithms.json"
))


def get_supported_algorithms() -> Dict[str, Any]:
    """Read algorithm registry from shared volume.
    
    DA-Dispatcher writes this file on startup.
    Returns dict of {name: metadata} for all registered algorithms.
    """
    if not ALGORITHM_REGISTRY_PATH.exists():
        logger.warning(f"Algorithm registry not found: {ALGORITHM_REGISTRY_PATH}")
        # Fallback to known algorithms if file doesn't exist yet
        return {"zscore": {}, "mock": {}, "iqr": {}}
    
    try:
        return json.loads(ALGORITHM_REGISTRY_PATH.read_text())
    except Exception as e:
        logger.error(f"Failed to read algorithm registry: {e}")
        return {"zscore": {}, "mock": {}, "iqr": {}}


class _DynamicAlgorithmSet:
    """Set-like object that reads from the registry file each time."""
    
    def __contains__(self, item):
        algos = get_supported_algorithms()
        return item.lower() in algos
    
    def __iter__(self):
        return iter(get_supported_algorithms().keys())
    
    def __len__(self):
        return len(get_supported_algorithms())


# This is used for validation - reads fresh from file each time
SUPPORTED_ALGORITHMS = _DynamicAlgorithmSet()


class QueryMode(BaseModel):
    """Represents how Elasticsearch data is materialized for training/detection."""

    model_config = ConfigDict(populate_by_name=True)

    type: str = Field(description="Data extraction mode: 'raw' or 'aggregated'.")
    timestamp_field: str = Field(description="Timestamp column returned by the SQL query.")

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in {"raw", "aggregated"}:
            raise ValueError("query_mode.type must be either 'raw' or 'aggregated'")
        return normalized

    @field_validator("timestamp_field")
    @classmethod
    def validate_timestamp_field(cls, value: str) -> str:
        if not value or not isinstance(value, str):
            raise ValueError("timestamp_field must be a non-empty string")
        return value


class TrainingConfig(BaseModel):
    """Training schedule metadata (legacy query fields kept for migration)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: str = Field(default="static", description="Training scope strategy (static|rolling).")
    from_: str = Field(alias="from", description="Training data start timestamp (ISO 8601).")
    to: str = Field(description="Training data end timestamp (ISO 8601).")
    is_active: bool = Field(default=True, description="Enable or pause training jobs.")
    training_window: Optional[int] = Field(
        default=None,
        description="Legacy window duration in seconds. Retained for backward compatibility.",
    )
    training_query: Optional[str] = Field(
        default=None,
        description="Legacy per-phase training query. Use elasticsearch_sql_query instead.",
    )

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in {"static", "rolling"}:
            raise ValueError("training_config.type must be 'static' or 'rolling'")
        return normalized

    @field_validator("from_", "to")
    @classmethod
    def validate_timestamps(cls, value: str) -> str:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"Invalid ISO 8601 timestamp: {value}") from exc
        return value


class DetectionConfig(BaseModel):
    """Detection schedule metadata (legacy query fields kept for migration)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    frequency: str = Field(description="Detection frequency (CRON expression).")
    detection_window: int = Field(description="Detection window in seconds.")
    is_active: bool = Field(default=True, description="Enable or pause detection jobs.")
    from_: Optional[str] = Field(default=None, alias="from", description="Detection start timestamp (ISO 8601).")
    detection_query: Optional[str] = Field(
        default=None,
        description="Legacy per-phase detection query. Use elasticsearch_sql_query instead.",
    )

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, value: str) -> str:
        if not CRON._is_valid_cron(value):
            raise ValueError(f"Invalid CRON expression: {value}")
        return value

    @field_validator("from_")
    @classmethod
    def validate_from_timestamp(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"Invalid ISO 8601 timestamp: {value}") from exc
        return value

    @field_validator("detection_window")
    @classmethod
    def validate_detection_window(cls, value: int) -> int:
        if not isinstance(value, int) or value <= 0:
            raise ValueError("detection_window must be a positive integer")
        return value


class SchedulingConfig(BaseModel):
    training_config: TrainingConfig = Field(description="Training configuration")
    detection_config: DetectionConfig = Field(description="Detection configuration")


class AnomalyConfig(BaseModel):
    """Generic holder for per-KB anomaly notification and future tweakable configs."""

    model_config = ConfigDict(populate_by_name=True)

    user_emails: Optional[List[str]] = Field(
        default=None,
        validation_alias=AliasChoices("user_emails", "UserEmails"),
        serialization_alias="user_emails",
        description="Optional list of email addresses to notify when anomalies are detected.",
    )

    @field_validator("user_emails")
    @classmethod
    def validate_user_emails(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return value
        if not isinstance(value, list):
            raise ValueError("user_emails must be a list of email addresses")
        validated_emails = []
        email_pattern = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
        for email in value:
            if not isinstance(email, str) or not email.strip():
                raise ValueError("Each email must be a non-empty string")
            email_clean = email.strip()
            if not email_pattern.match(email_clean):
                raise ValueError(f"Invalid email format: {email_clean}")
            validated_emails.append(email_clean)
        return validated_emails if validated_emails else None


class AlgorithmParameter(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dimension: str = Field(description="Column name to monitor for anomalies")
    is_active: bool = Field(default=True, description="Toggle anomaly detection for this dimension.")
    metadata: Optional[List[Dict[str, str]]] = Field(
        default=None,
        validation_alias=AliasChoices("metadata", "alg_metadata"),
        serialization_alias="metadata",
        description="Algorithm-specific metadata entries.",
    )


class AlgorithmConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(
        validation_alias=AliasChoices("name", "alg_name"),
        serialization_alias="name",
        description="Algorithm name (e.g., 'zscore').",
    )
    parameters: List[AlgorithmParameter] = Field(
        validation_alias=AliasChoices("parameters", "alg_parameters"),
        serialization_alias="parameters",
        description="Algorithm parameters",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in SUPPORTED_ALGORITHMS:
            raise ValueError(
                f"Algorithm '{value}' is not supported. Supported algorithms: {sorted(SUPPORTED_ALGORITHMS)}"
            )
        return normalized

    @field_validator("parameters")
    @classmethod
    def validate_parameters(cls, value: List[AlgorithmParameter]) -> List[AlgorithmParameter]:
        if not value:
            raise ValueError("algorithm.parameters cannot be empty")
        return value


# Backwards-compatible alias for legacy imports
AlgorithmConfigItem = AlgorithmConfig


class KBConfig(BaseModel):
    """Top-level configuration consumed by dispatcher and extractor services."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(description="Configuration name")
    description: str = Field(description="Human-readable description")
    change_flag: int = Field(default=0, description="Change flag for triggering change streams")
    elasticsearch_sql_query: str = Field(description="Unified Elasticsearch SQL query for training and detection")
    source_index: str = Field(
        description="Source Elasticsearch index being monitored (e.g., 'app-logs'). Used for dashboard naming and anomaly output index.",
    )
    query_mode: QueryMode = Field(description="Query mode metadata")
    bucket_profile_id: Optional[str] = Field(
        default=None,
        description="Optional reference to a bucket_profiles document (time-context definition).",
    )
    anomaly_config: Optional[AnomalyConfig] = Field(
        default=None,
        validation_alias=AliasChoices("anomaly_config", "AnomalyConfig"),
        serialization_alias="anomaly_config",
        description="Optional anomaly notification and configuration settings.",
    )
    algorithm: AlgorithmConfig = Field(description="Algorithm configuration")
    scheduling: SchedulingConfig = Field(description="Scheduling configuration")

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_schema(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(data, dict):
            return data

        migrated: Dict[str, Any] = dict(data)

        if "algorithm" not in migrated:
            legacy_algorithms = migrated.get("algorithms") or []
            if legacy_algorithms:
                migrated["algorithm"] = legacy_algorithms[0]

        if not migrated.get("query_mode"):
            migrated["query_mode"] = {"type": "raw", "timestamp_field": "@timestamp"}

        if "elasticsearch_sql_query" not in migrated:
            scheduling = migrated.get("scheduling") or {}
            training_cfg = (scheduling.get("training_config") or {}) if isinstance(scheduling, dict) else {}
            detection_cfg = (scheduling.get("detection_config") or {}) if isinstance(scheduling, dict) else {}
            fallback_query = training_cfg.get("training_query") or detection_cfg.get("detection_query")
            migrated["elasticsearch_sql_query"] = fallback_query or ""

        return migrated

    def __init__(self, **data):
        super().__init__(**data)
        if not self.name or not isinstance(self.name, str):
            raise ValueError("Name must be a non-empty string")
        if not self.description or not isinstance(self.description, str):
            raise ValueError("Description must be a non-empty string")

    @property
    def algorithms(self) -> List[AlgorithmConfig]:
        """Legacy helper to expose singular algorithm as list."""

        return [self.algorithm]

# CRON class moved before classes that use it
class CRON:
    """CRON expression validator supporting both 5-field (UNIX) and 6-field (Spring) formats.
    
    5-field format: minute hour day month weekday (UNIX standard)
    6-field format: second minute hour day month weekday (Spring format)
    
    The actual frequency validation is delegated to the extractor service which uses
    Spring's CronExpression for sub-minute resolution support.
    """
    
    def __init__(self, value: str):
        if not self._is_valid_cron(value):
            raise ValueError(f"Invalid CRON format: {value}")
        self.value = value

    @staticmethod
    def _is_valid_cron(cron_string: str) -> bool:
        """Basic CRON syntax validation.
        
        Accepts both 5-field (UNIX) and 6-field (Spring with seconds) formats.
        Full validation including frequency floor checks is done by the extractor.
        """
        if not cron_string or not isinstance(cron_string, str):
            return False
        
        parts = cron_string.strip().split()
        
        # Must have 5 fields (UNIX) or 6 fields (Spring with seconds)
        if len(parts) not in (5, 6):
            return False
        
        # Basic validation: each field should contain valid CRON characters
        valid_chars = set('0123456789*,-/LW#?')
        for part in parts:
            if not part:
                return False
            # Allow alphanumeric for day/month names (MON, JAN, etc.)
            if not all(c in valid_chars or c.isalpha() for c in part):
                return False
        
        return True

    def __str__(self):
        return self.value

    def __repr__(self):
        return f"CRON('{self.value}')"

# KB Configuration Classes
class schedulingTrainingConfig(BaseModel):
    '''
    Configuration class for scheduling training jobs.
    '''
    from_date: datetime
    to_date: datetime
    mode: str

class schedulingDetectionConfig(BaseModel):
    '''
    Configuration class for scheduling detection jobs.
    '''
    frequency: str  # Will store CRON value
    window: str     # Will store CRON value
    start: datetime
    mode: str

    def __init__(self, **data):
        # Handle CRON objects in initialization
        if 'frequency' in data and isinstance(data['frequency'], CRON):
            data['frequency'] = data['frequency'].value
        if 'window' in data and isinstance(data['window'], CRON):
            data['window'] = data['window'].value
        super().__init__(**data)

# Algorithm configuration models for FastMCP tool parameters
class ZScoreConfig(AlgorithmConfigItem):
    """Z-score algorithm configuration used by FastMCP tool schemas."""

    name: str = Field(default="zscore", description="Algorithm name (must be 'zscore')")

# SQL class for validating SQL queries
class SQL:
    def __init__(self, value: str):
        if not self._is_valid_sql(value):
            raise ValueError(f"Invalid SQL format: {value}")
        self.value = value

    @staticmethod
    def _is_valid_sql(query: str) -> bool:
        # Basic SQL syntax validation without using MCP tools during startup
        try:
            # Basic regex validation for SQL structure
            if not re.search(r'\bSELECT\b', query, re.IGNORECASE):
                return False

            # Check for basic SQL structure
            if not re.search(r'\bFROM\b', query, re.IGNORECASE):
                return False

            # Check for balanced quotes
            single_quotes = query.count("'") - query.count("\\'")
            double_quotes = query.count('"') - query.count('\\"')
            if single_quotes % 2 != 0 or double_quotes % 2 != 0:
                return False

            return True
        except Exception:
            return False

    def extract_output_fields(self) -> list[str]:
        """
        Extract all output field names from the SQL query.

        Returns:
            list[str]: List of all field names that could be output from the query

        Raises:
            ValueError: If query parsing fails
        """
        from .validation import extract_sql_output_fields
        return extract_sql_output_fields(self.value)

    def extract_stats_fields(self) -> list[str]:
        """
        Extract output field names from SQL SELECT clauses.

        Returns:
            list[str]: List of field names defined in SELECT clauses

        Raises:
            ValueError: If SELECT clause parsing fails
        """
        from .validation import extract_sql_select_fields
        return extract_sql_select_fields(self.value)

    def __str__(self):
        return self.value

    def __repr__(self):
        return f"SQL('{self.value}')"

class UUID:
    def __init__(self, value: str):
        if not self._is_valid_uuid(value):
            raise ValueError(f"Invalid UUID format: {value}")
        self.value = value

    @staticmethod
    def _is_valid_uuid(uuid_str: str) -> bool:
        try:
            import uuid
            uuid.UUID(uuid_str)
            return True
        except ValueError:
            return False

    def __str__(self):
        return self.value

    def __repr__(self):
        return f"UUID('{self.value}')"