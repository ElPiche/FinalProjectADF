#!/usr/bin/env python3
"""
KB Stress Generator - Stress Test for Anomaly Detection Framework

Periodically creates KB configurations AND bucket profiles to stress test the stack:
- Extractor (ETL pipeline)
- DA-Dispatcher (anomaly detection)
- MongoDB (change streams)
- Elasticsearch (queries)

Features:
- Continuous config generation at random intervals
- Burst mode: occasionally spam multiple configs at once
- Creates bucket profiles with various time-context patterns
- Randomized query patterns, dimensions, and schedules
- Uses ONLY app-logs index (dynamic data from log generator)
- All queries are pre-validated against Elasticsearch SQL
"""

import os
import sys
import time
import random
import signal
import logging
import argparse
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
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


class KBConfigGenerator:
    """Generates randomized KB configurations for stress testing."""
    
    def __init__(self, seed: Optional[int] = None):
        self.fake = Faker()
        if seed is not None:
            random.seed(seed)
            Faker.seed(seed)
        
        self.config_counter = 0
        
        # VALIDATED QUERIES - Only app-logs index (dynamic data)
        # All queries have been validated against Elasticsearch SQL
        self.validated_queries = [
            {
                "name": "status_codes",
                "description": "Monitor HTTP status code distribution",
                "sql": '''SELECT DATE_TRUNC('MINUTE', "@timestamp") AS es_timestamp, SUM(CASE WHEN status_code = 200 THEN 1 ELSE 0 END) AS status_200_count, SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END) AS status_5xx_count, COUNT(*) AS total_requests FROM "app-logs" WHERE "@timestamp" >= '$from' AND "@timestamp" < '$to' GROUP BY es_timestamp ORDER BY es_timestamp''',
                "dimensions": ["status_200_count", "status_5xx_count", "total_requests"],
            },
            {
                "name": "latency_metrics",
                "description": "Monitor API response latency",
                "sql": '''SELECT DATE_TRUNC('MINUTE', "@timestamp") AS es_timestamp, AVG(response_time_ms) AS avg_latency, MAX(response_time_ms) AS max_latency, COUNT(*) AS request_count FROM "app-logs" WHERE "@timestamp" >= '$from' AND "@timestamp" < '$to' GROUP BY es_timestamp ORDER BY es_timestamp''',
                "dimensions": ["avg_latency", "max_latency", "request_count"],
            },
            {
                "name": "error_traffic",
                "description": "Monitor error rates and traffic volume",
                "sql": '''SELECT DATE_TRUNC('MINUTE', "@timestamp") AS es_timestamp, SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS error_count, SUM(bytes_sent) AS total_bytes, COUNT(*) AS total_count FROM "app-logs" WHERE "@timestamp" >= '$from' AND "@timestamp" < '$to' GROUP BY es_timestamp ORDER BY es_timestamp''',
                "dimensions": ["error_count", "total_bytes", "total_count"],
            },
            {
                "name": "user_activity",
                "description": "Monitor unique users and endpoints",
                "sql": '''SELECT DATE_TRUNC('MINUTE', "@timestamp") AS es_timestamp, COUNT(DISTINCT endpoint) AS unique_endpoints, COUNT(DISTINCT user_id) AS unique_users, COUNT(*) AS request_count FROM "app-logs" WHERE "@timestamp" >= '$from' AND "@timestamp" < '$to' GROUP BY es_timestamp ORDER BY es_timestamp''',
                "dimensions": ["unique_endpoints", "unique_users", "request_count"],
            },
            {
                "name": "client_errors",
                "description": "Monitor 4xx client errors",
                "sql": '''SELECT DATE_TRUNC('MINUTE', "@timestamp") AS es_timestamp, SUM(CASE WHEN status_code >= 400 AND status_code < 500 THEN 1 ELSE 0 END) AS client_errors, SUM(CASE WHEN status_code = 404 THEN 1 ELSE 0 END) AS not_found_count, COUNT(*) AS total_requests FROM "app-logs" WHERE "@timestamp" >= '$from' AND "@timestamp" < '$to' GROUP BY es_timestamp ORDER BY es_timestamp''',
                "dimensions": ["client_errors", "not_found_count", "total_requests"],
            },
            {
                "name": "server_health",
                "description": "Monitor server errors and response times",
                "sql": '''SELECT DATE_TRUNC('MINUTE', "@timestamp") AS es_timestamp, SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END) AS server_errors, AVG(response_time_ms) AS avg_response_time, COUNT(*) AS request_count FROM "app-logs" WHERE "@timestamp" >= '$from' AND "@timestamp" < '$to' GROUP BY es_timestamp ORDER BY es_timestamp''',
                "dimensions": ["server_errors", "avg_response_time", "request_count"],
            },
        ]
        
        # Detection frequencies (CRON expressions)
        self.detection_frequencies = [
            "*/1 * * * *",   # Every minute
            "*/2 * * * *",   # Every 2 minutes
            "*/5 * * * *",   # Every 5 minutes
            "*/10 * * * *",  # Every 10 minutes
            "*/15 * * * *",  # Every 15 minutes
        ]
        
        # Detection windows in seconds
        self.detection_windows = [
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
        """Generate a training period based on available data."""
        now = datetime.now(timezone.utc)
        
        # Training should cover recent data (last few hours to 1 day)
        # Since log generator creates continuous data
        training_hours = random.randint(1, 6)  # 1-6 hours of training data
        
        # Training ends a few minutes ago to ensure data exists
        training_end = now - timedelta(minutes=random.randint(5, 30))
        training_start = training_end - timedelta(hours=training_hours)
        
        return (
            training_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            training_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
    
    def _generate_detection_start(self, training_to: str) -> str:
        """Generate detection start time (after training ends)."""
        training_end = datetime.fromisoformat(training_to.replace("Z", "+00:00"))
        # Detection starts 1-5 minutes after training ends
        detection_start = training_end + timedelta(minutes=random.randint(1, 5))
        return detection_start.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    def generate_config(self, bucket_profile_id: Optional[str] = None) -> Dict[str, Any]:
        """Generate a random KB configuration."""
        self.config_counter += 1
        
        # Select random validated query
        query_template = random.choice(self.validated_queries)
        
        # Generate training period
        training_from, training_to = self._generate_training_period()
        detection_start = self._generate_detection_start(training_to)
        
        # Generate config name
        name_template = random.choice(self.name_templates)
        focus = random.choice(self.focus_areas)
        config_name = name_template.format(focus=focus, num=self.config_counter)
        
        # Select dimensions (use 1-3 dimensions)
        available_dims = query_template["dimensions"]
        num_dims = min(len(available_dims), random.randint(1, 3))
        selected_dims = random.sample(available_dims, num_dims)
        
        # Build algorithm parameters
        algorithm_params = []
        for dim in selected_dims:
            param = {
                "dimension": dim,
                "is_active": True,
            }
            # 30% chance to add metadata
            if random.random() < 0.3:
                param["metadata"] = [
                    {"key": "percentile", "value": str(random.choice([95, 97.5, 99, 99.5]))}
                ]
            algorithm_params.append(param)
        
        # Build the KB config document (matching MongoDB schema)
        config = {
            "name": config_name,
            "description": f"Auto-generated stress test: {query_template['description']}. "
                          f"Monitoring {', '.join(selected_dims)}.",
            "change_flag": 0,
            "elasticsearch_sql_query": query_template["sql"],
            "source_index": "app-logs",
            "query_mode": {
                "type": "aggregated",
                "timestamp_field": "es_timestamp",
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
                "name": "zscore",
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
        self.kb_generator = KBConfigGenerator(config.seed)
        self.bucket_generator = BucketProfileGenerator(config.seed)
        self.mongo_client: Optional[MongoClient] = None
        self.db = None
        self.kb_collection = None
        self.bucket_collection = None
        
        self.total_configs_created = 0
        self.total_buckets_created = 0
        self.total_bursts = 0
        self.created_bucket_ids: List[str] = []
        
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
            bucket_info = f" (bucket: {kb_config['bucket_profile_id']})" if kb_config.get('bucket_profile_id') else ""
            logger.info(f"✅ Created config: '{kb_config['name']}'{bucket_info}")
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
        logger.info(f"Index: app-logs (dynamic data)")
        logger.info(f"Interval: {self.config.min_interval}-{self.config.max_interval}s")
        logger.info(f"Burst probability: {self.config.burst_probability * 100:.0f}%")
        logger.info(f"Burst size: {self.config.burst_size_min}-{self.config.burst_size_max}")
        logger.info(f"Bucket creation probability: {self.config.bucket_probability * 100:.0f}%")
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
