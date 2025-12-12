# Fire Test Commands Documentation

This document contains all the commands and MCP operations used during the comprehensive "Fire Test" of the Knowledge Base anomaly detection system.

## Prerequisites
- Docker and Docker Compose installed
- Python 3.x with required dependencies
- MCP servers configured (KB-MCP and Elasticsearch)

## 1. Infrastructure Setup

### Start Docker Compose Infrastructure
```bash
docker-compose up -d
```

Note: The `log-generator` is not started by default. To enable the load generator for a fire test, run docker-compose with the `stress` profile: `docker-compose --profile stress up -d`. If you need to override environment variables, pass your custom env-file by name using `--env-file <your-file>` (optional). Use this profile only when you intentionally want to generate high load.

CAUTION: The stress profile generates high load. Do NOT use `--profile stress` on production systems or local machines without sufficient resources. Use it only for controlled fire tests.

### Verify Infrastructure Status
```bash
docker ps
```

## 2. MCP Elasticsearch Operations
## 2.5 Fire Test using Log Generator (stress profile)
### Quick Fire Test (short-run) Example
Use this to validate a short end-to-end flow without long waits. This example focuses on quick detection using minute-level buckets and a short historical range.

1) Optionally override load parameters by setting env variables or editing `docker-compose.yml`. Example env values for a quick test:

```pwsh
BASE_REQUESTS_PER_HOUR=1200
HISTORICAL_DAYS=1
CONTINUOUS_INTERVAL=0.2
LOGS_PER_INTERVAL_MIN=20
LOGS_PER_INTERVAL_MAX=100
NUM_WORKERS=4
CHUNK_SIZE=1000
```

2) Start the stack with stress profile:

```pwsh
docker-compose --profile stress up -d --build
```

3) Create a KB configuration with 1-minute buckets and 1-minute detection frequency (for quick response):

```bash
docker exec -i kb-mcp python kb-mcp.py --kb-config '{"name":"quick-fire","description":"Quick 1-min detection","source_index":"ecommerce-logs","elasticsearch_sql_query":"FROM \"ecommerce-logs\" WHERE @timestamp >= '$from' AND @timestamp < '$to' | EVAL es_timestamp = DATE_TRUNC(\"minute\", @timestamp) | STATS COUNT(CASE WHEN response >= 500 AND response < 600 THEN 1 ELSE NULL END) AS error_5xx_count BY es_timestamp | SORT es_timestamp","query_mode":{"type":"aggregated","timestamp_field":"es_timestamp"},"algorithm":{"name":"zscore","parameters":[{"dimension":"error_5xx_count","is_active":true}]},"scheduling":{"training_config":{"from":"2025-12-11T00:00:00Z","to":"2025-12-11T23:59:59Z","is_active":true},"detection_config":{"frequency":"*/1 * * * *","detection_window":60,"is_active":true}}}'
```

NOTE: Adjust the `training_config` dates and `source_index` if necessary.

4) Monitor the Extractor and DA-Dispatcher logs to see the training and detection steps and to watch anomalies being produced in Elasticsearch.

```pwsh
docker logs -f etl-app
docker logs -f da-dispatcher
```

5) Validate results in MongoDB (series and trained_models) and Elasticsearch (anomalies index):

```pwsh
docker exec mongodb mongosh -u admin -p '1q2w3E*' --authenticationDatabase admin --eval "use anomaly_detection; db.getCollectionNames()"
docker exec mongodb mongosh -u admin -p '1q2w3E*' --authenticationDatabase admin --eval "use anomaly_detection; db['series'].find({ 'metadata.kbId': 'REPLACE_WITH_KB_ID' }).limit(5).pretty()"
curl -s 'http://localhost:9201/anomaly_results/_search?pretty' | jq '.hits.hits'
```

6) Stop or tune the generator when done:

```pwsh
docker stop log-generator
docker-compose --profile stress down
```


To run a fire test using the built-in `log-generator` service, use the `stress` profile from `docker-compose` and optionally provide overrides via a `.env` file.

1) Optionally provide an env-file with your overrides or set env variables prior to running the stress profile. Example values:

