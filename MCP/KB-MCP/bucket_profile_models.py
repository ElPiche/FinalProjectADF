"""Pydantic models for bucket profiles.

Per Feature Specification Section 4.2.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExceptionRuleConfig(BaseModel):
    """Exception rule configuration for specific dates (e.g., holidays)."""
    
    model_config = ConfigDict(populate_by_name=True)
    
    month: int = Field(ge=1, le=12, description="Month (1-12)")
    day: int = Field(ge=1, le=31, description="Day of month (1-31)")
    year: Optional[int] = Field(default=None, description="Specific year or None for recurring")


class ExceptionConfig(BaseModel):
    """Exception entry in bucket profile."""
    
    model_config = ConfigDict(populate_by_name=True)
    
    bucket_base_key: str = Field(description="Base key for this exception (e.g., 'holiday_xmas')")
    rule: ExceptionRuleConfig = Field(description="Date matching rule")
    granularity: str = Field(default="block", description="'block' or 'hourly'")
    
    @field_validator("granularity")
    @classmethod
    def validate_granularity(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in {"block", "hourly"}:
            raise ValueError("granularity must be 'block' or 'hourly'")
        return normalized


class TimeRangeConfig(BaseModel):
    """Time range for schedule rules."""
    
    model_config = ConfigDict(populate_by_name=True)
    
    start: str = Field(default="00:00", description="Start time (HH:MM)")
    end: str = Field(default="23:59", description="End time (HH:MM)")
    
    @field_validator("start", "end")
    @classmethod
    def validate_time_format(cls, value: str) -> str:
        if not value:
            return value
        parts = value.split(":")
        if len(parts) != 2:
            raise ValueError(f"Time must be in HH:MM format, got: {value}")
        try:
            hour = int(parts[0])
            minute = int(parts[1])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError(f"Invalid time value: {value}")
        except ValueError as e:
            raise ValueError(f"Invalid time format: {value}") from e
        return value


class ScheduleConfig(BaseModel):
    """Schedule entry in bucket profile."""
    
    model_config = ConfigDict(populate_by_name=True)
    
    bucket_base_key: str = Field(description="Base key for this schedule (e.g., 'workday')")
    days: List[int] = Field(description="Days of week (1=Monday, 7=Sunday)")
    time_range: TimeRangeConfig = Field(default_factory=TimeRangeConfig, description="Active time range")
    granularity: str = Field(default="hourly", description="'block' or 'hourly'")
    months: Optional[List[int]] = Field(default=None, description="Months this applies (1-12) or None for all")
    
    @field_validator("granularity")
    @classmethod
    def validate_granularity(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in {"block", "hourly"}:
            raise ValueError("granularity must be 'block' or 'hourly'")
        return normalized
    
    @field_validator("days")
    @classmethod
    def validate_days(cls, value: List[int]) -> List[int]:
        for d in value:
            if not (1 <= d <= 7):
                raise ValueError(f"Day must be 1-7 (ISO weekday), got: {d}")
        return value
    
    @field_validator("months")
    @classmethod
    def validate_months(cls, value: Optional[List[int]]) -> Optional[List[int]]:
        if value is None:
            return value
        for m in value:
            if not (1 <= m <= 12):
                raise ValueError(f"Month must be 1-12, got: {m}")
        return value


class FallbackConfig(BaseModel):
    """Fallback configuration when no exception or schedule matches."""
    
    model_config = ConfigDict(populate_by_name=True)
    
    bucket_base_key: str = Field(default="fallback", description="Base key for fallback")
    granularity: str = Field(default="hourly", description="'block' or 'hourly'")
    
    @field_validator("granularity")
    @classmethod
    def validate_granularity(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in {"block", "hourly"}:
            raise ValueError("granularity must be 'block' or 'hourly'")
        return normalized


class BucketProfileConfig(BaseModel):
    """Complete bucket profile configuration.
    
    Per Feature Specification Section 4.2.
    
    Example:
    {
        "_id": "business_hours_v1",
        "timezone": "America/New_York",
        "exceptions": [
            {"bucket_base_key": "holiday_xmas", "rule": {"month": 12, "day": 25}, "granularity": "block"}
        ],
        "schedule": [
            {"bucket_base_key": "workday", "days": [1,2,3,4,5], "time_range": {"start": "09:00", "end": "17:00"}, "granularity": "hourly"}
        ],
        "fallback": {"bucket_base_key": "off_hours", "granularity": "hourly"}
    }
    """
    
    model_config = ConfigDict(populate_by_name=True)
    
    id: str = Field(alias="_id", description="Custom string ID for this profile")
    timezone: str = Field(description="IANA timezone (e.g., 'America/New_York')")
    exceptions: List[ExceptionConfig] = Field(default_factory=list, description="Exception rules (holidays)")
    schedule: List[ScheduleConfig] = Field(default_factory=list, description="Schedule rules")
    fallback: FallbackConfig = Field(default_factory=FallbackConfig, description="Fallback configuration")
    
    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(value)
        except Exception as e:
            raise ValueError(f"Invalid timezone: {value}") from e
        return value
    
    def to_mongodb_doc(self) -> Dict[str, Any]:
        """Convert to MongoDB document format."""
        return {
            "_id": self.id,
            "timezone": self.timezone,
            "exceptions": [
                {
                    "bucket_base_key": exc.bucket_base_key,
                    "rule": {
                        "month": exc.rule.month,
                        "day": exc.rule.day,
                        **({"year": exc.rule.year} if exc.rule.year is not None else {}),
                    },
                    "granularity": exc.granularity,
                }
                for exc in self.exceptions
            ],
            "schedule": [
                {
                    "bucket_base_key": sched.bucket_base_key,
                    "days": sched.days,
                    "time_range": {
                        "start": sched.time_range.start,
                        "end": sched.time_range.end,
                    },
                    "granularity": sched.granularity,
                    **({"months": sched.months} if sched.months is not None else {}),
                }
                for sched in self.schedule
            ],
            "fallback": {
                "bucket_base_key": self.fallback.bucket_base_key,
                "granularity": self.fallback.granularity,
            },
        }
