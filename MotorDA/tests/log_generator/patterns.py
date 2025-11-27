"""Value Generation Patterns

Defines patterns for generating field values. Similar to how bucket profiles
define time-context patterns, these define value generation patterns.

Usage:
    from log_generator.patterns import RandomPattern, TimeSeriesPattern
    
    # Random integers between 200-599
    status_pattern = RandomPattern(
        value_type="choice",
        choices=[200, 201, 404, 500, 502, 503],
        weights=[0.7, 0.1, 0.1, 0.03, 0.03, 0.04]
    )
    
    # Time series with daily pattern
    request_count = TimeSeriesPattern(
        base_value=1000,
        noise_std=50,
        daily_pattern={"09": 1.5, "12": 1.8, "18": 1.3, "03": 0.3}
    )
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
import random
import math


class ValuePattern(ABC):
    """Abstract base class for value generation patterns."""
    
    @abstractmethod
    def generate(self, timestamp: datetime, context: Dict[str, Any] = None) -> Any:
        """Generate a value, optionally using timestamp and context.
        
        Args:
            timestamp: Current timestamp for time-aware patterns
            context: Additional context (e.g., previous values, other fields)
        
        Returns:
            Generated value
        """
        pass
    
    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Serialize pattern to dictionary."""
        pass
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ValuePattern":
        """Deserialize pattern from dictionary."""
        pattern_type = data.get("type")
        
        if pattern_type == "constant":
            return ConstantPattern.from_dict(data)
        elif pattern_type == "random":
            return RandomPattern.from_dict(data)
        elif pattern_type == "choice":
            return ChoicePattern.from_dict(data)
        elif pattern_type == "time_series":
            return TimeSeriesPattern.from_dict(data)
        elif pattern_type == "sequence":
            return SequencePattern.from_dict(data)
        elif pattern_type == "template":
            return TemplatePattern.from_dict(data)
        else:
            raise ValueError(f"Unknown pattern type: {pattern_type}")


@dataclass
class ConstantPattern(ValuePattern):
    """Always returns the same value."""
    
    value: Any
    
    def generate(self, timestamp: datetime, context: Dict[str, Any] = None) -> Any:
        return self.value
    
    def to_dict(self) -> Dict[str, Any]:
        return {"type": "constant", "value": self.value}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConstantPattern":
        return cls(value=data["value"])


@dataclass
class RandomPattern(ValuePattern):
    """Generates random values within a range."""
    
    min_value: float = 0.0
    max_value: float = 100.0
    value_type: str = "float"  # "float", "int"
    
    def generate(self, timestamp: datetime, context: Dict[str, Any] = None) -> Any:
        if self.value_type == "int":
            return random.randint(int(self.min_value), int(self.max_value))
        return random.uniform(self.min_value, self.max_value)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "random",
            "min_value": self.min_value,
            "max_value": self.max_value,
            "value_type": self.value_type,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RandomPattern":
        return cls(
            min_value=data.get("min_value", 0.0),
            max_value=data.get("max_value", 100.0),
            value_type=data.get("value_type", "float"),
        )


@dataclass
class ChoicePattern(ValuePattern):
    """Selects from a list of choices with optional weights."""
    
    choices: List[Any]
    weights: Optional[List[float]] = None
    
    def generate(self, timestamp: datetime, context: Dict[str, Any] = None) -> Any:
        if self.weights:
            return random.choices(self.choices, weights=self.weights, k=1)[0]
        return random.choice(self.choices)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {"type": "choice", "choices": self.choices}
        if self.weights:
            result["weights"] = self.weights
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChoicePattern":
        return cls(
            choices=data["choices"],
            weights=data.get("weights"),
        )


