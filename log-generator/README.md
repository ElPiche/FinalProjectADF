# Continuous Log Generator

A containerized log generator that continuously produces realistic random logs for testing the Anomaly Detection Framework.

## Features

- **Continuous Operation**: Runs indefinitely, generating logs at configurable rates
- **Realistic Data**: Uses [Faker](https://faker.readthedocs.io/) for realistic fake data
- **Anomaly Injection**: Configurable probability of generating anomalous logs
- **Time-Aware Patterns**: Simulates workday vs weekend traffic patterns
- **Traffic Bursts**: Random traffic spikes for realistic load simulation
- **Multiple Formats**: JSON, Apache Combined Log, or custom format
- **Log Rotation**: Automatic file rotation based on size

## Quick Start

### Run with Docker Compose

The log generator is integrated into the main docker-compose.yml:

```bash
# Start all services including log generator
docker-compose up -d

# Or start only the log generator
docker-compose up -d log-generator

# View logs
docker logs -f log-generator

# Check generated logs
tail -f logs/continuous-logs.log
```

### Run Standalone

```bash
# Build the image
docker build -t log-generator .

# Run with defaults
docker run -v $(pwd)/logs:/var/log/app-logs log-generator

# Run with custom settings
docker run \
  -e LOGS_PER_MINUTE=120 \
  -e ANOMALY_PROBABILITY=0.05 \
  -e LOG_FORMAT=json \
  -v $(pwd)/logs:/var/log/app-logs \
  log-generator
```

### Run Locally (Development)

```bash
# Install dependencies
pip install -r requirements.txt

# Run with defaults
python continuous_log_generator.py

# Run with custom settings
python continuous_log_generator.py \
  --output-dir ./logs \
  --logs-per-minute 60 \
  --anomaly-prob 0.01 \
  --format json
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_OUTPUT_DIR` | `/var/log/app-logs` | Directory for output logs |
| `LOG_FILE_NAME` | `continuous-logs` | Base name for log files |
| `LOGS_PER_MINUTE` | `60` | Target log generation rate |
| `ANOMALY_PROBABILITY` | `0.01` | Probability of anomaly (0-1) |
| `LOG_FORMAT` | `custom` | Format: `json`, `apache`, `custom` |
| `SEED` | (none) | Random seed for reproducibility |
| `BURST_ENABLED` | `true` | Enable random traffic bursts |
| `WORKDAY_PATTERN` | `true` | Enable workday traffic patterns |
| `ROTATE_SIZE_MB` | `10` | Log file rotation size in MB |
| `MAX_FILES` | `5` | Maximum rotated log files |
| `AGGREGATED_MODE` | `false` | Generate aggregated metrics instead |

### Anomaly Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ANOMALY_REQUEST_COUNT_MIN` | `5000` | Min request count for anomalies |
| `ANOMALY_REQUEST_COUNT_MAX` | `10000` | Max request count for anomalies |
| `ANOMALY_ERROR_RATE` | `0.5` | Error rate during anomalies (50%) |
| `ANOMALY_LATENCY_MULTIPLIER` | `10.0` | Latency multiplier for anomalies |

## Log Formats

### JSON Format

```json
{
  "@timestamp": "2025-11-27T18:30:45.123456+00:00",
  "timestamp": "2025-11-27 18:30:45.123",
  "level": "INFO",
  "http_method": "GET",
  "url": "/api/v1/users/12345",
  "status": 200,
  "duration_ms": 45.23,
  "bytes": 2456,
  "client_ip": "192.168.1.100",
  "user_agent": "Mozilla/5.0 ...",
  "session_id": "a1b2c3d4",
  "request_id": "req_123456",
  "user_id": "user_789"
}
```

### Custom Format (Logstash Compatible)

```
2025-11-27 18:30:45.123 -00:00 [INFO] Request finished HTTP/1.1 GET /api/v1/users/12345 - 200 null application/json 45.23ms
```

### Apache Combined Format

```
192.168.1.100 - user_789 [2025-11-27 18:30:45.123] "GET /api/v1/users/12345 HTTP/1.1" 200 2456 "-" "Mozilla/5.0 ..."
```

## Traffic Patterns

### Workday Pattern

When `WORKDAY_PATTERN=true`, traffic varies by hour:

| Hour | Traffic Level |
|------|---------------|
| 0-5  | 5-10% |
| 6-7  | 20-40% |
| 8-11 | 70-100% |
| 12   | 80% |
| 13-16| 90-100% |
| 17-19| 50-70% |
| 20-23| 15-30% |

Weekend traffic is reduced to 30% of weekday levels.

### Traffic Bursts

When `BURST_ENABLED=true`, random traffic spikes occur:
- 1% chance per minute
- Burst size: 50-200 extra logs
- Simulates sudden traffic increases

## Anomaly Types

### Normal Logs
- Status codes: 200 (85%), 201, 204, 301, 302, 304, 400, 404
- Latency: ~50ms with normal distribution
- Error rate: 0.1-2%

### Anomalous Logs
- Status codes: 500 (40%), 502, 503, 504, 400, 403, 429
- Latency: 500-5000ms (10-20x normal)
- Elevated request counts (5000-10000)
- High error rates (50%)

## Integration with Logstash

The log generator writes to `/var/log/app-logs/` which is mounted to `./logs/` on the host. Logstash monitors this directory and ingests logs into Elasticsearch.

### Logstash Pipeline

The logs are parsed by `logstash/pipeline/logsParser.conf`:
- Extracts timestamp, level, HTTP method, URL, status, duration
- Creates dynamic index based on filename
- Outputs to `elasticsearch-dataset:9200`

## Aggregated Mode

Set `AGGREGATED_MODE=true` for time-series testing (ARMAX algorithm):

```json
{
  "@timestamp": "2025-11-27T18:30:00.000000+00:00",
  "request_count": 1523,
  "error_count": 15,
  "error_rate": 0.0098,
  "avg_latency_ms": 48.5,
  "p95_latency_ms": 121.25,
  "p99_latency_ms": 194.0,
  "bytes_sent": 4569000,
  "active_users": 234,
  "is_workday": 1,
  "hour": 18
}
```

## Monitoring

View generator stats every minute in logs:
```
2025-11-27 18:30:00 [INFO] Stats: 3456 logs generated, 42 anomalies (1.22%)
```

## Graceful Shutdown

The generator handles `SIGINT` and `SIGTERM` gracefully:
```bash
docker stop log-generator
# Logs: "Received signal 15, shutting down..."
# Logs: "Shutting down. Total: 12345 logs, 123 anomalies"
```

## Development

### Local Testing

```bash
# Create test output directory
mkdir -p ./test-logs

# Run with verbose output
python continuous_log_generator.py \
  --output-dir ./test-logs \
  --logs-per-minute 10 \
  --anomaly-prob 0.1 \
  --format json

# Watch generated logs
tail -f ./test-logs/continuous-logs.log | jq
```

### Customization

Extend `FakeDataGenerator` class to add custom data types:

```python
class MyDataGenerator(FakeDataGenerator):
    def generate_custom_field(self):
        return self.fake.custom_provider()
```
