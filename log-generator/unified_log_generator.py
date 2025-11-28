#!/usr/bin/env python3
"""
Unified Log Generator for Anomaly Detection Framework.

This script:
1. FIRST: Generates 1 year of historical data (backfill)
2. THEN: Switches to continuous real-time log generation

Both phases use the SAME index for seamless detection.
"""
import os
import sys
import time
import json
import random
import signal
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from elasticsearch import Elasticsearch, helpers
from faker import Faker

# =============================================================================
# CONFIGURATION
# =============================================================================
ES_HOST = os.getenv("ES_HOST", "http://elasticsearch-dataset:9200")
INDEX_NAME = os.getenv("INDEX_NAME", "app-logs")  # Single unified index

# Historical data settings
HISTORICAL_DAYS = int(os.getenv("HISTORICAL_DAYS", "365"))  # 1 year of history
HISTORICAL_BATCH_SIZE = int(os.getenv("HISTORICAL_BATCH_SIZE", "5000"))
HISTORICAL_ANOMALY_RATE = float(os.getenv("HISTORICAL_ANOMALY_RATE", "0.02"))  # 2%

# Continuous generation settings  
CONTINUOUS_INTERVAL = float(os.getenv("CONTINUOUS_INTERVAL", "1.0"))  # seconds
LOGS_PER_INTERVAL_MIN = int(os.getenv("LOGS_PER_INTERVAL_MIN", "15"))
LOGS_PER_INTERVAL_MAX = int(os.getenv("LOGS_PER_INTERVAL_MAX", "30"))
CONTINUOUS_ANOMALY_RATE = float(os.getenv("CONTINUOUS_ANOMALY_RATE", "0.02"))

# Traffic burst settings
BURST_PROBABILITY = float(os.getenv("BURST_PROBABILITY", "0.05"))  # 5% chance per interval
BURST_SIZE_MIN = int(os.getenv("BURST_SIZE_MIN", "50"))
BURST_SIZE_MAX = int(os.getenv("BURST_SIZE_MAX", "200"))

# =============================================================================
# LOGGING SETUP
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# =============================================================================
# DATA GENERATION
# =============================================================================
fake = Faker()

HTTP_METHODS = ["GET"] * 70 + ["POST"] * 20 + ["PUT"] * 5 + ["DELETE"] * 3 + ["PATCH"] * 2
STATUS_CODES_NORMAL = [200] * 85 + [201] * 5 + [301] * 2 + [302] * 2 + [400] * 2 + [401] * 1 + [403] * 1 + [404] * 5
STATUS_CODES_ANOMALY = [500, 502, 503, 504, 500, 500, 503]

ENDPOINTS = [
    "/api/v1/users", "/api/v1/users/{id}", "/api/v1/users/{id}/profile",
    "/api/v1/products", "/api/v1/products/{id}", "/api/v1/products/search",
    "/api/v1/orders", "/api/v1/orders/{id}", "/api/v1/orders/{id}/status",
    "/api/v1/cart", "/api/v1/cart/items", "/api/v1/checkout",
    "/api/v1/auth/login", "/api/v1/auth/logout", "/api/v1/auth/refresh",
    "/api/v1/search", "/api/v1/recommendations", "/api/v1/notifications",
    "/health", "/metrics", "/api/v1/webhooks",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 Safari/17.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120.0.0.0",
    "python-requests/2.31.0",
    "axios/1.6.0",
    "PostmanRuntime/7.35.0",
]


def get_time_factor(hour: int, is_weekday: bool) -> float:
    """Get traffic multiplier based on time of day and day type."""
    if not is_weekday:
        # Weekend: lower traffic
        if 0 <= hour < 8:
            return 0.2
        elif 8 <= hour < 12:
            return 0.5
        elif 12 <= hour < 20:
            return 0.7
        else:
            return 0.3
    else:
        # Weekday: business hours pattern
        if 0 <= hour < 6:
            return 0.1  # Night
        elif 6 <= hour < 9:
            return 0.5  # Morning ramp-up
        elif 9 <= hour < 12:
            return 1.0  # Business hours
        elif 12 <= hour < 14:
            return 0.8  # Lunch dip
        elif 14 <= hour < 18:
            return 1.0  # Afternoon peak
        elif 18 <= hour < 21:
            return 0.6  # Evening wind-down
        else:
            return 0.2  # Night


def generate_log_entry(timestamp: datetime, is_anomaly: bool = False) -> dict:
    """Generate a single log entry."""
    method = random.choice(HTTP_METHODS)
    endpoint = random.choice(ENDPOINTS).replace("{id}", str(random.randint(1, 10000)))
    
    if is_anomaly:
        status_code = random.choice(STATUS_CODES_ANOMALY)
        response_time = random.randint(3000, 30000)  # Slow response
        bytes_sent = random.randint(0, 500)  # Small or error response
    else:
        status_code = random.choice(STATUS_CODES_NORMAL)
        if status_code >= 400:
            response_time = random.randint(50, 500)
            bytes_sent = random.randint(100, 2000)
        else:
            response_time = random.randint(10, 500)
            bytes_sent = random.randint(500, 100000)
    
    return {
        "@timestamp": timestamp.isoformat().replace("+00:00", "Z") if timestamp.tzinfo else timestamp.isoformat() + "Z",
        "method": method,
        "endpoint": endpoint,
        "status_code": status_code,
        "response_time_ms": response_time,
        "bytes_sent": bytes_sent,
        "client_ip": fake.ipv4_public(),
        "user_agent": random.choice(USER_AGENTS),
        "request_id": fake.uuid4(),
        "user_id": f"user_{random.randint(1, 10000)}",
        "session_id": fake.uuid4()[:8],
        "geo": {
            "country": fake.country_code(),
            "city": fake.city(),
        },
        "is_anomaly_marker": is_anomaly,  # For validation, not used in detection
    }