@dataclass
class TimeSeriesPattern(ValuePattern):
    """Generates values with time-based patterns.
    
    Supports:
    - Base value with Gaussian noise
    - Daily patterns (hour-based multipliers)
    - Weekly patterns (weekday-based multipliers)
    - Trend (linear drift over time)
    - Anomaly injection
    """
    
    base_value: float = 100.0
    noise_std: float = 10.0
    
    # Hour -> multiplier (0-23)
    daily_pattern: Optional[Dict[str, float]] = None
    
    # Weekday -> multiplier (0=Monday, 6=Sunday)
    weekly_pattern: Optional[Dict[str, float]] = None
    
    # Linear trend per hour
    trend_per_hour: float = 0.0
    
    # Anomaly injection
    anomaly_probability: float = 0.0
    anomaly_multiplier: float = 3.0
    
    # Reference time for trend calculation
    _reference_time: Optional[datetime] = field(default=None, repr=False)
    
    def generate(self, timestamp: datetime, context: Dict[str, Any] = None) -> Any:
        context = context or {}
        
        # Start with base value
        value = self.base_value
        
        # Apply daily pattern
        if self.daily_pattern:
            hour_str = str(timestamp.hour)
            hour_mult = self.daily_pattern.get(hour_str, 1.0)
            value *= hour_mult
        
        # Apply weekly pattern
        if self.weekly_pattern:
            weekday_str = str(timestamp.weekday())
            weekday_mult = self.weekly_pattern.get(weekday_str, 1.0)
            value *= weekday_mult
        
        # Apply trend
        if self.trend_per_hour != 0.0:
            ref_time = self._reference_time or datetime(2025, 1, 1, tzinfo=timezone.utc)
            hours_elapsed = (timestamp - ref_time).total_seconds() / 3600
            value += self.trend_per_hour * hours_elapsed
        
        # Add noise
        if self.noise_std > 0:
            value += random.gauss(0, self.noise_std)
        
        # Inject anomaly?
        force_anomaly = context.get("force_anomaly", False)
        if force_anomaly or (self.anomaly_probability > 0 and random.random() < self.anomaly_probability):
            # Anomaly: spike up or down
            direction = random.choice([1, -1])
            value = value + (direction * abs(value) * self.anomaly_multiplier)
            if context is not None:
                context["is_anomaly"] = True
        
        return max(0, value)  # Ensure non-negative
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "time_series",
            "base_value": self.base_value,
            "noise_std": self.noise_std,
            "daily_pattern": self.daily_pattern,
            "weekly_pattern": self.weekly_pattern,
            "trend_per_hour": self.trend_per_hour,
            "anomaly_probability": self.anomaly_probability,
            "anomaly_multiplier": self.anomaly_multiplier,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TimeSeriesPattern":
        return cls(
            base_value=data.get("base_value", 100.0),
            noise_std=data.get("noise_std", 10.0),
            daily_pattern=data.get("daily_pattern"),
            weekly_pattern=data.get("weekly_pattern"),
            trend_per_hour=data.get("trend_per_hour", 0.0),
            anomaly_probability=data.get("anomaly_probability", 0.0),
            anomaly_multiplier=data.get("anomaly_multiplier", 3.0),
        )


@dataclass
class SequencePattern(ValuePattern):
    """Generates sequential values (IDs, counters)."""
    
    start: int = 1
    step: int = 1
    prefix: str = ""
    suffix: str = ""
    _current: int = field(default=None, repr=False)
    
    def __post_init__(self):
        if self._current is None:
            self._current = self.start
    
    def generate(self, timestamp: datetime, context: Dict[str, Any] = None) -> Any:
        value = f"{self.prefix}{self._current}{self.suffix}"
        self._current += self.step
        return value
    
    def reset(self):
        """Reset sequence to start value."""
        self._current = self.start
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "sequence",
            "start": self.start,
            "step": self.step,
            "prefix": self.prefix,
            "suffix": self.suffix,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SequencePattern":
        return cls(
            start=data.get("start", 1),
            step=data.get("step", 1),
            prefix=data.get("prefix", ""),
            suffix=data.get("suffix", ""),
        )


@dataclass
class TemplatePattern(ValuePattern):
    """Generates values from a template with placeholders.
    
    Example:
        TemplatePattern(
            template="{ip} - - [{timestamp}] \"{method} {path} HTTP/1.1\" {status}",
            field_refs={"ip": "client_ip", "method": "http_method"}
        )
    """
    
    template: str
    field_refs: Dict[str, str] = field(default_factory=dict)
    
    def generate(self, timestamp: datetime, context: Dict[str, Any] = None) -> Any:
        context = context or {}
        
        # Build substitution dict
        subs = {
            "timestamp": timestamp.isoformat(),
            "date": timestamp.strftime("%Y-%m-%d"),
            "time": timestamp.strftime("%H:%M:%S"),
            "hour": str(timestamp.hour),
            "minute": str(timestamp.minute),
        }
        
        # Add field references from context
        for placeholder, field_name in self.field_refs.items():
            if field_name in context:
                subs[placeholder] = str(context[field_name])
        
        # Also add any extra context directly
        for key, value in context.items():
            if key not in subs:
                subs[key] = str(value)
        
        try:
            return self.template.format(**subs)
        except KeyError as e:
            # Return partial substitution if some keys missing
            result = self.template
            for key, val in subs.items():
                result = result.replace(f"{{{key}}}", str(val))
            return result
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "template",
            "template": self.template,
            "field_refs": self.field_refs,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TemplatePattern":
        return cls(
            template=data["template"],
            field_refs=data.get("field_refs", {}),
        )
