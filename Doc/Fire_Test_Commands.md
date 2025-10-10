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

### Verify Infrastructure Status
```bash
docker ps
```

## 2. MCP Elasticsearch Operations

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
# MCP Tool: create_da_config
{
  "description": "HTTP Status Code Anomaly Detection - Monitors 5xx error rates for service health",
  "query": "FROM .ds-kibana_sample_data_logs-* | WHERE @timestamp >= '2025-10-01T00:00:00.000Z' AND @timestamp < '2025-11-01T00:00:00.000Z' | EVAL es_timestamp = DATE_TRUNC(1 hour, @timestamp) | STATS status_code_200_counter = COUNT(*) WHERE response == '200', status_code_5xx_counter = COUNT(*) WHERE response >= '500' AND response < '600' BY es_timestamp | SORT es_timestamp",
  "training_from": "2025-10-01T00:00:00Z",
  "training_to": "2025-10-09T23:59:59Z",
  "detection_frequency": "5m",
  "detection_start": "2025-10-10T00:00:00Z",
  "algorithms": [
    {
      "Algorithm": "ZScore",
      "Parameters": {
        "threshold": 3,
        "observed_value": "status_code_5xx_counter"
      }
    }
  ]
}
```

### Create KB Configuration 2: Bandwidth Transfer Monitoring
```bash
# MCP Tool: create_da_config
{
  "description": "Bandwidth Transfer Volume Monitoring - Detects unusual spikes in data transfer volumes",
  "query": "FROM .ds-kibana_sample_data_logs-* | WHERE @timestamp >= '2025-10-01T00:00:00.000Z' AND @timestamp < '2025-11-01T00:00:00.000Z' | EVAL es_timestamp = DATE_TRUNC(1 hour, @timestamp) | STATS avg_bytes = AVG(bytes) BY es_timestamp | SORT es_timestamp",
  "training_from": "2025-10-01T00:00:00Z",
  "training_to": "2025-10-09T23:59:59Z",
  "detection_frequency": "5m",
  "detection_start": "2025-10-10T00:00:00Z",
  "algorithms": [
    {
      "Algorithm": "ZScore",
      "Parameters": {
        "threshold": 3,
        "observed_value": "avg_bytes"
      }
    }
  ]
}
```

### Create KB Configuration 3: Geographic Traffic Monitoring
```bash
# MCP Tool: create_da_config
{
  "description": "Geographic Traffic Pattern Analysis - Monitors unusual traffic patterns by country/region",
  "query": "FROM .ds-kibana_sample_data_logs-* | WHERE @timestamp >= '2025-10-01T00:00:00.000Z' AND @timestamp < '2025-11-01T00:00:00.000Z' | EVAL es_timestamp = DATE_TRUNC(1 hour, @timestamp) | STATS cn_traffic = COUNT(*) WHERE geo.src == 'CN' BY es_timestamp | SORT es_timestamp",
  "training_from": "2025-10-01T00:00:00Z",
  "training_to": "2025-10-09T23:59:59Z",
  "detection_frequency": "5m",
  "detection_start": "2025-10-10T00:00:00Z",
  "algorithms": [
    {
      "Algorithm": "ZScore",
      "Parameters": {
        "threshold": 3,
        "observed_value": "cn_traffic"
      }
    }
  ]
}
```

### List All KB Configurations
```bash
# MCP Tool: list_kb_configurations
{}
```

## 4. Deployer Operations

### Run Deployer to Launch Containers and Generate Configs
```bash
python Deployer/deployer.py
```

### Verify Container Status
```bash
docker ps
```

### Check Container Logs (Example)
```bash
docker logs logstash-kb-be566b15-94d5-4c6b-b622-036f14cf9096 --tail 20
```

## 5. MongoDB Verification

### List Databases
```bash
docker exec mongodb mongosh --username admin --password 1q2w3E* --authenticationDatabase admin --eval "db.getMongo().getDBNames()"
```

### List Collections in logsdb
```bash
docker exec mongodb mongosh --username admin --password 1q2w3E* --authenticationDatabase admin logsdb --eval "db.getCollectionNames()"
```

### Count Documents in Collections
```bash
# HTTP Status Collection
docker exec mongodb mongosh --username admin --password 1q2w3E* --authenticationDatabase admin logsdb --eval "db['be566b15-94d5-4c6b-b622-036f14cf9096'].countDocuments()"

# Bandwidth Collection
docker exec mongodb mongosh --username admin --password 1q2w3E* --authenticationDatabase admin logsdb --eval "db['60c00c7c-d853-4bdc-ab1f-efaffd9a7481'].countDocuments()"

# Geographic Collection
docker exec mongodb mongosh --username admin --password 1q2w3E* --authenticationDatabase admin logsdb --eval "db['409e9efb-4eb4-4a84-8a9c-01b2b2fdec43'].countDocuments()"
```

## 6. MotorDA Anomaly Detection

### Run Anomaly Detection Tests
```bash
python MotorDA/da-algorithm-zScore-mongo.py
```

## 7. Container Management (During Troubleshooting)

### Stop Existing Containers
```bash
docker stop logstash-kb-be566b15-94d5-4c6b-b622-036f14cf9096 logstash-kb-60c00c7c-d853-4bdc-ab1f-efaffd9a7481 logstash-kb-409e9efb-4eb4-4a84-8a9c-01b2b2fdec43
```

### Remove Existing Containers
```bash
docker rm logstash-kb-be566b15-94d5-4c6b-b622-036f14cf9096 logstash-kb-60c00c7c-d853-4bdc-ab1f-efaffd9a7481 logstash-kb-409e9efb-4eb4-4a84-8a9c-01b2b2fdec43
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
docker stop logstash-kb-be566b15-94d5-4c6b-b622-036f14cf9096 logstash-kb-60c00c7c-d853-4bdc-ab1f-efaffd9a7481 logstash-kb-409e9efb-4eb4-4a84-8a9c-01b2b2fdec43
docker rm logstash-kb-be566b15-94d5-4c6b-b622-036f14cf9096 logstash-kb-60c00c7c-d853-4bdc-ab1f-efaffd9a7481 logstash-kb-409e9efb-4eb4-4a84-8a9c-01b2b2fdec43
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