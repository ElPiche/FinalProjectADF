# Log Generator - Smart E-Commerce Simulation

This directory contains intelligent log generators for testing the Anomaly Detection Framework, featuring a **realistic e-commerce website simulation**.

## 🛒 Smart E-Commerce Generator (NEW)

The main generator (`ecommerce_log_generator.py`) simulates a complete online store with:

### Realistic Business Model
- **36 products** across 5 categories (Electronics, Clothing, Home & Garden, Beauty, Sports)
- **User sessions** with shopping intent (browse, search, add-to-cart, checkout)
- **Device distribution** (55% mobile, 40% desktop, 5% bots)
- **Geographic distribution** weighted by e-commerce activity (US, UK, DE, FR, etc.)

### Intelligent Traffic Patterns
- **Time-of-day patterns**: Peak during lunch breaks and evenings
- **Weekly patterns**: Different weekday vs weekend behavior  
- **Seasonal patterns**: November/December peak shopping season
- **Special events**: Black Friday (8x traffic), Cyber Monday, Summer Sales

### High-Volume Data Generation
- **Base rate**: 5,000 requests/hour (vs old 60/hour = **83x more data!**)
- **Peak hours**: Up to 20,000 requests/hour during sales events
- **1 year of data**: ~45-60 million documents

### Realistic Anomaly Patterns
- **Database outages**: Every 2nd month, 15th day, 2-4 AM
- **Deployment issues**: Wednesday evenings
- **Payment failures**: Occasional payment gateway problems
- **Traffic spikes**: Random viral moments

---

## Files

| File | Description |
|------|-------------|
| `ecommerce_log_generator.py` | **Main** - Smart e-commerce simulation (writes to `ecommerce-logs`) |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Container build configuration |

---

## Quick Start

### Docker (Recommended)

```bash
# Build and run e-commerce generator
docker-compose up log-generator

# Or run directly
docker build -t ecommerce-log-gen .
docker run -e ES_HOST=http://elasticsearch:9200 ecommerce-log-gen
```

### Local Development

```bash
pip install -r requirements.txt
python ecommerce_log_generator.py
```

---

## Environment Variables

### Core Settings
| Variable | Default | Description |
|----------|---------|-------------|
| `ES_HOST` | `http://elasticsearch-dataset:9200` | Elasticsearch URL |
| `INDEX_NAME` | `ecommerce-logs` | Target index name |
| `HISTORICAL_DAYS` | `365` | Days of historical data to generate |

### Volume Settings
| Variable | Default | Description |
|----------|---------|-------------|
| `BASE_REQUESTS_PER_HOUR` | `5000` | Base traffic volume per hour |
| `PEAK_MULTIPLIER` | `4.0` | Multiplier for peak hours |
| `HISTORICAL_BATCH_SIZE` | `10000` | Bulk indexing batch size |

### Anomaly Settings
| Variable | Default | Description |
|----------|---------|-------------|
| `HISTORICAL_ANOMALY_RATE` | `0.015` | 1.5% anomaly rate in historical data |
| `CONTINUOUS_ANOMALY_RATE` | `0.02` | 2% anomaly rate in real-time data |

### Continuous Generation
| Variable | Default | Description |
|----------|---------|-------------|
| `CONTINUOUS_INTERVAL` | `1.0` | Seconds between batches |
| `LOGS_PER_INTERVAL_MIN` | `50` | Min logs per interval |
| `LOGS_PER_INTERVAL_MAX` | `150` | Max logs per interval |
| `BURST_PROBABILITY` | `0.03` | 3% chance of traffic burst |
| `BURST_SIZE_MIN` | `200` | Min burst size |
| `BURST_SIZE_MAX` | `1000` | Max burst size |

---

## Index Schema

The `ecommerce-logs` index includes rich e-commerce data:

```json
{
  "@timestamp": "2024-11-29T12:30:45.123Z",
  
  "method": "POST",
  "endpoint": "/api/v1/cart/items",
  "endpoint_name": "cart_add",
  "status_code": 200,
  "response_time_ms": 145,
  "bytes_sent": 1250,
  
  "session_id": "a1b2c3d4e5f6",
  "user_id": "user_12345",
  "is_authenticated": true,
  
  "device_type": "mobile",
  "client_ip": "203.0.113.45",
  "user_agent": "Mozilla/5.0 (iPhone; ...",
  
  "geo": {
    "country": "US",
    "city": "New York"
  },
  
  "category": "electronics",
  "product_id": "ELEC001",
  "product_name": "Wireless Headphones Pro",
  "product_price": 149.99,
  
  "search_query": "headphones",
  "search_results_count": 42,
  
  "payment_method": "credit_card",
  "order_total": 299.98,
  "items_count": 2,
  
  "is_anomaly_marker": false,
  "anomaly_type": null
}
```

---

## Products Catalog

### Electronics (30% of traffic)
- Wireless Headphones Pro ($149.99)
- Smart Watch Series X ($299.99)
- Bluetooth Speaker Mini ($49.99)
- USB-C Hub 7-in-1 ($39.99)
- Mechanical Keyboard RGB ($119.99)
- And more...

