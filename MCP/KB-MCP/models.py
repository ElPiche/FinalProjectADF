# models.py - Pydantic models and data structures for KB-MCP

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

# Knowledge Base Configuration
class KBConfig(BaseModel):
    # No id field - MongoDB will auto-generate _id
    name: str
    description: str
    change_flag: int = Field(default=0, description="Change flag for triggering change streams")
    scheduling: dict
    algorithms: List[Dict[str, Any]]  # Simple list of algorithm dicts

    def __init__(self, **data):
        super().__init__(**data)
        # Basic validation - detailed validation happens in tools
        if not self.name or not isinstance(self.name, str):
            raise ValueError("Name must be a non-empty string")
        if not self.description or not isinstance(self.description, str):
            raise ValueError("Description must be a non-empty string")

# CRON class moved before classes that use it
class CRON:
    def __init__(self, value: str):
        if not self._is_valid_cron(value):
            raise ValueError(f"Invalid CRON format: {value}")
        self.value = value

    @staticmethod
    def _is_valid_cron(cron_string: str) -> bool:
        try:
            from croniter import croniter
            croniter(cron_string)
            return True
        except Exception:
            return False

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

# Supported algorithms - only fully implemented ones
SUPPORTED_ALGORITHMS = {"zscore"}

# Algorithm configuration models for FastMCP tool parameters
class ZScoreConfig(BaseModel):
    algorithm: str = Field(default="zscore", description="Algorithm type")
    dimensions: List[str] = Field(description="List of field names to monitor for anomalies")

# Union type for all supported algorithms (expand when more algorithms are added)
AlgorithmConfig = ZScoreConfig  # Add KMeansConfig, ARMAConfig, etc. when implemented

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