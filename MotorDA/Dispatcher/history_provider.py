"""History Provider - Fetches recent values for SERIES algorithms.

This module provides the infrastructure for SERIES mode algorithms that need
access to historical values at detection time.

For SERIES algorithms like ARMA/ARMAX/LSTM:
- Detection requires the last N values (where N = required_history_length)
- This provider fetches those values from MongoDB or a cache

Usage:
    from MotorDA.Dispatcher.history_provider import HistoryProvider
    
    provider = HistoryProvider.create(mongo_client, db_name)
    
    # Get history for detection
    history = provider.get_history(
        kb_id="...",
        dimension="status_5xx",
        timestamp=current_timestamp,
        window_size=10  # From algorithm.required_history_length
    )
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import threading

from pymongo import MongoClient, DESCENDING
import pandas as pd


@dataclass
class HistoryEntry:
    """A single historical data point."""
    timestamp: datetime
    value: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat() if hasattr(self.timestamp, 'isoformat') else str(self.timestamp),
            "value": self.value,
        }


@dataclass
class HistoryWindow:
    """A window of historical values for a dimension."""
    entries: List[HistoryEntry]
    dimension: str
    kb_id: str
    
    @property
    def values(self) -> List[float]:
        """Get just the values in chronological order."""
        return [e.value for e in sorted(self.entries, key=lambda e: e.timestamp)]
    
    @property
    def timestamps(self) -> List[datetime]:
        """Get just the timestamps in chronological order."""
        return [e.timestamp for e in sorted(self.entries, key=lambda e: e.timestamp)]
    
    def to_list(self) -> List[Dict[str, Any]]:
        """Convert to list of dicts for algorithm interface."""
        sorted_entries = sorted(self.entries, key=lambda e: e.timestamp)
        return [e.to_dict() for e in sorted_entries]
    
    def __len__(self) -> int:
        return len(self.entries)


class HistoryCache:
    """In-memory cache for recent history values.
    
    Maintains a sliding window of recent values per (kb_id, dimension) pair
    to avoid repeated MongoDB queries.
    """
    
    def __init__(self, max_entries_per_dimension: int = 1000):
        self._cache: Dict[Tuple[str, str], List[HistoryEntry]] = defaultdict(list)
        self._max_entries = max_entries_per_dimension
        self._lock = threading.Lock()
    
    def add(self, kb_id: str, dimension: str, entry: HistoryEntry) -> None:
        """Add a new entry to the cache."""
        key = (kb_id, dimension)
        with self._lock:
            self._cache[key].append(entry)
            # Trim if over limit
            if len(self._cache[key]) > self._max_entries:
                # Keep most recent entries
                self._cache[key] = sorted(
                    self._cache[key], 
                    key=lambda e: e.timestamp
                )[-self._max_entries:]
    
    def get_recent(
        self, 
        kb_id: str, 
        dimension: str, 
        before: datetime, 
        count: int
    ) -> List[HistoryEntry]:
        """Get up to `count` entries before the given timestamp."""
        key = (kb_id, dimension)
        with self._lock:
            entries = self._cache.get(key, [])
            # Filter entries before timestamp and sort descending
            recent = [e for e in entries if e.timestamp < before]
            recent.sort(key=lambda e: e.timestamp, reverse=True)
            return recent[:count]
    
    def clear(self, kb_id: Optional[str] = None, dimension: Optional[str] = None) -> None:
        """Clear cache entries."""
        with self._lock:
            if kb_id is None and dimension is None:
                self._cache.clear()
            elif kb_id and dimension:
                key = (kb_id, dimension)
                if key in self._cache:
                    del self._cache[key]
            elif kb_id:
                keys_to_remove = [k for k in self._cache if k[0] == kb_id]
                for key in keys_to_remove:
                    del self._cache[key]


@dataclass
class HistoryProvider:
    """Provides historical values for SERIES algorithm detection.
    
    This is the main interface for SERIES algorithms to access history.
    It combines MongoDB queries with an in-memory cache for efficiency.
    """
    
    mongo_client: MongoClient
    db_name: str
    series_collection_name: str = "series"
    cache: HistoryCache = field(default_factory=lambda: HistoryCache())
    
    @classmethod
    def create(
        cls, 
        mongo_client: MongoClient, 
        db_name: str = "anomaly_detection",
        series_collection_name: str = "series",
        cache_size: int = 1000,
    ) -> "HistoryProvider":
        """Factory method to create a HistoryProvider.
        
        Args:
            mongo_client: MongoDB client
            db_name: Database name
            series_collection_name: Collection containing series data
            cache_size: Max entries per dimension in cache
        
        Returns:
            HistoryProvider instance
        """
        cache = HistoryCache(max_entries_per_dimension=cache_size)
        return cls(
            mongo_client=mongo_client,
            db_name=db_name,
            series_collection_name=series_collection_name,
            cache=cache,
        )
    
    def get_history(
        self,
        kb_id: str,
        dimension: str,
        before_timestamp: datetime,
        window_size: int,
        use_cache: bool = True,
    ) -> HistoryWindow:
        """Get historical values before a timestamp.
        
        This is the main method for SERIES algorithms to get history.
        
        Args:
            kb_id: Knowledge Base ID
            dimension: Metric dimension
            before_timestamp: Get values before this time
            window_size: Number of values to retrieve
            use_cache: Whether to use cache (default True)
        
        Returns:
            HistoryWindow with the requested values
        """
        entries: List[HistoryEntry] = []
        
        # Try cache first
        if use_cache:
            cached = self.cache.get_recent(kb_id, dimension, before_timestamp, window_size)
            if len(cached) >= window_size:
                return HistoryWindow(
                    entries=cached[:window_size],
                    dimension=dimension,
                    kb_id=kb_id,
                )
            entries = cached
        
        # Need more from MongoDB
        needed = window_size - len(entries)
        if needed > 0:
            # Determine cutoff - don't re-fetch cached entries
            if entries:
                oldest_cached = min(e.timestamp for e in entries)
                cutoff = oldest_cached
            else:
                cutoff = before_timestamp
            
            db_entries = self._fetch_from_mongo(
                kb_id=kb_id,
                dimension=dimension,
                before_timestamp=cutoff,
                limit=needed,
            )
            entries.extend(db_entries)
        
        # Sort chronologically (oldest first)
        entries.sort(key=lambda e: e.timestamp)
        
        return HistoryWindow(
            entries=entries[-window_size:],  # Take most recent N
            dimension=dimension,
            kb_id=kb_id,
        )
    
    def _fetch_from_mongo(
        self,
        kb_id: str,
        dimension: str,
        before_timestamp: datetime,
        limit: int,
    ) -> List[HistoryEntry]:
        """Fetch historical entries from MongoDB."""
        collection = self.mongo_client[self.db_name][self.series_collection_name]
        
        # Query for detection mode (mode=1) data
        query = {
            "metadata.kbId": kb_id,
            "metadata.dim": dimension,
            "timestamp": {"$lt": before_timestamp},
        }
        
        cursor = collection.find(query).sort("timestamp", DESCENDING).limit(limit)
        
        entries = []
        for doc in cursor:
            ts = doc.get("timestamp")
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            
            value = doc.get("value", 0)
            if isinstance(value, dict):
                value = float(value.get("$numberLong", 0))
            else:
                value = float(value)
            
            entries.append(HistoryEntry(timestamp=ts, value=value))
        
        return entries
    
    def add_to_cache(
        self,
        kb_id: str,
        dimension: str,
        timestamp: datetime,
        value: float,
    ) -> None:
        """Add a new data point to the cache.
        
        Call this when new detection data arrives to keep cache fresh.
        
        Args:
            kb_id: Knowledge Base ID
            dimension: Metric dimension
            timestamp: Timestamp of the value
            value: The metric value
        """
        entry = HistoryEntry(timestamp=timestamp, value=value)
        self.cache.add(kb_id, dimension, entry)
    
    def preload_history(
        self,
        kb_id: str,
        dimension: str,
        from_timestamp: datetime,
        to_timestamp: datetime,
    ) -> int:
        """Preload history into cache from a time range.
        
        Useful when starting detection for a dimension.
        
        Args:
            kb_id: Knowledge Base ID
            dimension: Metric dimension
            from_timestamp: Start of time range
            to_timestamp: End of time range
        
        Returns:
            Number of entries loaded
        """
        collection = self.mongo_client[self.db_name][self.series_collection_name]
        
        query = {
            "metadata.kbId": kb_id,
            "metadata.dim": dimension,
            "timestamp": {"$gte": from_timestamp, "$lte": to_timestamp},
        }
        
        cursor = collection.find(query).sort("timestamp", DESCENDING)
        
        count = 0
        for doc in cursor:
            ts = doc.get("timestamp")
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            
            value = doc.get("value", 0)
            if isinstance(value, dict):
                value = float(value.get("$numberLong", 0))
            else:
                value = float(value)
            
            self.cache.add(kb_id, dimension, HistoryEntry(timestamp=ts, value=value))
            count += 1
        
        return count
    
    def clear_cache(
        self, 
        kb_id: Optional[str] = None, 
        dimension: Optional[str] = None
    ) -> None:
        """Clear the history cache.
        
        Args:
            kb_id: Optional - clear only this KB's cache
            dimension: Optional - clear only this dimension's cache
        """
        self.cache.clear(kb_id, dimension)


# Global instance for dispatcher (initialized lazily)
_history_provider: Optional[HistoryProvider] = None


def get_history_provider(mongo_client: MongoClient, db_name: str = "anomaly_detection") -> HistoryProvider:
    """Get or create the global HistoryProvider instance.
    
    Args:
        mongo_client: MongoDB client
        db_name: Database name
    
    Returns:
        HistoryProvider instance
    """
    global _history_provider
    if _history_provider is None:
        _history_provider = HistoryProvider.create(mongo_client, db_name)
    return _history_provider
