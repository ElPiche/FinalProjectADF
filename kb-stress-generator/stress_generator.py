#!/usr/bin/env python3
"""
KB Stress Generator - Stress Test for Anomaly Detection Framework

Periodically creates KB configurations AND bucket profiles to stress test the stack:
- Extractor (ETL pipeline)
- DA-Dispatcher (anomaly detection)
- MongoDB (change streams)
- Elasticsearch (queries)

Features:
- Dynamic algorithm discovery from shared Docker volume
- Continuous config generation at random intervals
- Burst mode: occasionally spam multiple configs at once
- Creates bucket profiles with various time-context patterns
- Randomized query patterns, dimensions, and schedules
- Configurable source index via SOURCE_INDEX env var (default: ecommerce-logs)
- All queries are pre-validated against Elasticsearch SQL
"""

import os
import sys
import json
import time
import random
import signal
import logging
import argparse
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from pathlib import Path
import uuid

from pymongo import MongoClient
from faker import Faker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
running = True


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global running
    if running:
        logger.info("Received shutdown signal. Stopping stress generator...")
        running = False


@dataclass
class StressGeneratorConfig:
    """Configuration for the stress generator."""
    
    mongodb_uri: str = "mongodb://admin:1q2w3E%2A@mongodb:27017/?authSource=admin&replicaSet=rs0"
    mongodb_db: str = "knowledge_base"  # ETL expects configs in knowledge_base database
    mongodb_collection: str = "kb_configs"  # Must match ETL expectation
    bucket_collection: str = "bucket_profiles"  # For bucket profiles
    es_url: str = "http://elasticsearch-dataset:9200"
    source_index: str = "ecommerce-logs"  # Target index for KB configs (must match log-generator INDEX_NAME)
    historical_days: int = 365  # Must match log-generator HISTORICAL_DAYS setting
    algorithm_registry_path: str = "/app/registry/algorithms.json"  # Shared volume
    
    mode: str = "continuous"  # continuous, burst, single
    min_interval: int = 30  # seconds between configs
    max_interval: int = 120
    burst_probability: float = 0.1  # 10% chance of burst
    burst_size_min: int = 3
    burst_size_max: int = 10
    bucket_probability: float = 0.3  # 30% chance to create a bucket profile
    
    seed: Optional[int] = None
    
    @classmethod
    def from_env(cls) -> "StressGeneratorConfig":
        """Create config from environment variables."""
        return cls(
            mongodb_uri=os.getenv("MONGODB_URI", cls.mongodb_uri),
            mongodb_db=os.getenv("MONGODB_DB", cls.mongodb_db),
            mongodb_collection=os.getenv("MONGODB_COLLECTION", cls.mongodb_collection),
            bucket_collection=os.getenv("BUCKET_COLLECTION", cls.bucket_collection),
            es_url=os.getenv("ES_URL", cls.es_url),
            source_index=os.getenv("SOURCE_INDEX", cls.source_index),
            historical_days=int(os.getenv("HISTORICAL_DAYS", str(cls.historical_days))),
            algorithm_registry_path=os.getenv("ALGORITHM_REGISTRY_PATH", cls.algorithm_registry_path),
            mode=os.getenv("MODE", cls.mode),
            min_interval=int(os.getenv("MIN_INTERVAL", str(cls.min_interval))),
            max_interval=int(os.getenv("MAX_INTERVAL", str(cls.max_interval))),
            burst_probability=float(os.getenv("BURST_PROBABILITY", str(cls.burst_probability))),
            burst_size_min=int(os.getenv("BURST_SIZE_MIN", str(cls.burst_size_min))),
            burst_size_max=int(os.getenv("BURST_SIZE_MAX", str(cls.burst_size_max))),
            bucket_probability=float(os.getenv("BUCKET_PROBABILITY", str(cls.bucket_probability))),
            seed=int(os.getenv("SEED")) if os.getenv("SEED") else None,
        )


