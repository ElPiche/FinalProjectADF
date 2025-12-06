"""BucketResolver - Resolves UTC timestamps to semantic bucket keys.

This module implements the core BucketResolver logic for the Dynamic Context-Aware
Anomaly Detection feature. It maps timestamps to semantic keys based on configurable
bucket profiles with support for:
- Timezone conversion
- Exception rules (holidays) with highest priority
- Schedule rules (workdays/weekends) with priority ordering
- Overnight shift handling (shifts crossing midnight)
- Hourly vs block granularity
- Fallback rules

Per Feature Specification Section 5.1.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date, time as dt_time
from typing import Dict, List, Optional, Tuple, Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Default key when no bucket profile is configured
GLOBAL_DEFAULT_KEY = "global_default"


def sanitize_bucket_key(key: str) -> str:
    """Sanitize bucket key to snake_case, lowercase, no special chars.
    
    Per Test D.1 - Naming Determinism (Sanitization):
    Input: "My Super Campaign! (2025)"
    Output: "my_super_campaign_2025"
    """
    if not key:
        return "unknown"
    
    # Convert to lowercase
    result = key.lower()
    
    # Replace spaces and hyphens with underscores
    result = re.sub(r'[\s\-]+', '_', result)
    
    # Remove all non-alphanumeric characters except underscores
    result = re.sub(r'[^a-z0-9_]', '', result)
    
    # Collapse multiple underscores
    result = re.sub(r'_+', '_', result)
    
    # Strip leading/trailing underscores
    result = result.strip('_')
    
    return result or "unknown"


@dataclass
class ExceptionRule:
    """Exception rule for specific dates (e.g., holidays).
    
    Exceptions have HIGHEST priority and are checked first.
    """
    bucket_base_key: str
    month: int
    day: int
    granularity: str = "block"  # "block" or "hourly"
    year: Optional[int] = None  # If None, applies every year
    
    def matches(self, local_date: date) -> bool:
        """Check if this exception matches the given date."""
        if self.year is not None and local_date.year != self.year:
            return False
        return local_date.month == self.month and local_date.day == self.day


@dataclass
class ScheduleRule:
    """Schedule rule for recurring time patterns (e.g., workdays, weekends).
    
    Schedule rules are checked after exceptions, in list order (first match wins).
    """
    bucket_base_key: str
    days: List[int]  # 1=Monday, 7=Sunday (ISO weekday)
    start_time: str = "00:00"  # HH:MM format
    end_time: str = "23:59"    # HH:MM format
    granularity: str = "hourly"  # "block" or "hourly"
    months: Optional[List[int]] = None  # If None, applies all months
    
    # Cached parsed times
    _start_minutes: int = field(init=False, repr=False, default=-1)
    _end_minutes: int = field(init=False, repr=False, default=-1)
    _is_overnight: bool = field(init=False, repr=False, default=False)
    
    def __post_init__(self):
        self._parse_times()
    
    def _parse_times(self):
        """Parse start/end times into minutes since midnight.
        
        Validates that times are in HH:MM format with valid hours (0-23) and minutes (0-59).
        Per Test E.4 - Invalid Configuration (Garbage Protection).
        """
        try:
            start_parts = self.start_time.split(':')
            if len(start_parts) != 2:
                raise ValueError(f"Invalid start_time format: {self.start_time}")
            start_hour = int(start_parts[0])
            start_minute = int(start_parts[1])
            if not (0 <= start_hour <= 23) or not (0 <= start_minute <= 59):
                raise ValueError(f"Invalid start_time value: {self.start_time}")
            self._start_minutes = start_hour * 60 + start_minute
            
            end_parts = self.end_time.split(':')
            if len(end_parts) != 2:
                raise ValueError(f"Invalid end_time format: {self.end_time}")
            end_hour = int(end_parts[0])
            end_minute = int(end_parts[1])
            if not (0 <= end_hour <= 23) or not (0 <= end_minute <= 59):
                raise ValueError(f"Invalid end_time value: {self.end_time}")
            self._end_minutes = end_hour * 60 + end_minute
            
            # Overnight shift: end time is "before" start time (e.g., 20:00 - 04:00)
            self._is_overnight = self._end_minutes < self._start_minutes
            
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid time format in ScheduleRule: start={self.start_time}, end={self.end_time}")
            raise ValueError(f"Invalid time format: {e}")
    
    @property
    def is_overnight(self) -> bool:
        return self._is_overnight
    
    def matches_day(self, local_dt: datetime) -> bool:
        """Check if this rule matches the day of week."""
        if not self.days:
            return False
        return local_dt.isoweekday() in self.days
    
    def matches_month(self, local_dt: datetime) -> bool:
        """Check if this rule matches the month.
        
        Per Test C.3 - Empty Month Safety:
        - If months is None, match all months (no restriction)
        - If months is an empty list, match NO months (explicit "never")
        """
        if self.months is None:
            return True  # No month restriction - match all
        if not self.months:
            return False  # Empty list - match none
        return local_dt.month in self.months
    
    def matches_time(self, local_dt: datetime) -> bool:
        """Check if the time falls within this rule's time range."""
        current_minutes = local_dt.hour * 60 + local_dt.minute
        
        if self._is_overnight:
            # Overnight shift: matches if >= start OR < end
            return current_minutes >= self._start_minutes or current_minutes < self._end_minutes
        else:
            # Normal shift: matches if >= start AND <= end (inclusive end)
            # Per Test E.2: 17:00:59 should match, 17:01:00 should not
            return self._start_minutes <= current_minutes <= self._end_minutes
    
    def matches(self, local_dt: datetime) -> bool:
        """Check if this rule matches the given datetime (same day logic)."""
        if not self.matches_month(local_dt):
            return False
        if not self.matches_day(local_dt):
            return False
        if not self.matches_time(local_dt):
            return False
        return True


