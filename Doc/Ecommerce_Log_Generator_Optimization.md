# E-Commerce Log Generator Optimization Summary

**Date:** December 1, 2025  
**Branch:** feature/big-bucketing-feature

## Overview

Transformed the log generator from a basic bulk indexer to a high-performance streaming pipeline capable of generating **43+ million documents in ~18 minutes** at **~45,000 docs/sec**.

---

## Performance Evolution

| Stage | Approach | Speed | Issues |
|-------|----------|-------|--------|
| Initial | elasticsearch-py bulk | ~14,000 docs/sec | Too slow (77 min ETA) |
| Optimization 1 | Parallel bulk + orjson | ~22-26k docs/sec | Still bottlenecked |
| Optimization 2 | Direct aiohttp bulk API | ~28,500 docs/sec | Better but not streaming |
| Optimization 3 | Chunked transfer streaming | ~30-31k docs/sec | CPU waves (batching) |
| Optimization 4 | Continuous pipeline | ~44k docs/sec peak | Memory explosion |
| Optimization 5 | Backpressure + retry | **~45k docs/sec** | Container restarts |
| **Final** | Memory-safe + 16 streams | **~45k docs/sec stable** | ✅ No issues |

**Final Result:** 43,037,568 documents in 18.4 minutes with 0 errors

---

## Key Technical Changes

### 1. Direct HTTP API (Bypassing elasticsearch-py)

Replaced `elasticsearch-py` library with direct `aiohttp` calls to eliminate client overhead:

```python
async with session.post(
    f"{host}/_bulk",
    data=body_generator(),
    headers={"Content-Type": "application/x-ndjson"},
    timeout=aiohttp.ClientTimeout(total=120),
) as resp:
```

### 2. Chunked Transfer Encoding (Streaming)

Used async generators for true streaming without buffering entire payloads:

```python
async def body_generator():
    action_line = fast_json_dumps({"index": {"_index": index_name}})
    for doc in documents:
        yield action_line + b'\n'
        yield fast_json_dumps(doc) + b'\n'
```

### 3. Continuous Pipeline with asyncio.as_completed

Changed from 7-day batch processing to streaming each day as it completes:

```python
# OLD: Submit all 365 days, wait for 7, stream 7, repeat (waves)
# NEW: Stream each day immediately as its generation completes

for future in asyncio.as_completed(day_futures.keys()):
    day_docs = await future
    # Stream immediately
```

### 4. Memory-Safe Backpressure

Limited concurrent generators AND streams to prevent memory explosion:

```python
max_pending_streams = BULK_THREAD_COUNT  # 16 concurrent bulk streams
max_pending_generators = NUM_WORKERS + 2  # 6 days generating at once

# Only submit new day when room available
while len(pending_generators) >= max_pending_generators:
    await asyncio.wait(...)
```

### 5. Retry Logic with Exponential Backoff

Added retry for transient failures (connection drops, 429 rate limiting):

```python
for attempt in range(max_retries):
    try:
        async with session.post(...) as resp:
            if resp.status == 429:  # Rate limited
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                await asyncio.sleep(wait_time)
                continue
    except (aiohttp.ClientError, asyncio.TimeoutError):
        # Retry with backoff
```

### 6. Performance Libraries

- **orjson**: 10x faster JSON serialization
- **uvloop**: Faster asyncio event loop (Linux)
- **ProcessPoolExecutor**: Parallel CPU-bound document generation

### 7. Elasticsearch Index Optimizations

```python
# Disable refresh during bulk load
"refresh_interval": "-1"

# Async translog for speed
"translog": {"durability": "async", "sync_interval": "30s"}

# Re-enable after historical load
"refresh_interval": "1s"
```

---

## Container Stability Fixes

### Issue 1: Healthcheck Killing Container

**Problem:** Dockerfile had a healthcheck that docker-compose couldn't override with comments.

**Solution:** Explicitly disable in docker-compose:
```yaml
healthcheck:
  disable: true
```

### Issue 2: Memory Explosion (OOM Kill)

**Problem:** Submitting all 365 days to ProcessPoolExecutor at once = 11GB+ memory.