class BucketProfileGenerator:
    """Generates randomized bucket profiles for time-context anomaly detection."""
    
    def __init__(self, seed: Optional[int] = None):
        self.fake = Faker()
        if seed is not None:
            random.seed(seed)
            Faker.seed(seed)
        
        self.profile_counter = 0
        
        # Timezones to use
        self.timezones = [
            "America/Montevideo",
            "America/New_York",
            "America/Los_Angeles",
            "Europe/London",
            "Europe/Madrid",
            "Asia/Tokyo",
            "UTC",
        ]
        
        # Profile name templates
        self.profile_templates = [
            "stress_profile_{num}",
            "auto_bucket_{num}",
            "load_test_profile_{num}",
            "synthetic_context_{num}",
        ]
    
    def generate_schedule_rule(self) -> Dict[str, Any]:
        """Generate a random schedule rule."""
        # Random days (weekdays, weekends, or mix)
        day_patterns = [
            [1, 2, 3, 4, 5],  # Weekdays
            [6, 7],  # Weekend
            [1, 2, 3, 4, 5, 6, 7],  # All days
            random.sample(range(1, 8), random.randint(2, 5)),  # Random mix
        ]
        days = random.choice(day_patterns)
        
        # Random time ranges
        start_hour = random.randint(0, 18)
        end_hour = random.randint(start_hour + 2, min(start_hour + 12, 23))
        
        time_range = {
            "start": f"{start_hour:02d}:00",
            "end": f"{end_hour:02d}:00",
        }
        
        # Bucket base keys
        base_keys = [
            "workday", "business_hours", "peak_traffic", "morning_rush",
            "afternoon", "evening", "night_shift", "maintenance_window",
        ]
        
        granularities = ["hourly", "block"]
        
        return {
            "bucket_base_key": random.choice(base_keys),
            "days": sorted(days),
            "time_range": time_range,
            "granularity": random.choice(granularities),
        }
    
    def generate_exception_rule(self) -> Dict[str, Any]:
        """Generate a random exception rule (holiday/special day)."""
        # Random month and day
        month = random.randint(1, 12)
        day = random.randint(1, 28)  # Safe for all months
        
        exception_keys = [
            "holiday", "maintenance", "special_event", "blackout",
            "sale_day", "release_day", "audit_window",
        ]
        
        return {
            "bucket_base_key": f"{random.choice(exception_keys)}_{month}_{day}",
            "rule": {
                "month": month,
                "day": day,
                "year": None,  # Recurring yearly
            },
            "granularity": random.choice(["block", "hourly"]),
        }
    
    def generate_profile(self) -> Dict[str, Any]:
        """Generate a complete bucket profile."""
        self.profile_counter += 1
        
        template = random.choice(self.profile_templates)
        profile_id = template.format(num=self.profile_counter)
        
        # Generate 1-4 schedule rules
        num_schedules = random.randint(1, 4)
        schedule = [self.generate_schedule_rule() for _ in range(num_schedules)]
        
        # 50% chance to have exceptions
        exceptions = None
        if random.random() < 0.5:
            num_exceptions = random.randint(1, 3)
            exceptions = [self.generate_exception_rule() for _ in range(num_exceptions)]
        
        # Fallback configuration
        fallback_keys = ["off_hours", "default", "baseline", "quiet_period"]
        fallback = {
            "bucket_base_key": random.choice(fallback_keys),
            "granularity": random.choice(["hourly", "block"]),
        }
        
        return {
            "profile_id": profile_id,
            "timezone": random.choice(self.timezones),
            "schedule": schedule,
            "exceptions": exceptions,
            "fallback": fallback,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "kb-stress-generator",
        }