```pwsh
BASE_REQUESTS_PER_HOUR=2000
HISTORICAL_DAYS=7
CONTINUOUS_INTERVAL=0.5
LOGS_PER_INTERVAL_MIN=50
LOGS_PER_INTERVAL_MAX=150
CONTINUOUS_ANOMALY_RATE=0.02
BURST_PROBABILITY=0.05
BURST_SIZE_MIN=200
BURST_SIZE_MAX=1000
NUM_WORKERS=8
CHUNK_SIZE=10000
```

2) Start the stack with stress profile (optional env-file not required):

```bash
docker-compose --profile stress up -d --build
```

3) Monitor the log-generator:

```bash
docker logs -f log-generator
docker logs -f da-dispatcher
```

4) Example to stop only stress components:

```bash
docker stop log-generator
```

5) Full cleanup with profile:

```bash
docker-compose --profile stress down
```


### List Available Elasticsearch Indices
```bash
# MCP Tool: elasticsearch.list_indices
{
  "index_pattern": "*"
}
```

### Search Sample Data for Available Fields
```bash
# MCP Tool: elasticsearch.search
{
  "index": ".ds-kibana_sample_data_logs-*",
  "query_body": {
    "size": 1,
    "_source": true
  }
}
```

### Get Mappings for Sample Data Index
```bash
# MCP Tool: elasticsearch.get_mappings
{
  "index": ".ds-kibana_sample_data_logs-*"
}
```

### Execute ES|QL Query for Data Exploration
```bash
# MCP Tool: elasticsearch.esql
{
  "query": "FROM .ds-kibana_sample_data_logs-* | LIMIT 10"
}
```

## 3. MCP KB-MCP Operations

### Create KB Configuration 1: HTTP Status Code Monitoring
```bash
# MCP Tool: create_da_config (modern KBConfig schema)
{
  "name": "http-5xx-errors",
  "description": "HTTP Status Code Anomaly Detection - Monitors 5xx error rates for service health",
  "source_index": "ecommerce-logs",
  "elasticsearch_sql_query": "FROM \"ecommerce-logs\" WHERE @timestamp >= '$from' AND @timestamp < '$to' | EVAL es_timestamp = DATE_TRUNC('hour', @timestamp) | STATS COUNT(CASE WHEN response >= 500 AND response < 600 THEN 1 ELSE NULL END) AS error_5xx_count BY es_timestamp | SORT es_timestamp",
  "query_mode": {"type": "aggregated", "timestamp_field": "es_timestamp"},
  "algorithm": {"name": "zscore", "parameters": [{"dimension": "error_5xx_count", "is_active": true}]},
  "scheduling": {
    "training_config": {"from": "2025-10-01T00:00:00Z", "to": "2025-10-09T23:59:59Z", "is_active": true},
    "detection_config": {"frequency": "*/5 * * * *", "detection_window": 3600, "is_active": true}
  }
}
```

### Create KB Configuration 2: Bandwidth Transfer Monitoring
```bash
# MCP Tool: create_da_config (modern KBConfig schema)
{
  "name": "bandwidth-transfer-volume",
  "description": "Bandwidth Transfer Volume Monitoring - Detects unusual spikes in data transfer volumes",
  "source_index": "ecommerce-logs",
  "elasticsearch_sql_query": "FROM \"ecommerce-logs\" WHERE @timestamp >= '$from' AND @timestamp < '$to' | EVAL es_timestamp = DATE_TRUNC('hour', @timestamp) | STATS AVG(bytes) AS avg_bytes BY es_timestamp | SORT es_timestamp",
  "query_mode": {"type": "aggregated", "timestamp_field": "es_timestamp"},
  "algorithm": {"name": "zscore", "parameters": [{"dimension": "avg_bytes", "is_active": true}]},
  "scheduling": {
    "training_config": {"from": "2025-10-01T00:00:00Z", "to": "2025-10-09T23:59:59Z", "is_active": true},
    "detection_config": {"frequency": "*/5 * * * *", "detection_window": 3600, "is_active": true}
  }
}
```