**Solution:** Limited `max_pending_generators = NUM_WORKERS + 2` (6 days max in memory).

### Issue 3: Connection Errors with 32 Streams

**Problem:** 32 concurrent HTTP streams overwhelmed Elasticsearch, causing connection drops.

**Solution:** Reduced to 16 streams with 5000-doc chunks and retry logic.

---

## Continuous Generation Phase

After historical data completes, the generator switches to real-time mode:

```python
async def run_continuous_async(es_manager):
    while True:
        # Generate realistic traffic (50-150 logs/interval)
        num_logs = int(base_logs * get_traffic_multiplier(now))
        
        # Random traffic bursts (3% probability)
        if random.random() < BURST_PROBABILITY:
            num_logs += random.randint(200, 1000)
        
        # Index and sleep
        await stream_bulk_index(...)
        await asyncio.sleep(CONTINUOUS_INTERVAL)
```

**Output:** ~112 logs/sec with periodic bursts, 1.7% anomaly injection rate.

---

## Configuration (docker-compose.yml)

```yaml
log-generator:
  environment:
    - ES_HOST=http://elasticsearch-dataset:9200
    - INDEX_NAME=ecommerce-logs
    - HISTORICAL_DAYS=365
    - BASE_REQUESTS_PER_HOUR=5000
    - PEAK_MULTIPLIER=4.0
    - HISTORICAL_ANOMALY_RATE=0.015
    - CONTINUOUS_INTERVAL=1.0
    - LOGS_PER_INTERVAL_MIN=50
    - LOGS_PER_INTERVAL_MAX=150
    - BURST_PROBABILITY=0.03
    # Performance tuning
    - NUM_WORKERS=4
    - BULK_THREAD_COUNT=16
    - CHUNK_SIZE=5000
  healthcheck:
    disable: true
```

---

## E-Commerce Data Model

### Products (36 across 5 categories)
- Electronics: iPhone, MacBook, AirPods, etc.
- Fashion: Nike Shoes, Levi's Jeans, etc.
- Home: Dyson Vacuum, Instant Pot, etc.
- Sports: Yoga Mat, Dumbbells, etc.
- Beauty: Perfume, Skincare, etc.

### Endpoints (Weighted)
| Endpoint | Weight | Description |
|----------|--------|-------------|
| `/` | 25% | Homepage |
| `/products` | 20% | Product listing |
| `/product/{id}` | 20% | Product detail |
| `/cart` | 15% | Cart operations |
| `/checkout` | 10% | Checkout flow |
| `/api/v1/*` | 10% | API endpoints |

### Traffic Patterns
- **Business hours** (9-17): 2x multiplier
- **Peak hours** (12-14, 19-21): 3x multiplier
- **Night** (0-6): 0.3x multiplier
- **Weekends**: 1.5x base multiplier

### Anomaly Types
- Slow response (>2000ms)
- Error spikes (5xx codes)
- Traffic bursts
- High latency patterns

---

## End-to-End Test Results

Successfully tested the full pipeline:

1. ✅ Generated 43M+ e-commerce logs
2. ✅ Created KB config via KB-MCP
3. ✅ ETL extracted training data (648 hourly points)
4. ✅ Dispatcher trained Z-score model
5. ✅ Detection triggered (5-min CRON)
6. ✅ **2 anomalies detected:**
   - `request_count`: 86,655 (z-score 12.21)
   - `error_5xx_count`: 1,509 (z-score 7.10)
7. ✅ Anomalies stored in `ecommerce-logs_anomalies` index

---

## Files Modified

| File | Changes |
|------|---------|
| `log-generator/ecommerce_log_generator.py` | Complete rewrite with streaming pipeline |
| `log-generator/Dockerfile` | Added healthcheck (later disabled) |
| `log-generator/requirements.txt` | Added orjson, aiohttp, uvloop |
| `docker-compose.yml` | Performance tuning, healthcheck disable |

---

## Usage

```bash
# Start with stress profile
docker-compose --profile stress up -d log-generator

# Monitor progress
docker logs -f log-generator

# Check document count
curl http://localhost:9200/ecommerce-logs/_count
```
