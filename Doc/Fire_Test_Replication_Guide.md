# Fire Test Replication Guide

This guide provides generic steps to replicate the comprehensive "Fire Test" of the Knowledge Base anomaly detection system. Follow these steps to set up and validate the complete end-to-end system functionality.

## Prerequisites

- Docker and Docker Compose installed
- Python 3.x with required dependencies (pymongo, pandas, numpy)
- MCP servers configured:
  - KB-MCP server (for configuration management)
  - Elasticsearch MCP server (for data exploration)
- Access to Elasticsearch with sample data (kibana_sample_data_logs)

## Step 1: Infrastructure Setup

### 1.1 Start Docker Services
```bash
# Navigate to project root directory
cd /path/to/FinalProjectADF

# Start all infrastructure services
docker-compose up -d

# Verify services are running
docker ps
```

**Expected Result**: 3 containers running (elasticsearch-dataset, kibana, mongodb)

### 1.2 Verify Elasticsearch Access
```bash
# Check if Elasticsearch is accessible
curl -X GET "localhost:9200/_cluster/health?pretty"
```

**Expected Result**: Status should be "green" or "yellow"

## Step 2: Data Exploration with MCP Elasticsearch

### 2.1 List Available Indices
Use MCP Elasticsearch tool to list indices:
```bash
# MCP Tool: elasticsearch.list_indices
{
  "index_pattern": "*"
}
```

### 2.2 Explore Sample Data Structure
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

### 2.3 Get Field Mappings
```bash
# MCP Tool: elasticsearch.get_mappings
{
  "index": ".ds-kibana_sample_data_logs-*"
}
```

### 2.4 Test ES|QL Query
```bash
# MCP Tool: elasticsearch.esql
{
  "query": "FROM .ds-kibana_sample_data_logs-* | LIMIT 10"
}
```

## Step 3: Create Knowledge Base Configurations

### 3.1 Create HTTP Status Monitoring KB
Use MCP KB-MCP tool to create configuration:
```bash
# MCP Tool: create_da_config
{
  "description": "HTTP Status Code Anomaly Detection - Monitors 5xx error rates",
  "query": "FROM .ds-kibana_sample_data_logs-* | WHERE @timestamp >= '2025-10-01T00:00:00.000Z' AND @timestamp < '2025-11-01T00:00:00.000Z' | EVAL es_timestamp = DATE_TRUNC(1 hour, @timestamp) | STATS status_code_200_counter = COUNT(*) WHERE response == '200', status_code_5xx_counter = COUNT(*) WHERE response >= '500' AND response < '600' BY es_timestamp | SORT es_timestamp",
  "training_from": "2025-10-01T00:00:00Z",
  "training_to": "2025-10-09T23:59:59Z",
  "detection_frequency": "5m",
  "detection_start": "2025-10-10T00:00:00Z",
  "algorithms": [
    {
      "Algorithm": "ZScore",
      "Parameters": {
        "threshold": 3.0,
        "observed_value": "status_code_5xx_counter"
      }
    }
  ]
}
```

**Note**: Save the generated KB ID for later verification.

### 3.2 Create Bandwidth Monitoring KB
```bash
# MCP Tool: create_da_config
{
  "description": "Bandwidth Transfer Volume Monitoring - Detects unusual data transfer spikes",
  "query": "FROM .ds-kibana_sample_data_logs-* | WHERE @timestamp >= '2025-10-01T00:00:00.000Z' AND @timestamp < '2025-11-01T00:00:00.000Z' | EVAL es_timestamp = DATE_TRUNC(1 hour, @timestamp) | STATS avg_bytes = AVG(bytes) BY es_timestamp | SORT es_timestamp",
  "training_from": "2025-10-01T00:00:00Z",
  "training_to": "2025-10-09T23:59:59Z",
  "detection_frequency": "5m",
  "detection_start": "2025-10-10T00:00:00Z",
  "algorithms": [
    {
      "Algorithm": "ZScore",
      "Parameters": {
        "threshold": 3.0,
        "observed_value": "avg_bytes"
      }
    }
  ]
}
```

### 3.3 Create Geographic Traffic Monitoring KB
```bash
# MCP Tool: create_da_config
{
  "description": "Geographic Traffic Pattern Analysis - Monitors traffic by region",
  "query": "FROM .ds-kibana_sample_data_logs-* | WHERE @timestamp >= '2025-10-01T00:00:00.000Z' AND @timestamp < '2025-11-01T00:00:00.000Z' | EVAL es_timestamp = DATE_TRUNC(1 hour, @timestamp) | STATS cn_traffic = COUNT(*) WHERE geo.src == 'CN' BY es_timestamp | SORT es_timestamp",
  "training_from": "2025-10-01T00:00:00Z",
  "training_to": "2025-10-09T23:59:59Z",
  "detection_frequency": "5m",
  "detection_start": "2025-10-10T00:00:00Z",
  "algorithms": [
    {
      "Algorithm": "ZScore",
      "Parameters": {
        "threshold": 3.0,
        "observed_value": "cn_traffic"
      }
    }
  ]
}
```