### Create KB Configuration 3: Geographic Traffic Monitoring
```bash
# MCP Tool: create_da_config (modern KBConfig schema)
{
  "name": "cn-traffic-monitor",
  "description": "Geographic Traffic Pattern Analysis - Monitors unusual traffic patterns by country/region",
  "source_index": "ecommerce-logs",
  "elasticsearch_sql_query": "FROM \"ecommerce-logs\" WHERE @timestamp >= '$from' AND @timestamp < '$to' | EVAL es_timestamp = DATE_TRUNC('hour', @timestamp) | STATS COUNT(CASE WHEN geo.src == 'CN' THEN 1 ELSE NULL END) AS cn_traffic BY es_timestamp | SORT es_timestamp",
  "query_mode": {"type": "aggregated", "timestamp_field": "es_timestamp"},
  "algorithm": {"name": "zscore", "parameters": [{"dimension": "cn_traffic", "is_active": true}]},
  "scheduling": {
    "training_config": {"from": "2025-10-01T00:00:00Z", "to": "2025-10-09T23:59:59Z", "is_active": true},
    "detection_config": {"frequency": "*/5 * * * *", "detection_window": 3600, "is_active": true}
  }
}
```

### List All KB Configurations
```bash
# MCP Tool: list_kb_configurations
{}
```

## 4. Deployment & CLI Operations

### Start the stack and generate configs
This repository no longer relies on a top-level `Deployer/deployer.py` script. Instead, use `docker-compose` to start services and the KB-MCP CLI to create and manage KB configurations. Example:
```bash
# Start the stack
docker-compose up -d

# Create KB configuration using the KB-MCP CLI (inside the container to use internal network)
docker exec -i kb-mcp python kb-mcp.py --kb-config '{...json...}'
```

### Verify Container Status
```bash
docker ps
```

### Check Container Logs (Example)
```bash
docker logs logstash --tail 20
```

## 5. MongoDB Verification

### List Databases
```bash
docker exec mongodb mongosh --username admin --password 1q2w3E* --authenticationDatabase admin --eval "db.getMongo().getDBNames()"
```

### List Collections in `anomaly_detection` DB
```bash
docker exec mongodb mongosh --username admin --password 1q2w3E* --authenticationDatabase admin --eval "use anomaly_detection; db.getCollectionNames()"
```

### Count Documents in Collections
```bash
# HTTP Status Collection (series per KB)
docker exec mongodb mongosh --username admin --password 1q2w3E* --authenticationDatabase admin --eval "use anomaly_detection; db['series'].find({ 'metadata.kbId': 'be566b15-94d5-4c6b-b622-036f14cf9096' }).count()"

# Bandwidth Collection (series per KB)
docker exec mongodb mongosh --username admin --password 1q2w3E* --authenticationDatabase admin --eval "use anomaly_detection; db['series'].find({ 'metadata.kbId': '60c00c7c-d853-4bdc-ab1f-efaffd9a7481' }).count()"

# Geographic Collection (series per KB)
docker exec mongodb mongosh --username admin --password 1q2w3E* --authenticationDatabase admin --eval "use anomaly_detection; db['series'].find({ 'metadata.kbId': '409e9efb-4eb4-4a84-8a9c-01b2b2fdec43' }).count()"
```

## 6. MotorDA Anomaly Detection

### Run Anomaly Detection (DA Dispatcher)
```bash
# Run DA-Dispatcher from container (recommended)
docker exec -it da-dispatcher sh -c "python -m MotorDA.Dispatcher.DADispatcher"

# Or run locally for development (host environment)
python -m MotorDA.Dispatcher.DADispatcher
```

## 7. Container Management (During Troubleshooting)

### Stop Existing Containers (for cleanup)
```bash
docker stop logstash
```

### Remove Existing Containers (for cleanup)
```bash
docker rm logstash
```

## 8. Configuration Updates (During Troubleshooting)

### Update MotorDA Config Dates (Example for one config)
The MotorDA configs needed date range updates to match collected data:

```json
{
  "Scheduling": {
    "TrainingPeriod": {
      "from": "2025-10-01T00:00:00Z",
      "to": "2025-10-09T23:59:59Z"
    },
    "Detection": {
      "frequency": "60",
      "start": "2025-10-10T00:00:00Z"
    }
  }
}
```