# =============================================================================
# ELASTICSEARCH OPERATIONS
# =============================================================================
class ElasticsearchManager:
    def __init__(self, host: str, index_name: str):
        self.host = host
        self.index_name = index_name
        self.es: Optional[Elasticsearch] = None
        
    def connect(self, max_retries: int = 30, retry_delay: int = 5) -> bool:
        """Connect to Elasticsearch with retries."""
        for attempt in range(max_retries):
            try:
                self.es = Elasticsearch([self.host])
                # Use info() instead of ping() for compatibility with ES 8.x client
                info = self.es.info()
                logger.info(f"Connected to Elasticsearch at {self.host} (version: {info['version']['number']})")
                return True
            except Exception as e:
                logger.warning(f"Connection attempt {attempt + 1}/{max_retries} failed: {e}")
            time.sleep(retry_delay)
        
        logger.error("Failed to connect to Elasticsearch")
        return False
    
    def create_index(self) -> bool:
        """Create the index with proper mappings."""
        mapping = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "refresh_interval": "5s"
            },
            "mappings": {
                "properties": {
                    "@timestamp": {"type": "date"},
                    "method": {"type": "keyword"},
                    "endpoint": {"type": "keyword"},
                    "status_code": {"type": "integer"},
                    "response_time_ms": {"type": "integer"},
                    "bytes_sent": {"type": "long"},
                    "client_ip": {"type": "ip"},
                    "user_agent": {"type": "text"},
                    "request_id": {"type": "keyword"},
                    "user_id": {"type": "keyword"},
                    "session_id": {"type": "keyword"},
                    "geo": {
                        "properties": {
                            "country": {"type": "keyword"},
                            "city": {"type": "keyword"}
                        }
                    },
                    "is_anomaly_marker": {"type": "boolean"}
                }
            }
        }
        
        try:
            if self.es.indices.exists(index=self.index_name):
                logger.info(f"Index {self.index_name} already exists, deleting...")
                self.es.indices.delete(index=self.index_name)
            
            self.es.indices.create(index=self.index_name, body=mapping)
            logger.info(f"Created index: {self.index_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to create index: {e}")
            return False
    
    def bulk_index(self, documents: list) -> int:
        """Bulk index documents. Returns count of successfully indexed."""
        if not documents:
            return 0
        
        actions = [
            {"_index": self.index_name, "_source": doc}
            for doc in documents
        ]
        
        try:
            success, failed = helpers.bulk(self.es, actions, raise_on_error=False)
            if failed:
                logger.warning(f"Bulk indexing: {success} succeeded, {len(failed)} failed")
            return success
        except Exception as e:
            logger.error(f"Bulk indexing failed: {e}")
            return 0
    
    def refresh(self):
        """Refresh the index."""
        try:
            self.es.indices.refresh(index=self.index_name)
        except Exception as e:
            logger.warning(f"Refresh failed: {e}")
    
    def get_count(self) -> int:
        """Get document count in index."""
        try:
            return self.es.count(index=self.index_name)["count"]
        except:
            return 0


# =============================================================================
# PHASE 1: HISTORICAL DATA GENERATION
# =============================================================================
def generate_historical_data(es_manager: ElasticsearchManager, days: int = 365) -> int:
    """Generate historical data for the past N days."""
    logger.info(f"=" * 60)
    logger.info(f"PHASE 1: Generating {days} days of historical data")
    logger.info(f"=" * 60)
    
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    logger.info(f"Date range: {start_date.date()} to {end_date.date()}")
    logger.info(f"Index: {es_manager.index_name}")
    
    total_docs = 0
    total_anomalies = 0
    batch = []
    
    current_date = start_date
    day_count = 0
    
    while current_date < end_date:
        day_count += 1
        is_weekday = current_date.weekday() < 5
        
        # Generate logs for each hour
        for hour in range(24):
            time_factor = get_time_factor(hour, is_weekday)
            base_logs = int(100 * time_factor)  # Base logs per hour
            num_logs = random.randint(int(base_logs * 0.8), int(base_logs * 1.2))
            
            for _ in range(num_logs):
                # Random minute and second within the hour
                minute = random.randint(0, 59)
                second = random.randint(0, 59)
                microsecond = random.randint(0, 999999)
                
                timestamp = current_date.replace(
                    hour=hour, minute=minute, second=second, microsecond=microsecond
                )
                
                is_anomaly = random.random() < HISTORICAL_ANOMALY_RATE
                if is_anomaly:
                    total_anomalies += 1
                
                batch.append(generate_log_entry(timestamp, is_anomaly))
                
                # Bulk index when batch is full
                if len(batch) >= HISTORICAL_BATCH_SIZE:
                    indexed = es_manager.bulk_index(batch)
                    total_docs += indexed
                    batch = []
                    
                    if total_docs % 50000 == 0:
                        logger.info(f"Progress: {total_docs:,} documents, Day {day_count}/{days}")
        
        current_date += timedelta(days=1)
    
    # Index remaining batch
    if batch:
        indexed = es_manager.bulk_index(batch)
        total_docs += indexed
    
    es_manager.refresh()
    
    logger.info(f"=" * 60)
    logger.info(f"Historical data generation complete!")
    logger.info(f"Total documents: {total_docs:,}")
    logger.info(f"Total anomalies: {total_anomalies:,} ({100*total_anomalies/max(1,total_docs):.2f}%)")
    logger.info(f"=" * 60)
    
    return total_docs


