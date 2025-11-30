#!/usr/bin/env python3
"""
Generate 1 year of historical log data for end-to-end testing.
Creates realistic web server logs with patterns suitable for anomaly detection.
"""
import json
import random
import math
from datetime import datetime, timedelta
from elasticsearch import Elasticsearch, helpers
from faker import Faker

# Configuration
ES_HOST = "http://localhost:9200"
INDEX_NAME = "historical-logs"
START_DATE = datetime(2024, 1, 1, 0, 0, 0)  # 1 year ago
END_DATE = datetime(2025, 1, 1, 0, 0, 0)    # Up to now
BULK_SIZE = 1000

# Initialize
fake = Faker()
es = Elasticsearch([ES_HOST])

# Weighted selections (same as continuous generator)
HTTP_METHODS = ["GET"] * 70 + ["POST"] * 20 + ["PUT"] * 5 + ["DELETE"] * 3 + ["PATCH"] * 2
STATUS_CODES = [200] * 85 + [201] * 5 + [301] * 2 + [302] * 2 + [400] * 2 + [401] * 1 + [403] * 1 + [404] * 5 + [500] * 2 + [502] * 1 + [503] * 2
ENDPOINTS = [
    "/api/v1/users", "/api/v1/products", "/api/v1/orders", "/api/v1/search",
    "/api/v1/auth/login", "/api/v1/auth/logout", "/api/v1/cart", "/api/v1/checkout",
    "/api/v1/inventory", "/api/v1/reports", "/api/v1/dashboard", "/api/v1/settings",
    "/api/v1/notifications", "/api/v1/payments", "/api/v1/shipping"
]
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X) Safari/17.0",
    "Mozilla/5.0 (Linux; Android 14) Chrome/120.0.0.0 Mobile",
    "Mozilla/5.0 (iPhone; iOS 17) Safari/604.1",
    "python-requests/2.31.0",
    "curl/8.4.0",
]


def get_traffic_multiplier(dt: datetime) -> float:
    """
    Get traffic multiplier based on time patterns:
    - Workdays (Mon-Fri) have 2x traffic vs weekends
    - Business hours (9am-6pm) have 3x traffic
    - Night hours (midnight-6am) have 0.3x traffic
    """
    hour = dt.hour
    weekday = dt.weekday()  # 0=Monday, 6=Sunday
    
    # Base multiplier
    multiplier = 1.0
    
    # Weekend reduction
    if weekday >= 5:  # Saturday or Sunday
        multiplier *= 0.5
    
    # Time of day pattern
    if 9 <= hour <= 18:  # Business hours
        multiplier *= 3.0
    elif 0 <= hour <= 6:  # Night hours
        multiplier *= 0.3
    elif 6 <= hour <= 9 or 18 <= hour <= 22:  # Transition hours
        multiplier *= 1.5
    
    # Add slight seasonal variation (more traffic in Q4)
    month = dt.month
    if month >= 10:  # October-December
        multiplier *= 1.2
    elif month <= 2:  # January-February
        multiplier *= 0.9
    
    return multiplier


def should_inject_anomaly(dt: datetime) -> bool:
    """
    Inject anomalies at specific dates for testing:
    - Every month on the 15th around noon: traffic spike
    - Random days: error rate spike
    """
    # Specific anomaly dates
    if dt.day == 15 and 11 <= dt.hour <= 14:
        return random.random() < 0.15  # 15% chance of anomaly during spike window
    
    # Random anomalies (2% chance)
    return random.random() < 0.02


def generate_log_entry(timestamp: datetime, is_anomaly: bool = False) -> dict:
    """Generate a single log entry."""
    method = random.choice(HTTP_METHODS)
    endpoint = random.choice(ENDPOINTS)
    
    if is_anomaly:
        # Anomalous entries: high error rates, slow response times
        status_code = random.choice([500, 502, 503, 504, 500, 500, 503])
        response_time = random.randint(5000, 30000)  # 5-30 seconds (very slow)
        bytes_sent = random.randint(0, 500)  # Error responses are small
    else:
        status_code = random.choice(STATUS_CODES)
        if status_code >= 500:
            response_time = random.randint(1000, 5000)
        elif status_code >= 400:
            response_time = random.randint(50, 500)
        else:
            response_time = random.randint(10, 300)
        bytes_sent = random.randint(100, 50000)
    
    return {
        "@timestamp": timestamp.isoformat() + "Z",
        "method": method,
        "endpoint": endpoint,
        "status_code": status_code,
        "response_time_ms": response_time,
        "bytes_sent": bytes_sent,
        "client_ip": fake.ipv4_public(),
        "user_agent": random.choice(USER_AGENTS),
        "request_id": fake.uuid4(),
        "user_id": f"user_{random.randint(1, 10000)}",
        "is_anomaly": is_anomaly,
        "data_type": "historical",
    }


