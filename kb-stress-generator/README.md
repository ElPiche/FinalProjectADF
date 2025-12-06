# KB Stress Generator

A stress testing tool that periodically creates KB anomaly detection configurations and bucket profiles to stress test the anomaly detection framework stack.

## Features

- **Dynamic Algorithm Discovery**: Reads available algorithms from shared Docker volume
- **Continuous Mode**: Creates configs at random intervals
- **Burst Mode**: Occasionally spams multiple configs at once
- **Bucket Profile Creation**: Automatically creates time-context bucket profiles
- **Randomized Configs**: Generates varied configurations with different:
  - **Algorithms**: Randomly selects from zscore, iqr, mock (or any registered algorithm)
  - Query types (status codes, latency metrics, error rates, unique users)
  - Detection frequencies (sub-minute to 5 minute intervals)
  - Algorithm-specific parameters (percentile for zscore, multiplier for IQR)
  - Training periods
  - Bucket profile assignments
- **Stack Integration**: Directly inserts into MongoDB, triggering the ETL pipeline
- **Algorithm Usage Tracking**: Reports breakdown of algorithm usage in summary

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGODB_URI` | `mongodb://admin:1q2w3E%2A@mongodb:27017/?authSource=admin&replicaSet=rs0` | MongoDB connection string |
| `MONGODB_DB` | `knowledge_base` | Database name |
| `MONGODB_COLLECTION` | `kb_configs` | Collection for KB configs |
| `BUCKET_COLLECTION` | `bucket_profiles` | Collection for bucket profiles |
| `ES_URL` | `http://elasticsearch-dataset:9200` | Elasticsearch URL for query validation |
| `SOURCE_INDEX` | `ecommerce-logs` | Target index for KB configs |
| `ALGORITHM_REGISTRY_PATH` | `/app/registry/algorithms.json` | Path to algorithm registry (shared volume) |
| `MODE` | `continuous` | Run mode: `continuous`, `burst`, or `single` |
| `MIN_INTERVAL` | `30` | Minimum seconds between config creations |
| `MAX_INTERVAL` | `120` | Maximum seconds between config creations |
| `BURST_PROBABILITY` | `0.1` | Probability of a burst (0-1) |
| `BURST_SIZE_MIN` | `3` | Minimum configs in a burst |
| `BURST_SIZE_MAX` | `10` | Maximum configs in a burst |
| `BUCKET_PROBABILITY` | `0.3` | Probability of creating bucket profiles (0-1) |
| `SEED` | None | Random seed for reproducibility |

## Algorithm Discovery

The stress generator reads available algorithms from a shared Docker volume:

```
algorithm_registry volume
└── algorithms.json
    {
      "zscore": {"name": "zscore", "parameters": ["percentile", "min_points"]},
      "iqr": {"name": "iqr", "parameters": ["multiplier"]},
      "mock": {"name": "mock", "parameters": ["percentile"]}
    }
```

This file is written by the DA-Dispatcher container on startup. When new algorithms are added to the dispatcher, they automatically become available to the stress generator.

## Usage

### With Docker Compose (Profile-based)

The generator uses a profile and won't start by default:

```bash
# Start with stress profile
docker-compose --profile stress up -d

# Or just the stress generator
docker-compose --profile stress up -d kb-stress-generator
```

### Manual Docker Run

```bash
docker build -t kb-stress-generator .
docker run --network adf-network \
  -v algorithm_registry:/app/registry:ro \
  -e MODE=continuous \
  -e MIN_INTERVAL=10 \
  -e MAX_INTERVAL=30 \
  kb-stress-generator
```

### Direct Python

```bash
pip install -r requirements.txt
python stress_generator.py --mode continuous --min-interval 10 --max-interval 30
```

## Modes

### Continuous (default)
Generates configs at random intervals with occasional bursts:
```bash
python stress_generator.py --mode continuous
```

### Burst
Generates a single burst of configs and exits:
```bash
python stress_generator.py --mode burst --burst-size 5
```

### Single
Generates a single config and exits:
```bash
python stress_generator.py --mode single
```

## Example Output

```
2025-12-02 02:40:29 - INFO - 📚 Loaded 3 algorithms from registry: ['zscore', 'mock', 'iqr']
2025-12-02 02:40:29 - INFO - ============================================================
2025-12-02 02:40:29 - INFO - 🔥 KB Stress Generator - BURST MODE
2025-12-02 02:40:29 - INFO - ============================================================
2025-12-02 02:40:29 - INFO - 🔥 BURST MODE: Generating 10 configs...
2025-12-02 02:40:29 - INFO - ✅ Created config: 'Perf Test - Server Health Scanner #1' [algo: MOCK]
2025-12-02 02:40:30 - INFO - ✅ Created config: 'Load Test - Server Health Detector #2' [algo: ZSCORE]
2025-12-02 02:40:30 - INFO - ✅ Created config: 'Stress Test - User Activity Monitor #3' [algo: IQR]
...
2025-12-02 02:40:34 - INFO - 📊 STRESS TEST SUMMARY
2025-12-02 02:40:34 - INFO - ============================================================
2025-12-02 02:40:34 - INFO - Total KB configs created: 10
2025-12-02 02:40:34 - INFO - ------------------------------------------------------------
2025-12-02 02:40:34 - INFO - 📚 Algorithm usage breakdown:
2025-12-02 02:40:34 - INFO -    IQR: 2 configs (20.0%)
2025-12-02 02:40:34 - INFO -    MOCK: 3 configs (30.0%)
2025-12-02 02:40:34 - INFO -    ZSCORE: 5 configs (50.0%)
```

## Validated SQL Queries

All queries target the `ecommerce-logs` index and include:

1. **Status Code Metrics**: Counts of 200s, 5xx errors, total requests
2. **Latency Metrics**: Average and max response times
3. **Error & Bandwidth**: Error counts and bytes sent
4. **Unique Counts**: Unique endpoints and users
5. **Hourly Traffic**: Request counts with 5xx errors (hourly buckets)

## Bucket Profiles

The generator creates bucket profiles with:
- Random timezone selection
- Workday/weekend schedules
- Optional business hours ranges
- Hourly or block granularity

## Monitoring

Watch the generator logs:
```bash
docker logs -f kb-stress-generator
```

Watch the ETL processing the configs:
```bash
docker logs -f etl-app
```

Check configs in MongoDB:
```bash
docker exec mongodb mongosh -u admin -p '1q2w3E*' --eval "use knowledge_base; db.kb_configs.countDocuments()"
```

Check bucket profiles:
```bash
docker exec mongodb mongosh -u admin -p '1q2w3E*' --eval "use knowledge_base; db.bucket_profiles.find()"
```