class AlgorithmRegistry:
    """Reads and manages available algorithms from the shared Docker volume."""
    
    # Default algorithms in case registry file is not available
    DEFAULT_ALGORITHMS = {
        "zscore": {
            "name": "zscore",
            "description": "Z-Score statistical anomaly detection",
            "parameters": ["percentile", "min_points"],
        },
        "iqr": {
            "name": "iqr",
            "description": "IQR-based outlier detection",
            "parameters": ["multiplier"],
        },
        "mock": {
            "name": "mock",
            "description": "Mock algorithm for testing",
            "parameters": ["percentile"],
        },
    }
    
    def __init__(self, registry_path: str = "/app/registry/algorithms.json"):
        self.registry_path = Path(registry_path)
        self._algorithms: Dict[str, Any] = {}
        self._last_load_time: Optional[datetime] = None
        self._reload_interval = timedelta(minutes=5)  # Reload every 5 minutes
        
        # Initial load
        self._load_registry()
    
    def _load_registry(self) -> None:
        """Load algorithms from the registry file."""
        try:
            if self.registry_path.exists():
                with open(self.registry_path, 'r') as f:
                    self._algorithms = json.load(f)
                self._last_load_time = datetime.now(timezone.utc)
                logger.info(f"📚 Loaded {len(self._algorithms)} algorithms from registry: {list(self._algorithms.keys())}")
            else:
                logger.warning(f"⚠️ Algorithm registry not found at {self.registry_path}, using defaults")
                self._algorithms = self.DEFAULT_ALGORITHMS.copy()
        except Exception as e:
            logger.error(f"❌ Failed to load algorithm registry: {e}")
            self._algorithms = self.DEFAULT_ALGORITHMS.copy()
    
    def _maybe_reload(self) -> None:
        """Reload registry if enough time has passed."""
        now = datetime.now(timezone.utc)
        if self._last_load_time is None or (now - self._last_load_time) > self._reload_interval:
            self._load_registry()
    
    def get_algorithms(self) -> Dict[str, Any]:
        """Get all available algorithms (reloads periodically)."""
        self._maybe_reload()
        return self._algorithms.copy()
    
    def get_algorithm_names(self) -> List[str]:
        """Get list of algorithm names."""
        self._maybe_reload()
        return list(self._algorithms.keys())
    
    def get_random_algorithm(self) -> str:
        """Get a random algorithm name."""
        names = self.get_algorithm_names()
        return random.choice(names) if names else "zscore"
    
    def get_algorithm_info(self, name: str) -> Optional[Dict[str, Any]]:
        """Get info for a specific algorithm."""
        self._maybe_reload()
        return self._algorithms.get(name.lower())
    
    def get_algorithm_parameters(self, name: str) -> List[str]:
        """Get parameter names for an algorithm."""
        info = self.get_algorithm_info(name)
        if info:
            return info.get("parameters", [])
        return []