# =============================================================================
# PHASE 2: CONTINUOUS LOG GENERATION
# =============================================================================
class ContinuousGenerator:
    def __init__(self, es_manager: ElasticsearchManager):
        self.es_manager = es_manager
        self.running = True
        self.total_logs = 0
        self.total_anomalies = 0
        self.start_time = None
        
        # Register signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        logger.info("Shutdown signal received, stopping...")
        self.running = False
    
    def run(self):
        """Run continuous log generation."""
        logger.info(f"=" * 60)
        logger.info(f"PHASE 2: Starting continuous log generation")
        logger.info(f"=" * 60)
        logger.info(f"Interval: {CONTINUOUS_INTERVAL}s")
        logger.info(f"Logs per interval: {LOGS_PER_INTERVAL_MIN}-{LOGS_PER_INTERVAL_MAX}")
        logger.info(f"Anomaly rate: {CONTINUOUS_ANOMALY_RATE*100:.1f}%")
        
        self.start_time = time.time()
        last_stats_time = time.time()
        
        while self.running:
            try:
                now = datetime.now(timezone.utc)
                batch = []
                
                # Determine number of logs this interval
                num_logs = random.randint(LOGS_PER_INTERVAL_MIN, LOGS_PER_INTERVAL_MAX)
                
                # Check for traffic burst
                if random.random() < BURST_PROBABILITY:
                    burst_size = random.randint(BURST_SIZE_MIN, BURST_SIZE_MAX)
                    logger.info(f"Generating traffic burst: {burst_size} extra logs")
                    num_logs += burst_size
                
                # Generate logs
                for _ in range(num_logs):
                    # Slight timestamp variation within the interval
                    ts_offset = random.uniform(0, CONTINUOUS_INTERVAL)
                    timestamp = now - timedelta(seconds=ts_offset)
                    
                    is_anomaly = random.random() < CONTINUOUS_ANOMALY_RATE
                    if is_anomaly:
                        self.total_anomalies += 1
                    
                    batch.append(generate_log_entry(timestamp, is_anomaly))
                
                # Index batch
                indexed = self.es_manager.bulk_index(batch)
                self.total_logs += indexed
                
                # Print stats every 60 seconds
                if time.time() - last_stats_time >= 60:
                    self._print_stats()
                    last_stats_time = time.time()
                
                # Wait for next interval
                time.sleep(CONTINUOUS_INTERVAL)
                
            except Exception as e:
                logger.error(f"Error in continuous generation: {e}")
                time.sleep(5)
        
        self._print_stats()
        logger.info("Continuous generation stopped")
    
    def _print_stats(self):
        elapsed = time.time() - self.start_time
        rate = self.total_logs / elapsed if elapsed > 0 else 0
        anomaly_pct = 100 * self.total_anomalies / max(1, self.total_logs)
        
        logger.info(
            f"Stats: {self.total_logs:,} logs generated, "
            f"{self.total_anomalies:,} anomalies ({anomaly_pct:.2f}%), "
            f"Rate: {rate:.1f} logs/sec"
        )


# =============================================================================
# MAIN
# =============================================================================
def main():
    logger.info("=" * 60)
    logger.info("UNIFIED LOG GENERATOR FOR ANOMALY DETECTION")
    logger.info("=" * 60)
    logger.info(f"Elasticsearch: {ES_HOST}")
    logger.info(f"Index: {INDEX_NAME}")
    logger.info(f"Historical days: {HISTORICAL_DAYS}")
    
    # Connect to Elasticsearch
    es_manager = ElasticsearchManager(ES_HOST, INDEX_NAME)
    if not es_manager.connect():
        logger.error("Failed to connect to Elasticsearch, exiting")
        sys.exit(1)
    
    # Create index
    if not es_manager.create_index():
        logger.error("Failed to create index, exiting")
        sys.exit(1)
    
    # Phase 1: Generate historical data
    generate_historical_data(es_manager, HISTORICAL_DAYS)
    
    # Phase 2: Start continuous generation
    generator = ContinuousGenerator(es_manager)
    generator.run()


if __name__ == "__main__":
    main()