## Problems Encountered and Solutions

### 1. ES|QL Query Parsing Errors
**Problem**: Logstash containers failed to start with ES|QL parsing errors.
```
[2025-10-10T03:41:22,568][INFO ][logstash.inputs.elasticsearch.esql][main] `METADATA` not found the query. `_id`, `_version` and `_index` will not be available in the result {:query=>"FROM .ds-kibana_sample_data_logs-* | WHERE @timestamp >= \"2025-10-01T00:00:00.000Z\" AND @timestamp < \"2025-11-01T00:00:00.000Z\" | EVAL es_timestamp = DATE_TRUNC(1 hour, @timestamp) | STATS status_code_200_counter = COUNT(*) WHERE response == \"200\", status_code_5xx_counter = COUNT(*) WHERE response >= \"500\" AND response < \"600\" BY es_timestamp | SORT es_timestamp"}
```

**Root Cause**: Single quotes in ES|QL queries were being escaped with backslashes (`\'`), but ES|QL syntax requires double quotes for string literals.

**Solution**: Modified `prepare_esql_query()` function in `deployer.py` to convert single quotes to double quotes:
```python
def prepare_esql_query(s: str) -> str:
    # Convert ES|QL single quotes to double quotes (ES|QL uses double quotes for strings)
    return s.replace("'", '"')
```

### 2. Date Range Mismatch in MotorDA Configurations
**Problem**: MotorDA anomaly detection found no data to analyze.
```
Warning: No documents found in the given range for collection be566b15-94d5-4c6b-b622-036f14cf9096.
Iniciando detector de anomalias
No data to analyze.
```

**Root Cause**: MotorDA configs were set to training period September 1-30, 2025, but Logstash was collecting data from October 1-31, 2025.

**Solution**: Updated all MotorDA configuration files to use correct date ranges:
```json
{
  "Scheduling": {
    "TrainingPeriod": {
      "from": "2025-10-01T00:00:00Z",
      "to": "2025-10-09T23:59:59Z"
    },
    "Detection": {
      "start": "2025-10-10T00:00:00Z"
    }
  }
}
```

### 3. MongoDB Authentication Errors
**Problem**: Initial attempts to access MongoDB failed.
```
MongoServerError: Command listDatabases requires authentication
```

**Root Cause**: MongoDB was configured with authentication but commands didn't include credentials.

**Solution**: Used proper authentication parameters in all MongoDB commands:
```bash
docker exec mongodb mongosh --username admin --password 1q2w3E* --authenticationDatabase admin
```

### 4. Container Management Issues
**Problem**: Attempting to restart containers with new configurations failed due to existing containers.

**Solution**: Implemented proper container cleanup sequence:
```bash
docker stop logstash
docker rm logstash
```

### 5. Data Collection Verification Challenges
**Problem**: Needed to verify data isolation but encountered authentication and collection access issues.

**Solution**: Used authenticated MongoDB queries to verify collection counts and data integrity.

## Summary of Test Results

- ✅ **Infrastructure**: 6 containers running (3 Logstash + 3 infrastructure)
- ✅ **Data Collection**: 626 documents per collection (1,878 total)
- ✅ **Data Isolation**: 3 separate MongoDB collections
- ✅ **Anomaly Detection**: Successfully detected HTTP error anomalies (z-scores > 4.0)
- ✅ **ES|QL Queries**: Corrected quote handling for proper parsing

## Lessons Learned

- **ES|QL Syntax**: Always use double quotes for string literals in ES|QL queries
- **Date Synchronization**: Ensure MotorDA training periods match actual data collection windows
- **Authentication**: MongoDB requires explicit authentication parameters
- **Container Lifecycle**: Proper cleanup is essential when redeploying containers
- **Error Logs**: Container logs provide critical debugging information
- **Configuration Validation**: Always verify configurations before deployment

## Notes

- ES|QL queries use double quotes for string literals (not single quotes)
- Container-per-KB architecture ensures complete data isolation
- MotorDA configs must have training periods that match actual data collection dates
- MongoDB authentication requires username/password parameters
- Container logs are essential for troubleshooting pipeline issues