class KBConfigGenerator:
    """Generates randomized KB configurations for stress testing."""
    
    def __init__(
        self,
        source_index: str = "ecommerce-logs",
        historical_days: int = 365,
        algorithm_registry: Optional[AlgorithmRegistry] = None,
        seed: Optional[int] = None
    ):
        self.fake = Faker()
        self.source_index = source_index
        self.historical_days = historical_days  # From log-generator settings
        self.algorithm_registry = algorithm_registry or AlgorithmRegistry()
        
        if seed is not None:
            random.seed(seed)
            Faker.seed(seed)
        
        self.config_counter = 0
        
        # Query templates - {index} will be replaced with source_index
        # All queries have been validated against Elasticsearch SQL
        self.query_templates = [
            {
                "name": "status_codes",
                "description": "Monitor HTTP status code distribution",
                "sql": '''SELECT DATE_TRUNC('MINUTE', "@timestamp") AS bucket, SUM(CASE WHEN status_code = 200 THEN 1 ELSE 0 END) AS status_200_count, SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END) AS status_5xx_count, COUNT(*) AS total_requests FROM "{index}" WHERE "@timestamp" >= '$from' AND "@timestamp" < '$to' GROUP BY 1 ORDER BY bucket''',
                "dimensions": ["status_200_count", "status_5xx_count", "total_requests"],
            },
            {
                "name": "latency_metrics",
                "description": "Monitor API response latency",
                "sql": '''SELECT DATE_TRUNC('MINUTE', "@timestamp") AS bucket, AVG(response_time_ms) AS avg_latency, MAX(response_time_ms) AS max_latency, COUNT(*) AS request_count FROM "{index}" WHERE "@timestamp" >= '$from' AND "@timestamp" < '$to' GROUP BY 1 ORDER BY bucket''',
                "dimensions": ["avg_latency", "max_latency", "request_count"],
            },
            {
                "name": "error_traffic",
                "description": "Monitor error rates and traffic volume",
                "sql": '''SELECT DATE_TRUNC('MINUTE', "@timestamp") AS bucket, SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS error_count, SUM(bytes_sent) AS total_bytes, COUNT(*) AS total_count FROM "{index}" WHERE "@timestamp" >= '$from' AND "@timestamp" < '$to' GROUP BY 1 ORDER BY bucket''',
                "dimensions": ["error_count", "total_bytes", "total_count"],
            },
            {
                "name": "user_activity",
                "description": "Monitor unique users and endpoints",
                "sql": '''SELECT DATE_TRUNC('MINUTE', "@timestamp") AS bucket, COUNT(DISTINCT endpoint) AS unique_endpoints, COUNT(DISTINCT user_id) AS unique_users, COUNT(*) AS request_count FROM "{index}" WHERE "@timestamp" >= '$from' AND "@timestamp" < '$to' GROUP BY 1 ORDER BY bucket''',
                "dimensions": ["unique_endpoints", "unique_users", "request_count"],
            },
            {
                "name": "client_errors",
                "description": "Monitor 4xx client errors",
                "sql": '''SELECT DATE_TRUNC('MINUTE', "@timestamp") AS bucket, SUM(CASE WHEN status_code >= 400 AND status_code < 500 THEN 1 ELSE 0 END) AS client_errors, SUM(CASE WHEN status_code = 404 THEN 1 ELSE 0 END) AS not_found_count, COUNT(*) AS total_requests FROM "{index}" WHERE "@timestamp" >= '$from' AND "@timestamp" < '$to' GROUP BY 1 ORDER BY bucket''',
                "dimensions": ["client_errors", "not_found_count", "total_requests"],
            },
            {
                "name": "server_health",
                "description": "Monitor server errors and response times",
                "sql": '''SELECT DATE_TRUNC('MINUTE', "@timestamp") AS bucket, SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END) AS server_errors, AVG(response_time_ms) AS avg_response_time, COUNT(*) AS request_count FROM "{index}" WHERE "@timestamp" >= '$from' AND "@timestamp" < '$to' GROUP BY 1 ORDER BY bucket''',
                "dimensions": ["server_errors", "avg_response_time", "request_count"],
            },
            {
                "name": "hourly_traffic",
                "description": "Monitor hourly traffic patterns",
                "sql": '''SELECT DATE_TRUNC('hour', "@timestamp") AS bucket, COUNT(*) AS request_count, SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END) AS error_5xx_count, AVG(response_time_ms) AS avg_response_time FROM "{index}" WHERE "@timestamp" >= '$from' AND "@timestamp" < '$to' GROUP BY 1 ORDER BY bucket''',
                "dimensions": ["request_count", "error_5xx_count", "avg_response_time"],
            },
        ]
        
        # Detection frequencies (CRON expressions) - 6-field format for Spring
        # Format: second minute hour day month weekday
        self.detection_frequencies = [
            # Sub-minute frequencies (1-30 second intervals)
            "*/1 * * * * *",    # Every 1 second
            "*/2 * * * * *",    # Every 2 seconds
            "*/5 * * * * *",    # Every 5 seconds
            "*/10 * * * * *",   # Every 10 seconds
            "*/15 * * * * *",   # Every 15 seconds
            "*/30 * * * * *",   # Every 30 seconds
            # Minute-based frequencies
            "0 */1 * * * *",    # Every minute
            "0 */2 * * * *",    # Every 2 minutes
            "0 */5 * * * *",    # Every 5 minutes
        ]
        
        # Detection windows in seconds
        # IMPORTANT: With ~0.5 RPS data, we need longer windows to get enough samples:
        # - 60s = ~30 logs (minimum reasonable)
        # - 300s = ~150 logs (good)
        # - 600s = ~300 logs (better)
        # - 3600s = ~1800 logs (best for stable metrics)
        # Small windows (5s, 10s, 30s) don't work with low RPS data!
        self.detection_windows = [
            60,    # 1 minute - minimum reasonable with 0.5 RPS
            120,   # 2 minutes
            300,   # 5 minutes
            600,   # 10 minutes
            900,   # 15 minutes  
            1800,  # 30 minutes
            3600,  # 1 hour
        ]
        
        # Config name templates
        self.name_templates = [
            "Stress Test - {focus} Monitor #{num}",
            "Auto-Generated - {focus} Analyzer #{num}",
            "Load Test - {focus} Detector #{num}",
            "Synthetic - {focus} Watchdog #{num}",
            "Perf Test - {focus} Scanner #{num}",
        ]
        
        self.focus_areas = [
            "Traffic", "Error Rate", "Latency", "Status Codes",
            "Response Time", "Request Volume", "5xx Errors",
            "API Health", "User Activity", "Server Health",
        ]
    
    def _generate_training_period(self) -> tuple:
        """Generate a training period based on available historical data.
        
        IMPORTANT: Must respect the log-generator's HISTORICAL_DAYS setting.
        Historical data spans from (now - HISTORICAL_DAYS) to (now - buffer).
        
        Training windows are realistic for anomaly detection:
        - Short: 1-7 days (for quick tests)
        - Medium: 1-4 weeks (typical use case)  
        - Long: 1-6 months (comprehensive baseline)
        
        The training window is placed randomly within the available historical range.
        """
        now = datetime.now(timezone.utc)
        
        # Buffer: avoid the most recent data (gap between historical end and continuous start)
        buffer_days = 1  # Safe buffer to avoid timing edge cases
        
        # Maximum days back we can go (respecting log-generator's HISTORICAL_DAYS)
        max_days_back = self.historical_days - buffer_days
        
        # Choose training duration type randomly
        duration_type = random.choice(["short", "medium", "long"])
        
        if duration_type == "short":
            # 1-7 days of training data
            training_days = random.randint(1, 7)
        elif duration_type == "medium":
            # 1-4 weeks (7-28 days)
            training_days = random.randint(7, 28)
        else:  # long
            # 1-6 months (30-180 days), capped by available data
            training_days = random.randint(30, min(180, max_days_back - 7))
        
        # Ensure training_days doesn't exceed available data
        training_days = min(training_days, max_days_back - 7)
        
        # Pick where to end training (must leave room for training duration)
        # Training ends between (buffer_days + 7) and (max_days_back - training_days) days ago
        min_end_days_ago = buffer_days + 7  # At least 7 days ago
        max_end_days_ago = max_days_back - training_days  # Leave room for training window
        
        if max_end_days_ago < min_end_days_ago:
            # Fallback if historical_days is too small
            max_end_days_ago = min_end_days_ago
            training_days = min(7, max_days_back - min_end_days_ago)
        
        end_days_ago = random.randint(min_end_days_ago, max_end_days_ago)
        
        training_end = now - timedelta(days=end_days_ago)
        training_start = training_end - timedelta(days=training_days)
        
        return (
            training_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            training_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
    
    def _generate_detection_start(self, training_to: str) -> str:
        """Generate detection start time.
        
        Detection should start NOW (or very recently) since we want to detect
        on the continuous real-time data being generated.
        
        The training_to is in the past (yesterday), but detection runs on current data.
        """
        now = datetime.now(timezone.utc)
        # Detection starts NOW or up to 5 minutes ago
        detection_start = now - timedelta(minutes=random.randint(0, 5))
        return detection_start.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    def _generate_algorithm_metadata(self, algorithm_name: str) -> List[Dict[str, Any]]:
        """Generate algorithm-specific metadata based on its parameters."""
        metadata = []
        params = self.algorithm_registry.get_algorithm_parameters(algorithm_name)
        
        for param in params:
            if param == "percentile":
                metadata.append({
                    "key": "percentile",
                    "value": str(random.choice([95.0, 97.5, 99.0, 99.5]))
                })
            elif param == "min_points":
                metadata.append({
                    "key": "min_points",
                    "value": str(random.choice([3, 5, 10]))
                })
            elif param == "multiplier":
                # IQR multiplier: Higher values = less sensitive to outliers
                # 1.5 is standard but too tight for high-variance e-commerce data
                # Use 2.5-4.0 range for realistic detection
                metadata.append({
                    "key": "multiplier",
                    "value": str(random.choice([2.5, 3.0, 3.5, 4.0]))
                })
        
        return metadata if metadata else None
    
    def generate_config(self, bucket_profile_id: Optional[str] = None) -> Dict[str, Any]:
        """Generate a random KB configuration with a randomly selected algorithm."""
        self.config_counter += 1
        
        # Select random query template
        query_template = random.choice(self.query_templates)
        
        # Generate training period
        training_from, training_to = self._generate_training_period()
        detection_start = self._generate_detection_start(training_to)
        
        # Generate config name
        name_template = random.choice(self.name_templates)
        focus = random.choice(self.focus_areas)
        config_name = name_template.format(focus=focus, num=self.config_counter)
        
        # Select a random algorithm from the registry
        algorithm_name = self.algorithm_registry.get_random_algorithm()
        
        # Select dimensions (use 1-3 dimensions)
        available_dims = query_template["dimensions"]
        num_dims = min(len(available_dims), random.randint(1, 3))
        selected_dims = random.sample(available_dims, num_dims)
        
        # Build algorithm parameters with algorithm-specific metadata
        algorithm_params = []
        for dim in selected_dims:
            param = {
                "dimension": dim,
                "is_active": True,
            }
            # Add algorithm-specific metadata for some parameters
            if random.random() < 0.4:  # 40% chance
                metadata = self._generate_algorithm_metadata(algorithm_name)
                if metadata:
                    param["metadata"] = metadata
            algorithm_params.append(param)
        
        # Build the KB config document (matching MongoDB schema)
        config = {
            "name": config_name,
            "description": f"Auto-generated stress test: {query_template['description']}. "
                          f"Monitoring {', '.join(selected_dims)} using {algorithm_name.upper()} algorithm.",
            "change_flag": 0,
            "elasticsearch_sql_query": query_template["sql"].format(index=self.source_index),
            "source_index": self.source_index,
            "query_mode": {
                "type": "aggregated",
                "timestamp_field": "bucket",
            },
            "bucket_profile_id": bucket_profile_id,  # Can be None or a profile ID
            "scheduling": {
                "training_config": {
                    "type": "static",
                    "from": training_from,
                    "to": training_to,
                    "is_active": random.choice([True, True, True, False]),  # 75% active
                },
                "detection_config": {
                    "from": detection_start,
                    "frequency": random.choice(self.detection_frequencies),
                    "detection_window": random.choice(self.detection_windows),
                    "is_active": random.choice([True, True, True, False]),  # 75% active
                },
            },
            "algorithm": {
                "name": algorithm_name,
                "parameters": algorithm_params,
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "kb-stress-generator",
        }
        
        return config


class StressGenerator:
    """Main stress generator that creates KB configs and bucket profiles."""
    
    def __init__(self, config: StressGeneratorConfig):
        self.config = config
        
        # Initialize algorithm registry from shared volume
        self.algorithm_registry = AlgorithmRegistry(config.algorithm_registry_path)
        
        self.kb_generator = KBConfigGenerator(
            source_index=config.source_index,
            historical_days=config.historical_days,
            algorithm_registry=self.algorithm_registry,
            seed=config.seed
        )
        self.bucket_generator = BucketProfileGenerator(config.seed)
        self.mongo_client: Optional[MongoClient] = None
        self.db = None
        self.kb_collection = None
        self.bucket_collection = None
        
        self.total_configs_created = 0
        self.total_buckets_created = 0
        self.total_bursts = 0
        self.created_bucket_ids: List[str] = []
        self.algorithm_usage_counts: Dict[str, int] = {}  # Track algorithm usage
        
        # Set up signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def connect_mongodb(self) -> bool:
        """Connect to MongoDB."""
        try:
            logger.info(f"Connecting to MongoDB...")
            self.mongo_client = MongoClient(
                self.config.mongodb_uri,
                serverSelectionTimeoutMS=10000,
            )
            # Test connection
            self.mongo_client.admin.command('ping')
            
            self.db = self.mongo_client[self.config.mongodb_db]
            self.kb_collection = self.db[self.config.mongodb_collection]
            self.bucket_collection = self.db[self.config.bucket_collection]
            
            # Load existing bucket profile IDs
            existing_profiles = self.bucket_collection.find({}, {"profile_id": 1})
            self.created_bucket_ids = [p["profile_id"] for p in existing_profiles if "profile_id" in p]
            
            logger.info(f"Connected to MongoDB: {self.config.mongodb_db}")
            logger.info(f"  KB configs collection: {self.config.mongodb_collection}")
            logger.info(f"  Bucket profiles collection: {self.config.bucket_collection}")
            logger.info(f"  Existing bucket profiles: {len(self.created_bucket_ids)}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            return False
    
    def create_bucket_profile(self) -> Optional[str]:
        """Create a new bucket profile and return its ID."""
        try:
            profile = self.bucket_generator.generate_profile()
            profile_id = profile["profile_id"]
            
            # Check for duplicate
            if self.bucket_collection.find_one({"profile_id": profile_id}):
                profile_id = f"{profile_id}_{random.randint(1000, 9999)}"
                profile["profile_id"] = profile_id
            
            self.bucket_collection.insert_one(profile)
            self.created_bucket_ids.append(profile_id)
            self.total_buckets_created += 1
            
            logger.info(f"🪣 Created bucket profile: '{profile_id}' (TZ: {profile['timezone']}, schedules: {len(profile['schedule'])})")
            return profile_id
            
        except Exception as e:
            logger.error(f"❌ Failed to create bucket profile: {e}")
            return None
    
    def get_random_bucket_id(self) -> Optional[str]:
        """Get a random existing bucket profile ID, or None."""
        if not self.created_bucket_ids:
            return None
        
        # 70% chance to use a bucket if available
        if random.random() < 0.7:
            return random.choice(self.created_bucket_ids)
        return None
    
    def insert_config(self, kb_config: Dict[str, Any]) -> bool:
        """Insert a KB config into MongoDB."""
        try:
            result = self.kb_collection.insert_one(kb_config)
            
            # Track algorithm usage
            algo_name = kb_config.get("algorithm", {}).get("name", "unknown")
            self.algorithm_usage_counts[algo_name] = self.algorithm_usage_counts.get(algo_name, 0) + 1
            
            bucket_info = f" (bucket: {kb_config['bucket_profile_id']})" if kb_config.get('bucket_profile_id') else ""
            logger.info(f"✅ Created config: '{kb_config['name']}' [algo: {algo_name.upper()}]{bucket_info}")
            self.total_configs_created += 1
            return True
        except Exception as e:
            logger.error(f"❌ Failed to insert config: {e}")
            return False
    
    def generate_and_insert(self) -> bool:
        """Generate and insert a single config, possibly with a new bucket."""
        # Maybe create a new bucket profile first
        if random.random() < self.config.bucket_probability:
            self.create_bucket_profile()
        
        # Get a bucket profile ID (existing or None)
        bucket_id = self.get_random_bucket_id()
        
        # Generate and insert config
        config = self.kb_generator.generate_config(bucket_profile_id=bucket_id)
        return self.insert_config(config)
    
    def generate_burst(self, size: Optional[int] = None) -> int:
        """Generate a burst of configs (and possibly buckets)."""
        if size is None:
            size = random.randint(self.config.burst_size_min, self.config.burst_size_max)
        
        logger.info(f"🔥 BURST MODE: Generating {size} configs...")
        self.total_bursts += 1
        
        # Create 1-2 bucket profiles for this burst
        num_buckets = random.randint(1, 2)
        for _ in range(num_buckets):
            self.create_bucket_profile()
        
        success_count = 0
        for i in range(size):
            if not running:
                break
            
            bucket_id = self.get_random_bucket_id()
            config = self.kb_generator.generate_config(bucket_profile_id=bucket_id)
            
            if self.insert_config(config):
                success_count += 1
            # Small delay between burst inserts
            time.sleep(0.5)
        
        logger.info(f"🔥 BURST COMPLETE: {success_count}/{size} configs created")
        return success_count
    
    def run_continuous(self):
        """Run in continuous mode."""
        logger.info("=" * 60)
        logger.info("🚀 KB Stress Generator - CONTINUOUS MODE")
        logger.info("=" * 60)
        logger.info(f"Source index: {self.config.source_index}")
        logger.info(f"Historical days: {self.config.historical_days} (training data range)")
        logger.info(f"Interval: {self.config.min_interval}-{self.config.max_interval}s")
        logger.info(f"Burst probability: {self.config.burst_probability * 100:.0f}%")
        logger.info(f"Burst size: {self.config.burst_size_min}-{self.config.burst_size_max}")
        logger.info(f"Bucket creation probability: {self.config.bucket_probability * 100:.0f}%")
        logger.info("-" * 60)
        logger.info(f"📚 Available algorithms: {', '.join(self.algorithm_registry.get_algorithm_names())}")
        logger.info("=" * 60)
        
        while running:
            try:
                # Check for burst
                if random.random() < self.config.burst_probability:
                    self.generate_burst()
                else:
                    self.generate_and_insert()
                
                # Random interval before next config
                interval = random.randint(self.config.min_interval, self.config.max_interval)
                logger.info(f"⏳ Next config in {interval}s...")
                
                # Sleep in small chunks to allow graceful shutdown
                for _ in range(interval):
                    if not running:
                        break
                    time.sleep(1)
                    
            except Exception as e:
                logger.error(f"Error in continuous mode: {e}")
                time.sleep(5)
        
        self._print_summary()
    
    def run_burst(self, size: Optional[int] = None):
        """Run a single burst and exit."""
        logger.info("=" * 60)
        logger.info("🔥 KB Stress Generator - BURST MODE")
        logger.info("=" * 60)
        
        self.generate_burst(size)
        self._print_summary()
    
    def run_single(self):
        """Generate a single config and exit."""
        logger.info("=" * 60)
        logger.info("📝 KB Stress Generator - SINGLE MODE")
        logger.info("=" * 60)
        
        self.generate_and_insert()
        self._print_summary()
    
    def _print_summary(self):
        """Print final summary."""
        logger.info("")
        logger.info("=" * 60)
        logger.info("📊 STRESS TEST SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total KB configs created: {self.total_configs_created}")
        logger.info(f"Total bucket profiles created: {self.total_buckets_created}")
        logger.info(f"Total bursts: {self.total_bursts}")
        logger.info(f"Available bucket profiles: {len(self.created_bucket_ids)}")
        logger.info("-" * 60)
        logger.info("📚 Algorithm usage breakdown:")
        for algo_name, count in sorted(self.algorithm_usage_counts.items()):
            pct = (count / self.total_configs_created * 100) if self.total_configs_created > 0 else 0
            logger.info(f"   {algo_name.upper()}: {count} configs ({pct:.1f}%)")
        logger.info("=" * 60)
    
    def run(self):
        """Run the stress generator based on mode."""
        if not self.connect_mongodb():
            logger.error("Cannot proceed without MongoDB connection")
            sys.exit(1)
        
        try:
            if self.config.mode == "continuous":
                self.run_continuous()
            elif self.config.mode == "burst":
                self.run_burst()
            elif self.config.mode == "single":
                self.run_single()
            else:
                logger.error(f"Unknown mode: {self.config.mode}")
                sys.exit(1)
        finally:
            if self.mongo_client:
                self.mongo_client.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="KB Stress Generator")
    parser.add_argument("--mode", choices=["continuous", "burst", "single"],
                       default=None, help="Run mode")
    parser.add_argument("--min-interval", type=int, default=None,
                       help="Minimum seconds between configs")
    parser.add_argument("--max-interval", type=int, default=None,
                       help="Maximum seconds between configs")
    parser.add_argument("--burst-probability", type=float, default=None,
                       help="Probability of burst (0-1)")
    parser.add_argument("--burst-size", type=int, default=None,
                       help="Size for single burst (burst mode only)")
    parser.add_argument("--bucket-probability", type=float, default=None,
                       help="Probability of creating bucket profiles (0-1)")
    parser.add_argument("--seed", type=int, default=None,
                       help="Random seed for reproducibility")
    
    args = parser.parse_args()
    
    # Load config from environment, override with CLI args
    config = StressGeneratorConfig.from_env()
    
    if args.mode:
        config.mode = args.mode
    if args.min_interval:
        config.min_interval = args.min_interval
    if args.max_interval:
        config.max_interval = args.max_interval
    if args.burst_probability is not None:
        config.burst_probability = args.burst_probability
    if args.bucket_probability is not None:
        config.bucket_probability = args.bucket_probability
    if args.seed:
        config.seed = args.seed
    
    # Run generator
    generator = StressGenerator(config)
    
    # Handle burst size for burst mode
    if config.mode == "burst" and args.burst_size:
        generator.connect_mongodb()
        generator.run_burst(args.burst_size)
    else:
        generator.run()


if __name__ == "__main__":
    main()