@dataclass
class FallbackRule:
    """Fallback rule when no exception or schedule matches."""
    bucket_base_key: str = "fallback"
    granularity: str = "hourly"


@dataclass
class BucketProfile:
    """A complete bucket profile configuration.
    
    Per Feature Specification Section 4.2.
    """
    profile_id: str
    timezone: str
    exceptions: List[ExceptionRule] = field(default_factory=list)
    schedule: List[ScheduleRule] = field(default_factory=list)
    fallback: FallbackRule = field(default_factory=FallbackRule)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BucketProfile:
        """Create a BucketProfile from a dictionary (e.g., MongoDB document)."""
        profile_id = data.get("_id") or data.get("profile_id", "unknown")
        timezone = data.get("timezone", "UTC")
        
        # Parse exceptions (handle None explicitly)
        exceptions = []
        exceptions_data = data.get("exceptions") or []
        for exc in exceptions_data:
            rule = exc.get("rule", {}) or {}
            exceptions.append(ExceptionRule(
                bucket_base_key=exc.get("bucket_base_key", "exception"),
                month=rule.get("month", 1),
                day=rule.get("day", 1),
                granularity=exc.get("granularity", "block"),
                year=rule.get("year"),
            ))
        
        # Parse schedule (handle None explicitly)
        schedule = []
        schedule_data = data.get("schedule") or []
        for sched in schedule_data:
            time_range = sched.get("time_range", {}) or {}
            schedule.append(ScheduleRule(
                bucket_base_key=sched.get("bucket_base_key", "default"),
                days=sched.get("days") or [],
                start_time=time_range.get("start", "00:00"),
                end_time=time_range.get("end", "23:59"),
                granularity=sched.get("granularity", "hourly"),
                months=sched.get("months"),
            ))
        
        # Parse fallback (handle None explicitly)
        fb_data = data.get("fallback") or {}
        fallback = FallbackRule(
            bucket_base_key=fb_data.get("bucket_base_key", "fallback"),
            granularity=fb_data.get("granularity", "hourly"),
        )
        
        return cls(
            profile_id=profile_id,
            timezone=timezone,
            exceptions=exceptions,
            schedule=schedule,
            fallback=fallback,
        )


