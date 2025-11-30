# KB Stress Generator

A stress testing tool that periodically creates KB anomaly detection configurations and bucket profiles to stress test the anomaly detection framework stack.

## Features

- **Continuous Mode**: Creates configs at random intervals
- **Burst Mode**: Occasionally spams multiple configs at once
- **Bucket Profile Creation**: Automatically creates time-context bucket profiles
- **Randomized Configs**: Generates varied configurations with different:
  - Query types (status codes, latency metrics, error rates, unique users)
  - Detection frequencies (1-15 minute intervals)
  - Algorithm dimensions
  - Training periods
  - Bucket profile assignments
- **Stack Integration**: Directly inserts into MongoDB, triggering the ETL pipeline
- **Uses `app-logs` Index**: All queries target the dynamically generated app-logs data

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGODB_URI` | `mongodb://admin:1q2w3E%2A@mongodb:27017/?authSource=admin&replicaSet=rs0` | MongoDB connection string |
| `MONGODB_DB` | `anomaly_detection` | Database name |
| `MONGODB_COLLECTION` | `kb_configs` | Collection for KB configs |
| `BUCKET_COLLECTION` | `bucket_profiles` | Collection for bucket profiles |
| `ES_URL` | `http://elasticsearch-dataset:9200` | Elasticsearch URL for query validation |
| `MODE` | `continuous` | Run mode: `continuous`, `burst`, or `single` |
| `MIN_INTERVAL` | `30` | Minimum seconds between config creations |
| `MAX_INTERVAL` | `120` | Maximum seconds between config creations |
| `BURST_PROBABILITY` | `0.1` | Probability of a burst (0-1) |
| `BURST_SIZE_MIN` | `3` | Minimum configs in a burst |
| `BURST_SIZE_MAX` | `10` | Maximum configs in a burst |
| `BUCKET_PROBABILITY` | `0.3` | Probability of assigning a bucket profile (0-1) |
| `SEED` | None | Random seed for reproducibility |

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

## Validated SQL Queries

All queries have been validated against the `app-logs` index:

1. **Status Code Metrics**: Counts of 200s, 5xx errors, total requests
2. **Latency Metrics**: Average and max response times
3. **Error & Bandwidth**: Error counts and bytes sent
4. **Unique Counts**: Unique endpoints and users

## Bucket Profiles

The generator creates bucket profiles with:
- Random timezone selection
- Workday/weekend schedules
- Optional business hours ranges
- Hourly or daily granularity

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
docker exec mongodb mongosh -u admin -p '1q2w3E*' --eval "use anomaly_detection; db.kb_configs.find().count()"
```

Check bucket profiles:
```bash
docker exec mongodb mongosh -u admin -p '1q2w3E*' --eval "use anomaly_detection; db.bucket_profiles.find()"
```