def generate_hour_data(dt: datetime) -> list:
    """Generate data for a single hour."""
    entries = []
    
    # Base rate: 60 requests per hour (1 per minute)
    # Multiply by traffic pattern
    base_rate = 60
    multiplier = get_traffic_multiplier(dt)
    num_entries = int(base_rate * multiplier)
    
    # Generate entries spread throughout the hour
    for _ in range(num_entries):
        # Random minute/second within the hour
        minute = random.randint(0, 59)
        second = random.randint(0, 59)
        timestamp = dt.replace(minute=minute, second=second)
        
        is_anomaly = should_inject_anomaly(timestamp)
        entries.append(generate_log_entry(timestamp, is_anomaly))
    
    return entries


def create_index():
    """Create the index with proper mappings."""
    mapping = {
        "mappings": {
            "properties": {
                "@timestamp": {"type": "date"},
                "method": {"type": "keyword"},
                "endpoint": {"type": "keyword"},
                "status_code": {"type": "integer"},
                "response_time_ms": {"type": "integer"},
                "bytes_sent": {"type": "integer"},
                "client_ip": {"type": "ip"},
                "user_agent": {"type": "text"},
                "request_id": {"type": "keyword"},
                "user_id": {"type": "keyword"},
                "is_anomaly": {"type": "boolean"},
                "data_type": {"type": "keyword"},
            }
        },
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        }
    }
    
    # Delete if exists
    if es.indices.exists(index=INDEX_NAME):
        es.indices.delete(index=INDEX_NAME)
        print(f"Deleted existing index: {INDEX_NAME}")
    
    es.indices.create(index=INDEX_NAME, body=mapping)
    print(f"Created index: {INDEX_NAME}")


def bulk_index(documents: list):
    """Bulk index documents to Elasticsearch."""
    actions = [
        {
            "_index": INDEX_NAME,
            "_source": doc,
        }
        for doc in documents
    ]
    helpers.bulk(es, actions)


def main():
    print("=" * 60)
    print("Historical Log Data Generator")
    print(f"Index: {INDEX_NAME}")
    print(f"Date Range: {START_DATE} to {END_DATE}")
    print("=" * 60)
    
    # Create index
    create_index()
    
    # Generate data hour by hour
    current = START_DATE
    total_docs = 0
    buffer = []
    
    total_hours = int((END_DATE - START_DATE).total_seconds() / 3600)
    hours_processed = 0
    
    while current < END_DATE:
        # Generate data for this hour
        hour_data = generate_hour_data(current)
        buffer.extend(hour_data)
        
        # Bulk index when buffer is large enough
        if len(buffer) >= BULK_SIZE:
            bulk_index(buffer)
            total_docs += len(buffer)
            buffer = []
        
        # Progress reporting
        hours_processed += 1
        if hours_processed % 168 == 0:  # Every week
            progress = (hours_processed / total_hours) * 100
            print(f"Progress: {progress:.1f}% - {hours_processed}/{total_hours} hours - {total_docs} documents indexed")
        
        current += timedelta(hours=1)
    
    # Index remaining documents
    if buffer:
        bulk_index(buffer)
        total_docs += len(buffer)
    
    # Refresh index
    es.indices.refresh(index=INDEX_NAME)
    
    print("=" * 60)
    print(f"COMPLETED: {total_docs} documents indexed to {INDEX_NAME}")
    print("=" * 60)
    
    # Show sample query
    result = es.count(index=INDEX_NAME)
    print(f"Index document count: {result['count']}")
    
    # Show anomaly count
    anomaly_count = es.count(
        index=INDEX_NAME,
        body={"query": {"term": {"is_anomaly": True}}}
    )
    print(f"Anomaly documents: {anomaly_count['count']}")


if __name__ == "__main__":
    main()