class BucketResolver:
    """Resolves UTC timestamps to semantic bucket keys.
    
    Priority order:
    1. Exceptions (holidays) - checked first
    2. Schedule rules - checked in order, first match wins
    3. Overnight shift lookback - check if yesterday's overnight shift extends into today
    4. Fallback - always matches
    
    Per Feature Specification Section 5.1.
    """
    
    def __init__(self, profile: Optional[BucketProfile] = None):
        """Initialize the resolver with a bucket profile.
        
        Args:
            profile: BucketProfile configuration. If None, all timestamps
                    resolve to GLOBAL_DEFAULT_KEY (Test D.3).
        """
        self._profile = profile
        self._tz: Optional[ZoneInfo] = None
        self._exceptions_map: Dict[Tuple[int, int], ExceptionRule] = {}
        
        if profile is not None:
            self._init_profile(profile)
    
    def _init_profile(self, profile: BucketProfile):
        """Initialize internal state from profile."""
        try:
            self._tz = ZoneInfo(profile.timezone)
        except Exception as e:
            logger.error(f"Invalid timezone '{profile.timezone}': {e}")
            raise ValueError(f"Invalid timezone: {profile.timezone}")
        
        # Build exception lookup map (first-match wins per Test E.3)
        for exc in profile.exceptions:
            key = (exc.month, exc.day)
            if key not in self._exceptions_map:
                self._exceptions_map[key] = exc
    
    def _format_key(self, base_key: str, hour: int, granularity: str) -> str:
        """Format the final bucket key with optional hour suffix.
        
        Args:
            base_key: The base bucket key (will be sanitized)
            hour: Hour of the day (0-23)
            granularity: "hourly" or "block"
        
        Returns:
            Formatted bucket key (e.g., "workday_14" or "holiday")
        """
        sanitized = sanitize_bucket_key(base_key)
        if granularity == "hourly":
            return f"{sanitized}_{hour:02d}"
        return sanitized
    
    def _check_exception(self, local_dt: datetime) -> Optional[str]:
        """Check if date matches any exception rule (Priority 1)."""
        key = (local_dt.month, local_dt.day)
        exc = self._exceptions_map.get(key)
        if exc is not None:
            # Check year constraint if specified
            if exc.year is not None and local_dt.year != exc.year:
                return None
            return self._format_key(exc.bucket_base_key, local_dt.hour, exc.granularity)
        return None
    
    def _check_schedule(self, local_dt: datetime) -> Optional[str]:
        """Check if datetime matches any schedule rule (Priority 2)."""
        for rule in self._profile.schedule:
            if rule.matches(local_dt):
                return self._format_key(rule.bucket_base_key, local_dt.hour, rule.granularity)
        return None
    
    def _check_overnight_lookback(self, local_dt: datetime) -> Optional[str]:
        """Check if yesterday's overnight shift extends into today (Priority 3).
        
        Per Test C.1 - The "Friday Night Party":
        A shift that starts Friday at 20:00 and ends Saturday at 04:00.
        If we're on Saturday at 02:00, we should match the Friday overnight shift.
        """
        yesterday = local_dt - timedelta(days=1)
        current_minutes = local_dt.hour * 60 + local_dt.minute
        
        for rule in self._profile.schedule:
            if not rule.is_overnight:
                continue
            
            # Check if yesterday matched this rule's day
            if not rule.matches_day(yesterday):
                continue
            
            # Check if yesterday matched this rule's month
            if not rule.matches_month(yesterday):
                continue
            
            # Check if current time is in the overnight tail (< end, exclusive)
            # Per Test C.1 fix note: use < (exclusive) to prevent overlap at exactly 04:00
            if current_minutes < rule._end_minutes:
                return self._format_key(rule.bucket_base_key, local_dt.hour, rule.granularity)
        
        return None
    
    def _get_fallback(self, local_dt: datetime) -> str:
        """Return the fallback bucket key (Priority 4)."""
        fb = self._profile.fallback
        return self._format_key(fb.bucket_base_key, local_dt.hour, fb.granularity)
    
    def resolve(self, utc_timestamp: datetime) -> str:
        """Resolve a UTC timestamp to a semantic bucket key.
        
        Args:
            utc_timestamp: A timezone-aware datetime in UTC, or a naive datetime
                          that will be treated as UTC.
        
        Returns:
            A sanitized bucket key string (e.g., "workday_14", "holiday_xmas").
        
        Per Feature Specification Section 5.1 - Priority Order:
        1. Check Exceptions (Holidays) - Priority 1
        2. Check Schedule (Workdays/Weekends) - Priority 2
        3. Check Overnight Shifts (Yesterday's shift extending to today)
        4. Fallback
        """
        # Test D.3: Global Fallback (Null Profile)
        if self._profile is None:
            return GLOBAL_DEFAULT_KEY
        
        # Convert to local timezone
        # Handle both aware and naive datetimes
        if utc_timestamp.tzinfo is None:
            utc_timestamp = utc_timestamp.replace(tzinfo=ZoneInfo("UTC"))
        
        try:
            local_dt = utc_timestamp.astimezone(self._tz)
        except Exception as e:
            # Test E.1: DST edge case - resolver must not crash
            logger.warning(f"Timezone conversion failed for {utc_timestamp}: {e}. Using fallback.")
            # Use the hour from UTC as a fallback
            return self._format_key(
                self._profile.fallback.bucket_base_key,
                utc_timestamp.hour,
                self._profile.fallback.granularity
            )
        
        # 1. Check Exceptions (Holidays) - Priority 1
        result = self._check_exception(local_dt)
        if result is not None:
            return result
        
        # 2. Check Schedule (Workdays/Weekends) - Priority 2
        result = self._check_schedule(local_dt)
        if result is not None:
            return result
        
        # 3. Check Overnight Shifts (Yesterday's shift extending to today)
        result = self._check_overnight_lookback(local_dt)
        if result is not None:
            return result
        
        # 4. Fallback
        return self._get_fallback(local_dt)
    
    @classmethod
    def from_dict(cls, profile_data: Optional[Dict[str, Any]]) -> BucketResolver:
        """Create a BucketResolver from a dictionary.
        
        Args:
            profile_data: Dictionary from MongoDB bucket_profiles collection.
                         If None, creates a resolver that returns GLOBAL_DEFAULT_KEY.
        
        Returns:
            Configured BucketResolver instance.
        """
        if profile_data is None:
            return cls(profile=None)
        
        profile = BucketProfile.from_dict(profile_data)
        return cls(profile=profile)