### Clothing (25% of traffic)
- Premium Cotton T-Shirt ($29.99)
- Slim Fit Jeans ($59.99)
- Winter Jacket Waterproof ($129.99)
- Running Shoes Comfort ($89.99)
- And more...

### Home & Garden (20% of traffic)
- Smart LED Bulb Pack ($34.99)
- Robot Vacuum Cleaner ($299.99)
- Air Purifier HEPA ($179.99)
- And more...

### Beauty (15% of traffic)
- Vitamin C Serum ($29.99)
- Hair Dryer Professional ($79.99)
- And more...

### Sports (10% of traffic)
- Yoga Mat Premium ($34.99)
- Fitness Tracker Band ($49.99)
- And more...

---

## Sample ES SQL Queries

### Traffic by Category
```sql
SELECT category, COUNT(*) as requests
FROM "ecommerce-logs"
WHERE category IS NOT NULL
GROUP BY category
ORDER BY requests DESC
```

### Hourly Error Rate (Anomaly Detection Ready)
```sql
SELECT 
  DATE_TRUNC('hour', "@timestamp") AS bucket,
  SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END) AS error_count,
  COUNT(*) AS total_requests
FROM "ecommerce-logs"
WHERE "@timestamp" >= '$from' AND "@timestamp" < '$to'
GROUP BY 1
ORDER BY 1
```

### Checkout Conversion Funnel
```sql
SELECT endpoint_name, COUNT(*) as count
FROM "ecommerce-logs"
WHERE endpoint_name IN ('cart_view', 'cart_add', 'checkout_init', 'checkout_payment', 'order_confirm')
  AND status_code < 400
GROUP BY endpoint_name
```

### Device Type Distribution
```sql
SELECT device_type, COUNT(*) as requests
FROM "ecommerce-logs"
GROUP BY device_type
```

### Top Products by Views
```sql
SELECT product_id, product_name, COUNT(*) as views
FROM "ecommerce-logs"
WHERE product_id IS NOT NULL
GROUP BY product_id, product_name
ORDER BY views DESC
LIMIT 10
```

---

## Traffic Patterns Explained

### Daily Pattern (Weekday)
```
Hour    Multiplier    Description
0-6     0.15x         Night (minimal traffic)
6-9     0.50x         Morning ramp-up
9-12    1.00x         Late morning
12-14   1.30x         LUNCH BREAK SHOPPING!
14-17   0.90x         Afternoon
17-21   1.50x         EVENING PEAK (after work)
21-24   0.40x         Late night
```

### Weekly Pattern
- **Weekdays**: Full traffic with business hour patterns
- **Weekends**: 85% of weekday traffic, different hourly distribution

### Seasonal Pattern
- **Jan-Feb**: 85-90% (post-holiday slump)
- **Mar-Aug**: 90-100% (normal)
- **Sep-Oct**: 110-120% (pre-holiday buildup)
- **Nov-Dec**: 150-180% (PEAK HOLIDAY SEASON)

### Special Events
| Event | Date | Traffic Multiplier |
|-------|------|-------------------|
| Black Friday | Nov 27-30 | **8x** |
| Cyber Monday | Dec 2 | **6x** |
| Christmas Rush | Dec 15-23 | **3x** |
| New Year Sale | Jan 1-5 | **2x** |
| Valentine's | Feb 10-14 | **1.8x** |
| Summer Sale | Jul 12-15 | **4x** |

---

## Anomaly Types

### Scheduled Anomalies
| Type | When | Error Rate |
|------|------|------------|
| Database Outage | 15th of even months, 2-4 AM | 80% |
| Deployment Issues | Wednesdays, 6-8 PM | 40% |

### Random Anomalies
| Type | Probability | Effect |
|------|-------------|--------|
| Payment Gateway Failure | 0.8% | 60% errors on checkout |
| Traffic Spike Timeout | 0.2% | 5x latency |
| Random Errors | 1.5% baseline | 500 errors |

---

## Integration with Anomaly Detection

Create a KB configuration to detect e-commerce anomalies:

```json
{
  "name": "ecommerce-error-rate",
  "description": "Detect elevated error rates on e-commerce platform",
  "source_index": "ecommerce-logs",
  "elasticsearch_sql_query": "SELECT DATE_TRUNC('hour', \"@timestamp\") AS bucket, SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END) AS error_count, COUNT(*) AS total FROM \"ecommerce-logs\" WHERE \"@timestamp\" >= '$from' AND \"@timestamp\" < '$to' GROUP BY 1",
  "query_mode": {"type": "aggregated", "timestamp_field": "bucket"},
  "algorithm": {
    "name": "zscore",
    "parameters": [{"dimension": "error_count", "is_active": true}]
  }
}
```

---

## Graceful Shutdown

The generator handles `SIGINT` and `SIGTERM` gracefully:
```bash
docker stop log-generator
# Logs: "Shutdown signal received, stopping..."
# Logs final stats before exit
```
