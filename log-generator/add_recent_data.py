#!/usr/bin/env python3
"""
Add recent data to historical-logs for detection testing.
Generates last 2 hours of data so detection can find anomalies.
"""
import json
import random
from datetime import datetime, timedelta
from elasticsearch import Elasticsearch, helpers
from faker import Faker

# Configuration
ES_HOST = "http://localhost:9200"
INDEX_NAME = "historical-logs"

# Generate last 2 hours of data
END_DATE = datetime.utcnow()
START_DATE = END_DATE - timedelta(hours=2)
BULK_SIZE = 100

# Initialize
fake = Faker()
es = Elasticsearch([ES_HOST])

# Same selections as the historical generator
HTTP_METHODS = ["GET"] * 70 + ["POST"] * 20 + ["PUT"] * 5 + ["DELETE"] * 3 + ["PATCH"] * 2
STATUS_CODES = [200] * 85 + [201] * 5 + [301] * 2 + [302] * 2 + [400] * 2 + [401] * 1 + [403] * 1 + [404] * 5 + [500] * 2 + [502] * 1 + [503] * 2
ENDPOINTS = [
    "/api/v1/users", "/api/v1/products", "/api/v1/orders", "/api/v1/search",
    "/api/v1/auth/login", "/api/v1/auth/logout", "/api/v1/cart", "/api/v1/checkout",
]
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X) Safari/17.0",
    "python-requests/2.31.0",
]


def generate_log_entry(timestamp: datetime, is_anomaly: bool = False) -> dict:
    """Generate a single log entry."""
    method = random.choice(HTTP_METHODS)
    endpoint = random.choice(ENDPOINTS)
    
    if is_anomaly:
        status_code = random.choice([500, 502, 503, 504, 500, 500, 503])
        response_time = random.randint(5000, 30000)
        bytes_sent = random.randint(0, 500)
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
        "data_type": "recent",
    }


def main():
    print(f"Adding recent data to {INDEX_NAME}")
    print(f"Time range: {START_DATE} to {END_DATE}")
    
    entries = []
    current = START_DATE
    
    while current < END_DATE:
        # Generate ~90 entries per hour (business hours pattern)
        num_entries = random.randint(60, 120)
        for _ in range(num_entries):
            minute = random.randint(0, 59)
            second = random.randint(0, 59)
            timestamp = current.replace(minute=minute, second=second, microsecond=0)
            
            # 5% chance of anomaly
            is_anomaly = random.random() < 0.05
            entries.append(generate_log_entry(timestamp, is_anomaly))
        
        current += timedelta(hours=1)
    
    # Bulk index
    actions = [{"_index": INDEX_NAME, "_source": doc} for doc in entries]
    helpers.bulk(es, actions)
    es.indices.refresh(index=INDEX_NAME)
    
    print(f"Added {len(entries)} documents")
    
    # Verify
    result = es.count(index=INDEX_NAME)
    print(f"Total documents in index: {result['count']}")


if __name__ == "__main__":
    main()
