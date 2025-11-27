"""Log Generator

Main class that generates log documents based on a schema.
Controls timing, volume, and anomaly injection.

Usage:
    from log_generator import LogGenerator, LogSchema
    
    schema = LogSchema.from_dict({...})
    generator = LogGenerator(schema)
    
    # Generate 1000 logs over 24 hours
    logs = generator.generate_batch(
        start_time=datetime(2025, 1, 1),
        end_time=datetime(2025, 1, 2),
        count=1000,
    )
    
    # Inject specific anomalies
    logs = generator.generate_with_anomalies(
        start_time=datetime(2025, 1, 1),
        end_time=datetime(2025, 1, 2),
        normal_count=1000,
        anomaly_times=[datetime(2025, 1, 1, 12, 0)],
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import random

try:
    from .log_schema import LogSchema
except ImportError:
    from log_schema import LogSchema


@dataclass
class GenerationResult:
    """Result of log generation."""
    documents: List[Dict[str, Any]]
    total_count: int
    anomaly_count: int
    anomaly_indices: List[int]
    start_time: datetime
    end_time: datetime
    
    def get_anomalies(self) -> List[Dict[str, Any]]:
        """Get only the anomaly documents."""
        return [self.documents[i] for i in self.anomaly_indices]


@dataclass
class LogGenerator:
    """Generates log documents based on a schema.
    
    Attributes:
        schema: The log schema to use
        seed: Random seed for reproducibility
    """
    
    schema: LogSchema
    seed: Optional[int] = None
    
    def __post_init__(self):
        if self.seed is not None:
            random.seed(self.seed)
    
    def generate_single(
        self,
        timestamp: datetime,
        overrides: Optional[Dict[str, Any]] = None,
        force_anomaly: bool = False,
    ) -> Dict[str, Any]:
        """Generate a single log document.
        
        Args:
            timestamp: Timestamp for the log
            overrides: Field value overrides
            force_anomaly: Force anomaly in time series fields
        
        Returns:
            Log document dict
        """
        return self.schema.generate_document(
            timestamp=timestamp,
            overrides=overrides,
            force_anomaly=force_anomaly,
        )
    
    def generate_batch(
        self,
        start_time: datetime,
        end_time: datetime,
        count: int,
        distribution: str = "uniform",
    ) -> GenerationResult:
        """Generate a batch of logs over a time range.
        
        Args:
            start_time: Start of time range
            end_time: End of time range
            count: Number of logs to generate
            distribution: "uniform" or "random"
        
        Returns:
            GenerationResult with all documents
        """
        if count <= 0:
            return GenerationResult(
                documents=[],
                total_count=0,
                anomaly_count=0,
                anomaly_indices=[],
                start_time=start_time,
                end_time=end_time,
            )
        
        # Generate timestamps
        if distribution == "uniform":
            timestamps = self._uniform_timestamps(start_time, end_time, count)
        else:
            timestamps = self._random_timestamps(start_time, end_time, count)
        
        # Generate documents
        documents = []
        anomaly_indices = []
        
        for i, ts in enumerate(timestamps):
            doc = self.schema.generate_document(ts)
            documents.append(doc)
            
            # Check if any time series pattern marked this as anomaly
            if doc.get("_is_anomaly"):
                anomaly_indices.append(i)
                del doc["_is_anomaly"]
        
        return GenerationResult(
            documents=documents,
            total_count=len(documents),
            anomaly_count=len(anomaly_indices),
            anomaly_indices=anomaly_indices,
            start_time=start_time,
            end_time=end_time,
        )
    
    def generate_with_anomalies(
        self,
        start_time: datetime,
        end_time: datetime,
        normal_count: int,
        anomaly_times: List[datetime],
        anomaly_overrides: Optional[Dict[str, Any]] = None,
    ) -> GenerationResult:
        """Generate logs with specific anomalies at given times.
        
        Args:
            start_time: Start of time range
            end_time: End of time range
            normal_count: Number of normal logs
            anomaly_times: Specific times for anomalies
            anomaly_overrides: Field overrides for anomaly docs
        
        Returns:
            GenerationResult with anomalies at specified times
        """
        # Generate normal logs
        normal_timestamps = self._uniform_timestamps(start_time, end_time, normal_count)
        
        # Combine and sort
        all_entries = [(ts, False) for ts in normal_timestamps]
        all_entries.extend((ts, True) for ts in anomaly_times)
        all_entries.sort(key=lambda x: x[0])
        
        documents = []
        anomaly_indices = []
        
        for i, (ts, is_anomaly) in enumerate(all_entries):
            if is_anomaly:
                doc = self.schema.generate_document(
                    ts, 
                    overrides=anomaly_overrides,
                    force_anomaly=True,
                )
                anomaly_indices.append(i)
            else:
                doc = self.schema.generate_document(ts)
            
            documents.append(doc)
        
        return GenerationResult(
            documents=documents,
            total_count=len(documents),
            anomaly_count=len(anomaly_indices),
            anomaly_indices=anomaly_indices,
            start_time=start_time,
            end_time=end_time,
        )
    
    def generate_hourly_buckets(
        self,
        start_time: datetime,
        end_time: datetime,
        anomaly_hours: Optional[List[int]] = None,
    ) -> GenerationResult:
        """Generate one log per hour (for aggregated data).
        
        Useful for testing with pre-aggregated metrics where each
        document represents an hourly bucket.
        
        Args:
            start_time: Start of range (will be truncated to hour)
            end_time: End of range
            anomaly_hours: List of hours (0-23) to inject anomalies
        
        Returns:
            GenerationResult with hourly documents
        """
        anomaly_hours = set(anomaly_hours or [])
        
        # Truncate to hour
        current = start_time.replace(minute=0, second=0, microsecond=0)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        
        documents = []
        anomaly_indices = []
        
        i = 0
        while current < end_time:
            is_anomaly = current.hour in anomaly_hours
            
            doc = self.schema.generate_document(
                current,
                force_anomaly=is_anomaly,
            )
            documents.append(doc)
            
            if is_anomaly:
                anomaly_indices.append(i)
            
            current += timedelta(hours=1)
            i += 1
        
        return GenerationResult(
            documents=documents,
            total_count=len(documents),
            anomaly_count=len(anomaly_indices),
            anomaly_indices=anomaly_indices,
            start_time=start_time,
            end_time=end_time,
        )
    
    def _uniform_timestamps(
        self, 
        start: datetime, 
        end: datetime, 
        count: int
    ) -> List[datetime]:
        """Generate uniformly spaced timestamps."""
        if count <= 1:
            return [start]
        
        delta = (end - start) / (count - 1)
        return [start + delta * i for i in range(count)]
    
    def _random_timestamps(
        self, 
        start: datetime, 
        end: datetime, 
        count: int
    ) -> List[datetime]:
        """Generate randomly distributed timestamps."""
        total_seconds = (end - start).total_seconds()
        timestamps = [
            start + timedelta(seconds=random.random() * total_seconds)
            for _ in range(count)
        ]
        return sorted(timestamps)