### 3.4 Verify Configurations Created
```bash
# MCP Tool: list_kb_configurations
{}
```

**Expected Result**: Should show 3 KB configurations with different IDs.

## Step 4: Deploy and Launch Containers

### 4.1 Run Deployer
```bash
python Deployer/deployer.py
```

**Expected Output**:
- "Found 3 KB configurations"
- Container launch messages for each KB
- MotorDA config generation messages

### 4.2 Verify Containers
```bash
docker ps
```

**Expected Result**: 6 containers total (3 Logstash + 3 infrastructure)

### 4.3 Check Container Logs
```bash
# Check one of the Logstash containers (use actual container name from docker ps)
docker logs logstash-kb-[KB_ID] --tail 20
```

**Expected Result**: Should show successful pipeline startup without ES|QL parsing errors.

## Step 5: Verify Data Collection

### 5.1 Check MongoDB Databases
```bash
docker exec mongodb mongosh --username admin --password 1q2w3E* --authenticationDatabase admin --eval "db.getMongo().getDBNames()"
```

**Expected Result**: Should include "logsdb"

### 5.2 Check Collections
```bash
docker exec mongodb mongosh --username admin --password 1q2w3E* --authenticationDatabase admin logsdb --eval "db.getCollectionNames()"
```

**Expected Result**: Should show 3 collections with KB IDs as names.

### 5.3 Verify Data Counts
```bash
# Check each collection (replace [KB_ID] with actual IDs)
docker exec mongodb mongosh --username admin --password 1q2w3E* --authenticationDatabase admin logsdb --eval "db['[KB_ID_1]'].countDocuments()"
docker exec mongodb mongosh --username admin --password 1q2w3E* --authenticationDatabase admin logsdb --eval "db['[KB_ID_2]'].countDocuments()"
docker exec mongodb mongosh --username admin --password 1q2w3E* --authenticationDatabase admin logsdb --eval "db['[KB_ID_3]'].countDocuments()"
```

**Expected Result**: Each collection should have ~600+ documents.

**⚠️ Important Note**: Be patient for the first data extraction! The initial data collection to MongoDB will take as much time as the `detection_frequency` interval configured in your KB config (default: 5 minutes). Don't expect to see data immediately after containers start - wait at least the configured interval before checking document counts.

**Windows Example**: Use `ping -n 301 127.0.0.1 > nul` to wait 5 minutes (300 seconds) before checking data counts.

## Step 6: Run Anomaly Detection

### 6.1 Execute MotorDA
```bash
python MotorDA/da-algorithm-zScore-mongo.py
```

**Expected Output**:
- "Found 3 DA configurations"
- Processing messages for each KB
- Anomaly detection results with z-scores

### 6.2 Review Results
Look for:
- ✅ Successful data retrieval from MongoDB
- ✅ Z-score calculations for each time window
- ✅ Anomaly detection (z-score > 3.0) where applicable
- ✅ No "No data to analyze" errors

## Step 7: Troubleshooting

### If ES|QL Parsing Errors Occur:
1. Check that ES|QL queries use double quotes for strings
2. Verify `prepare_esql_query()` function converts single quotes properly
3. Restart containers after fixing queries

### If No Data Found:
1. Verify date ranges in MotorDA configs match data collection period
2. Check MongoDB collection names match KB IDs
3. Ensure Logstash containers are running and processing data

### If Authentication Errors:
1. Use correct MongoDB credentials: `--username admin --password 1q2w3E*`
2. Include `--authenticationDatabase admin` parameter

### If Container Issues:
1. Stop existing containers: `docker stop [container_names]`
2. Remove containers: `docker rm [container_names]`
3. Re-run deployer

## Validation Checklist

- [ ] Docker services running (3 infrastructure containers)
- [ ] Elasticsearch accessible and healthy
- [ ] Sample data available in kibana_sample_data_logs
- [ ] 3 KB configurations created via MCP
- [ ] Deployer runs successfully
- [ ] 3 Logstash containers running
- [ ] MongoDB has logsdb database
- [ ] 3 collections created with data
- [ ] MotorDA processes all configurations
- [ ] Anomaly detection produces results
- [ ] No critical errors in logs

## Expected Performance Metrics

- **Data Collection**: ~600-700 documents per KB collection
- **Anomaly Detection**: At least one KB should show anomalies (z-score > 3.0)
- **Container Stability**: All containers running without restarts
- **Query Performance**: ES|QL queries execute within seconds

## Notes

- KB IDs are auto-generated UUIDs - use the actual IDs returned by MCP tools
- Date ranges can be adjusted based on your data availability
- ES|QL syntax is strict - double quotes required for string literals
- Container names follow pattern: `logstash-kb-[KB_ID]`
- MongoDB collections are named after KB IDs for data isolation